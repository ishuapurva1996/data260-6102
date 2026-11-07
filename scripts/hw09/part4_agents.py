"""Develop the Part 4 lesson, freeze the experiment, and run the held-out comparison."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from statistics import mean
from time import perf_counter_ns
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.hw09_agents import (
    ANSWER_PROMPT,
    MAX_ATTEMPTS,
    RUBRIC,
    AnsweringAgent,
    EvaluatorAgent,
    Lesson,
    Run,
    run_question,
    validate_lesson,
    validation_pair_passes,
)
from src.model_client import build_ollama_client

EVIDENCE = ROOT / "reports/hw09/raw/part4"
DATA = EVIDENCE / "data"
TRAIN = "training_data.json"
VALIDATION = "validation_data.json"
TEST = "test_data.json"
REFERENCE = "rental_reference.json"
MODEL = {
    "model_name": "qwen2.5:7b",
    "base_url": "http://127.0.0.1:11434",
    "temperature": 0,
    "timeout": 90,
    "response_format": "json",
    "context_window": 4096,
    "output_limit": 256,
    "seed": 6102,
}
VARIANTS = (
    ("Baseline", False, "none"),
    ("Evaluator Repair", True, "none"),
    ("Lesson Memory", True, "training"),
    ("Validated Improvement", True, "approved"),
)
CASE_FIELDS = {"listing_id", "question", "requested_fields"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path):
    return json.loads(path.read_bytes())


def write_json(path: Path, value, *, receipt: Path | None = None) -> None:
    contents = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temp = path.with_suffix(".tmp")
    temp.write_bytes(contents)
    if receipt is not None:
        receipt.write_text(sha256(contents).hexdigest() + "\n", encoding="utf-8")
    temp.replace(path)


def checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def model_identity() -> dict:
    def ollama(path):
        with urlopen(MODEL["base_url"] + path, timeout=5) as response:
            return json.load(response)

    model = next(
        item for item in ollama("/api/tags")["models"] if item["name"] == MODEL["model_name"]
    )
    return {
        "adapter_settings": MODEL,
        "digest": model["digest"],
        "quantization": model["details"]["quantization_level"],
        "ollama_version": ollama("/api/version")["version"],
    }


def hardware() -> dict:
    details = {"platform": platform.platform(), "python": platform.python_version()}
    if platform.system() == "Darwin":
        for name, key in (("chip", "machdep.cpu.brand_string"), ("memory_bytes", "hw.memsize")):
            details[name] = subprocess.check_output(["sysctl", "-n", key], text=True).strip()
    return details


def load_cases(raw: bytes, reference: dict) -> list[dict]:
    cases = json.loads(raw)
    if not cases or len({case["listing_id"] for case in cases}) != len(cases):
        raise ValueError("Expected at least one question, with distinct listing IDs")
    for case in cases:
        if set(case) != CASE_FIELDS or case["listing_id"] not in reference:
            raise ValueError("Expected input-only records with a reference listing")
        fields = case["requested_fields"]
        if (
            not isinstance(case["question"], str)
            or not case["question"].strip()
            or not isinstance(fields, list)
            or not fields
            or not all(isinstance(field, str) for field in fields)
            or len(fields) != len(set(fields))
        ):
            raise ValueError("Expected a question and distinct requested field names")
    return cases


def check_disjoint(*splits: list[dict]) -> None:
    all_ids = [case["listing_id"] for cases in splits for case in cases]
    all_questions = [case["question"] for cases in splits for case in cases]
    if len(all_ids) != len(set(all_ids)) or len(all_questions) != len(set(all_questions)):
        raise ValueError("Questions and listing IDs must be distinct across splits")


def trace(run: Run) -> dict:
    grade = run.attempts[-1].grade
    return {
        **asdict(run),
        "attempt_count": len(run.attempts),
        "final_evaluation": asdict(grade) if grade is not None else None,
    }


def run_cases(cases, reference, answering, evaluator) -> tuple[Run, ...]:
    return tuple(
        run_question(case, reference[case["listing_id"]], answering, evaluator) for case in cases
    )


class ControlledOmission:
    """Drop a field from real Ollama drafts only for the two controlled demos."""

    def __init__(self, model, attempts_to_alter):
        self.model = model
        self.remaining = attempts_to_alter
        self.original_drafts = []

    def complete(self, messages):
        result = self.model.complete(messages)
        self.original_drafts.append(result.content)
        if self.remaining == 0:
            return result
        self.remaining -= 1
        claims = json.loads(result.content)
        claims.pop("available_units", None)
        return replace(result, content=json.dumps(claims))


def controlled_case(case, listing, model, evaluator, omissions, expected):
    altered = ControlledOmission(model, omissions)
    run = run_question(case, listing, AnsweringAgent(altered), evaluator)
    if [attempt.grade.result for attempt in run.attempts] != expected:
        raise RuntimeError(f"Controlled demo did not produce {expected}: {trace(run)}")
    return {
        **trace(run),
        "omission_injected_on_attempts": list(range(1, omissions + 1)),
        "original_model_drafts": altered.original_drafts,
    }


def development_material() -> tuple[dict[str, bytes], dict]:
    datasets = {name: (DATA / name).read_bytes() for name in (REFERENCE, TRAIN, VALIDATION)}
    return datasets, {
        "datasets": {name: sha256(raw).hexdigest() for name, raw in datasets.items()},
        "code": {
            name: checksum(ROOT / name)
            for name in (
                "src/hw09_agents.py",
                "src/model_client.py",
                "scripts/hw09/part4_agents.py",
            )
        },
    }


def held_out_blob(source_commit: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", f"{source_commit}:{(DATA / TEST).relative_to(ROOT)}"],
        text=True,
    ).strip()


def develop(output: Path) -> None:
    if (output / "freeze.json").exists():
        raise FileExistsError("Configuration already frozen. Use a fresh output directory.")
    output.mkdir(parents=True, exist_ok=True)
    source_commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    test_blob = held_out_blob(source_commit)
    datasets, material_hashes = development_material()
    reference = json.loads(datasets[REFERENCE])
    train = load_cases(datasets[TRAIN], reference)
    validation = load_cases(datasets[VALIDATION], reference)
    check_disjoint(train, validation)
    model_config = model_identity()
    model = build_ollama_client(**MODEL)
    grader = EvaluatorAgent()
    started = now()
    print(f"{started} | Pragya Apurva | Training and controlled revision", flush=True)
    reuse_question_index = 2
    pattern_questions = train[:reuse_question_index] + train[reuse_question_index + 1 :]
    observed = run_cases(pattern_questions, reference, AnsweringAgent(model), grader)
    failures = [
        run.question["listing_id"]
        for run in observed
        if run.attempts[0].answer.claims is not None
        and "available_units" in run.attempts[0].grade.incorrect_fields
    ]
    if len(failures) < 2:
        raise RuntimeError(f"A repeated availability failure was not observed: {failures}")

    lesson = Lesson(
        lesson_id="rental-ready-units-v1",
        failure_pattern="Answers omit or misstate immediate availability in the rental export.",
        correction="For available_units use inventory_export.bucket_b, including zero. "
        "Bucket_a is in turnover. Advertised_vacancies is the total of both buckets.",
        created_at=now(),
        use_count=0,
        scope={"requested_field": "available_units", "source_field": "inventory_export"},
    )
    if not all(
        reference[key]["source"]["inventory_export"]["bucket_b"]
        == reference[key]["facts"]["available_units"]
        for key in failures
    ):
        raise RuntimeError("The proposed correction contradicts the training reference")

    demo_case = train[1]
    demo_listing = reference[demo_case["listing_id"]]
    repaired = controlled_case(demo_case, demo_listing, model, grader, 1, ["REVISE", "PASS"])
    stop_case = train[0]
    capped = controlled_case(
        stop_case, reference[stop_case["listing_id"]], model, grader, 2, ["REVISE", "REVISE"]
    )

    candidate_path = output / "training_memory/lessons.json"
    candidate_path.parent.mkdir(exist_ok=True)
    write_json(candidate_path, [asdict(lesson)])
    loaded_lessons = tuple(Lesson(**item) for item in read_json(candidate_path))
    reuse_agent = AnsweringAgent(model, loaded_lessons)
    reuse = run_cases([train[reuse_question_index]], reference, reuse_agent, grader)[0]
    if (
        reuse.lesson_ids != (lesson.lesson_id,)
        or reuse.attempts[0].grade.result != "PASS"
        or reuse_agent.use_counts[lesson.lesson_id] != 1
    ):
        raise RuntimeError(f"Lesson reuse was not demonstrated: {trace(reuse)}")
    candidate = replace(lesson, use_count=reuse_agent.use_counts[lesson.lesson_id])
    write_json(
        output / "development.json",
        {
            "started_at": started,
            "finished_at": now(),
            "model": model_config,
            "training_runs": [trace(run) for run in observed],
            "repeated_failure_listing_ids": failures,
            "controlled_revision": repaired,
            "controlled_stop": capped,
            "lesson_reuse": {
                **trace(reuse),
                "loaded_from": str(candidate_path.relative_to(output)),
                "loaded_lesson": asdict(lesson),
                "use_counts_after": reuse_agent.use_counts,
            },
        },
    )
    print(
        f"{now()} | repeated failures {failures}; repair PASS; stop REVISE; reuse PASS", flush=True
    )

    before = run_cases(validation, reference, AnsweringAgent(model), grader)
    after = run_cases(validation, reference, AnsweringAgent(model, (candidate,)), grader)
    accepted, pairs = validate_lesson(before, after, candidate, reference)
    if development_material()[1] != material_hashes:
        raise RuntimeError("Development datasets or code changed while the lesson was evaluated")
    approved = [asdict(candidate)] if accepted else []
    write_json(output / "lessons.json", approved)
    write_json(
        output / "validation.json",
        {
            "decided_at": now(),
            "candidate": asdict(candidate),
            "accepted": accepted,
            "before": [trace(run) for run in before],
            "after": [trace(run) for run in after],
            "pairs": pairs,
            "regressions": [pair for pair in pairs if not validation_pair_passes(pair)],
        },
    )
    print(
        f"{now()} | Validation {'accepted' if accepted else 'rejected'} {lesson.lesson_id}",
        flush=True,
    )
    write_json(
        output / "freeze.json",
        {
            "frozen_at": now(),
            "model": model_config,
            "hardware": hardware(),
            "source_head_at_freeze": source_commit,
            "held_out_git_blob": test_blob,
            "answer_prompt": ANSWER_PROMPT,
            "grading_rubric": RUBRIC,
            "maximum_attempts": MAX_ATTEMPTS,
            "semantic_cache": "bypassed: direct local adapter only",
            "files_sha256": {**material_hashes, "lessons_json": checksum(output / "lessons.json")},
            "variants": [list(variant) for variant in VARIANTS],
            "lesson_snapshots": {"none": [], "training": [asdict(candidate)], "approved": approved},
        },
        receipt=output / "freeze.sha256",
    )
    print(f"{now()} | Prompts, rubric, code hashes and lesson snapshots frozen", flush=True)


def benchmark(output: Path) -> None:
    result_path = output / "held_out_results.json"
    if result_path.exists():
        raise FileExistsError(
            "Held-out results already exist. Keep them and use a fresh output directory."
        )
    freeze_bytes = (output / "freeze.json").read_bytes()
    frozen_hash = sha256(freeze_bytes).hexdigest()
    if frozen_hash != (output / "freeze.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("The pre-test freeze receipt does not match the frozen configuration")
    freeze = json.loads(freeze_bytes)
    datasets, material_hashes = development_material()
    lesson_hash = checksum(output / "lessons.json")
    if (
        {**material_hashes, "lessons_json": lesson_hash} != freeze["files_sha256"]
        or model_identity() != freeze["model"]
        or [list(variant) for variant in VARIANTS] != freeze["variants"]
        or read_json(output / "lessons.json") != freeze["lesson_snapshots"]["approved"]
    ):
        raise RuntimeError("Frozen inputs, code, model or lesson state changed")
    started = now()
    test_bytes = (DATA / TEST).read_bytes()
    test_blob = (
        subprocess.check_output(
            ["git", "-C", str(ROOT), "hash-object", "--stdin"], input=test_bytes
        )
        .decode()
        .strip()
    )
    if test_blob != freeze["held_out_git_blob"]:
        raise RuntimeError("Held-out inputs differ from the committed Git blob recorded at freeze")
    test_hash = sha256(test_bytes).hexdigest()
    reference = json.loads(datasets[REFERENCE])
    test_cases = load_cases(test_bytes, reference)
    check_disjoint(
        test_cases,
        *(load_cases(datasets[name], reference) for name in (TRAIN, VALIDATION)),
    )
    print(
        f"{started} | Pragya Apurva | Held-out input opened after freeze; SHA-256 {test_hash}",
        flush=True,
    )
    grader = EvaluatorAgent()
    results = []
    warm_model = build_ollama_client(**MODEL)
    warm_model.complete([("user", 'Return only the JSON object {"ready":true}.')])
    for name, repair, snapshot in freeze["variants"]:
        lessons = tuple(Lesson(**row) for row in freeze["lesson_snapshots"][snapshot])
        answering = AnsweringAgent(build_ollama_client(**MODEL), lessons)
        variant_started = now()
        runs = run_cases(test_cases, reference, answering, grader if repair else None)
        variant_finished = now()
        rows = []
        for run in runs:
            score_started = perf_counter_ns()
            score = grader.evaluate(
                run.question, reference[run.question["listing_id"]], run.attempts[-1].answer
            )
            score_ms = (perf_counter_ns() - score_started) / 1_000_000
            rows.append(
                {**trace(run), "offline_grade": asdict(score), "offline_grade_ms": score_ms}
            )
        correct = sum(row["offline_grade"]["result"] == "PASS" for row in rows)
        summary = {
            "correct": correct,
            "incorrect": len(runs) - correct,
            "average_attempts": mean(len(run.attempts) for run in runs),
            "average_latency_ms": mean(run.latency_ms for run in runs),
        }
        results.append(
            {
                "variant": name,
                "repair": repair,
                "lesson_snapshot": snapshot,
                "test_sha256": test_hash,
                "started_at": variant_started,
                "answering_finished_at": variant_finished,
                "metrics": summary,
                "lesson_use_counts": answering.use_counts,
                "cases": rows,
            }
        )
        print(f"{variant_finished} | {name} | {json.dumps(summary)}", flush=True)

    if (
        checksum(DATA / TEST) != test_hash
        or checksum(output / "freeze.json") != frozen_hash
        or development_material()[1] != material_hashes
        or checksum(output / "lessons.json") != lesson_hash
    ):
        raise RuntimeError("Experiment inputs or configuration changed during the benchmark")
    write_json(
        result_path,
        {
            "student": "Pragya Apurva",
            "started_at": started,
            "finished_at": now(),
            "freeze_sha256": frozen_hash,
            "model": freeze["model"],
            "hardware": freeze["hardware"],
            "semantic_cache": freeze["semantic_cache"],
            "test_case_count": len(test_cases),
            "dataset_sha256": {**freeze["files_sha256"]["datasets"], TEST: test_hash},
            "variants": results,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("develop", "test"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    (develop if args.phase == "develop" else benchmark)(args.output)


if __name__ == "__main__":
    main()
