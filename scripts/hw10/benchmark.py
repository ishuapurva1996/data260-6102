"""Collect a serial latency benchmark through the authenticated HW9 API."""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import cycle
from pathlib import Path
from time import perf_counter, sleep

import httpx

from scripts.hw09.cache_part2 import login
from scripts.hw10.benchmark_timing import (
    Attempt,
    EvidenceError,
    timing_row,
    timing_summary,
    unique_spans,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "reports/hw09/rental_fixtures.json"
QUESTIONS = (
    "How many units are available at {code}?",
    "What type of property is {code}?",
    "What title is advertised for listing {code}?",
    "What is the property type of {code}, and how many units are available?",
    "Give the title and number of available units for listing {code}.",
)
NAMESPACE = re.compile(r"hw10-benchmark-[a-z0-9][a-z0-9-]{0,48}")
DEFAULT_OUTPUT_ROOT = Path.home() / "code/agent_outputs/data260-hw10-planning/session-d"


@dataclass(frozen=True)
class Case:
    listing_code: str
    question: str


def fixtures():
    source = json.loads(FIXTURES.read_text(encoding="utf-8"))
    if source.get("synthetic") is not True:
        raise ValueError("expected the approved synthetic rental fixtures")
    return source["fixtures"]


def question_cases():
    codes = [fixture["listing_code"] for fixture in fixtures()]
    return [Case(code, question.format(code=code)) for question in QUESTIONS for code in codes]


def verify_fixtures(client):
    response = client.get("/api/rentals")
    response.raise_for_status()
    loaded = {row["listingCode"]: row for row in response.json()}
    fields = {
        "listingTitle": "listing_title",
        "propertyType": "property_type",
        "availableUnits": "available_units",
    }
    for fixture in fixtures():
        code = fixture["listing_code"]
        if any(loaded.get(code, {}).get(api) != fixture[key] for api, key in fields.items()):
            raise EvidenceError(f"load and verify the approved synthetic fixture {code} first")


def request_question(client, case_id, question):
    started = perf_counter()
    try:
        response = client.post("/api/kafka/questions", json={"question": question})
    except httpx.RequestError as exc:
        return Attempt(
            case_id,
            question,
            None,
            None,
            None,
            None,
            (perf_counter() - started) * 1000,
            type(exc).__name__,
        )
    http_ms = (perf_counter() - started) * 1000
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    response_id = body.get("request_id")
    header_id = response.headers.get("x-trace-id")
    trace_id = response_id or header_id
    return Attempt(
        case_id,
        question,
        response.status_code,
        trace_id if isinstance(trace_id, str) else None,
        body.get("is_cached"),
        body.get("latency_ms"),
        http_ms,
        "response and header trace IDs differ"
        if response_id and header_id and response_id != header_id
        else None,
    )


def jsonl(path, records):
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, allow_nan=False) + "\n")


def read_spans(path, trace_id):
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, ValueError) as exc:
        raise EvidenceError("missing or invalid span JSONL") from exc
    if any(
        not isinstance(record, dict) or record.get("trace_id") != trace_id for record in records
    ):
        raise EvidenceError("adapter returned an unrelated or malformed span")
    return records


def run_command(module, args, log_path, timeout, *, python=sys.executable):
    with log_path.open("ab") as log:
        try:
            return subprocess.run(
                [python, "-m", module, *args],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            ).returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EvidenceError(f"{module} failed ({type(exc).__name__})") from exc


def export_trace(attempt, directory, log_dir, source_sha):
    tracing = directory / "tracing"
    args = [
        "--log-dir",
        str(log_dir),
        "--output-dir",
        str(tracing),
        "--trace-id",
        attempt.trace_id,
        "--case-id",
        attempt.case_id,
    ]
    # A broker acknowledgement may be logged just after the HTTP response.
    deadline = perf_counter() + 5
    while (remaining := deadline - perf_counter()) > 0:
        if (
            run_command("scripts.hw10.export_traces", args, directory / "export.log", remaining)
            == 0
        ):
            spans = read_spans(tracing / "spans.jsonl", attempt.trace_id)
            if not spans or any(span.get("source_commit") != source_sha for span in spans):
                raise EvidenceError("trace sources do not match the measured checkout")
            return spans
        sleep(0.05)
    raise EvidenceError("trace export did not complete within 5 seconds")


def evaluate_trace(attempt, directory, judge_model, judge_digest, *, python=sys.executable):
    output = directory / "evaluation"
    code = run_command(
        "scripts.hw10.evaluate",
        [
            "pipeline",
            "--evidence-root",
            str(directory),
            "--trace-id",
            attempt.trace_id,
            "--model",
            judge_model,
            "--model-digest",
            judge_digest,
        ],
        directory / "evaluation.log",
        190,
        python=python,
    )
    if code != 0:
        raise EvidenceError(f"evaluator exited with status {code}")
    spans = read_spans(output / "spans.jsonl", attempt.trace_id)
    scores = read_spans(output / "pipeline_scores.jsonl", attempt.trace_id)
    if (
        len(spans) != 1
        or len(scores) != 1
        or not spans[0].get("evaluation_id")
        or spans[0]["evaluation_id"] != scores[0].get("evaluation_id")
        or scores[0].get("case_id") != attempt.case_id
    ):
        raise EvidenceError("evaluator did not produce a linked score and span")
    return spans


def collect(
    client,
    cases,
    output,
    *,
    target,
    max_attempts,
    reset_cache,
    capture,
    evaluate,
    provenance,
    pilot_only=False,
):
    """Run one excluded pilot, then replace exclusions until the target or cap."""
    if target < 1 or max_attempts < target or not cases:
        raise ValueError("expected questions and max_attempts >= target >= 1")
    rows = []
    seen = set()
    excluded = 0
    previous_trace_id = None
    for index, case in zip(range(1 if pilot_only else max_attempts + 1), cycle(cases)):
        case_id = "hw10-benchmark-pilot" if index == 0 else f"hw10-benchmark-{index:04d}"
        directory = output / case_id
        directory.mkdir()
        reset_cache(previous_trace_id)
        login(client)  # Refresh the teaching account token outside request timing.
        attempt = request_question(client, case_id, case.question)
        previous_trace_id = attempt.trace_id
        receipt = asdict(attempt)
        jsonl(output / "attempts.jsonl", [receipt])
        spans = []
        try:
            if attempt.trace_id:
                if attempt.trace_id in seen:
                    raise EvidenceError("duplicate request trace_id")
                seen.add(attempt.trace_id)
                spans.extend(capture(attempt, directory))
                if attempt.status_code == 200 and attempt.is_cached is False:
                    spans.extend(evaluate(attempt, directory))
            row = timing_row(attempt, spans)
            if index == 0:
                (output / "pilot_timing.json").write_text(
                    json.dumps(row, indent=2, allow_nan=False) + "\n", encoding="utf-8"
                )
                raise EvidenceError("pilot")
        except EvidenceError as exc:
            excluded += 1
            jsonl(output / "exclusions.jsonl", [{**receipt, "reason": str(exc)}])
            if spans:
                jsonl(directory / "spans.jsonl", unique_spans(spans))
            if index == 0 and str(exc) != "pilot":
                raise EvidenceError(f"pilot failed: {exc}") from exc
        else:
            rows.append(row)
            jsonl(output / "spans.jsonl", unique_spans(spans))
            with (output / "latency_rows.csv").open("a", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=row.keys())
                if len(rows) == 1:
                    writer.writeheader()
                writer.writerow(row)
        print(f"{case_id} {attempt.trace_id or '-'} | {len(rows)}/{target} admitted", flush=True)
        if len(rows) == target:
            break

    summary = {
        **provenance,
        **(timing_summary(rows) if rows else {}),
        "target_count": 0 if pilot_only else target,
        "admitted_count": len(rows),
        "exclusion_count": excluded,
        "complete": pilot_only or len(rows) == target,
        "pilot_only": pilot_only,
        "finished_at": datetime.now(UTC).isoformat(),
    }
    (output / "latency_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return summary


def cache_reset(cache):
    """Keep the live index and remove only the owned experiment's entry hashes."""

    def keys():
        return list(cache.redis.scan_iter(match=cache.entry_prefix + "*"))

    def verify_empty():
        if keys() or cache.redis.execute_command("FT.SEARCH", cache.index, "*", "LIMIT", 0, 0)[0]:
            raise EvidenceError("benchmark cache namespace is not empty")

    if not NAMESPACE.fullmatch(cache.settings.namespace):
        raise EvidenceError("use a fresh hw10-benchmark-<run-id> cache namespace")
    if cache.settings.threshold != 0.85 or cache.settings.allow_stale:
        raise EvidenceError("benchmark requires cutoff 0.85 with version enforcement")
    verify_empty()

    def reset(previous_trace_id):
        entries = keys()
        owned_key = (cache.entry_prefix + str(previous_trace_id)).encode()
        if any(key != owned_key for key in entries):
            raise EvidenceError("unexpected key in the benchmark cache namespace")
        if entries:
            cache.redis.delete(*entries)
        verify_empty()

    return reset


def source_revisions(a1, b1):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    if git("status", "--porcelain"):
        raise EvidenceError("measure from a clean committed checkout")
    for ref in (a1, b1):
        if not re.fullmatch(r"[0-9a-f]{40}", ref) or git("rev-parse", f"{ref}^{{commit}}") != ref:
            raise EvidenceError("A1 and B1 must be exact full commit SHAs")
    if git("merge-base", a1, b1) != a1 or git("merge-base", b1, "HEAD") != b1:
        raise EvidenceError("B1 must include A1 and HEAD must include B1")
    return {"a1": a1, "b1": b1, "measured_source_sha": git("rev-parse", "HEAD")}


def runtime_settings(log_dir, source_sha, settings):
    """Verify the exclusive stack's ready events and retain model settings."""
    ready = {}
    expected = {
        "api": "semantic_cache_ready",
        **dict.fromkeys(("planner", "writer", "reviewer"), "consumer_ready"),
    }
    for service, event in expected.items():
        path = log_dir / f"{service}.log"
        with path.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.startswith("{")]
        matches = [row for row in rows if row.get("event") == event]
        if len(matches) != 1 or matches[0].get("source_commit") != source_sha:
            raise EvidenceError(f"{service} log must record one ready event at the measured SHA")
        ready[service] = matches[0]
    api = ready.pop("api")
    if (
        api.get("namespace") != settings.namespace
        or api.get("threshold") != settings.threshold
        or api.get("allow_stale") is not False
    ):
        raise EvidenceError("API ready event does not match the benchmark cache configuration")
    if any(row.get("model") in (None, "", "fixture") for row in ready.values()):
        raise EvidenceError("benchmark requires real local models for all three agents")
    return {
        "embedding_model": api["embedding_model"],
        "embedding_digest": api["embedding_digest"],
        "agents": {
            service: {"model": row["model"], **row["configuration"]}
            for service, row in ready.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--log-dir", required=True, type=Path)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--judge-digest", required=True)
    parser.add_argument("--evaluator-python", default=sys.executable)
    parser.add_argument("--a1", required=True)
    parser.add_argument("--b1", required=True)
    parser.add_argument("--max-attempts", type=int, default=75)
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument("--exclusive-runtime", action="store_true", required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output_root = DEFAULT_OUTPUT_ROOT.resolve()
    if not output.is_relative_to(output_root) or output == output_root:
        parser.error(f"write live output to a new run directory under {DEFAULT_OUTPUT_ROOT}")
    provenance = source_revisions(args.a1, args.b1)
    log_dir = args.log_dir.resolve()
    from src.hw09.semantic_cache import CacheSettings, SemanticCache

    settings = CacheSettings.from_env()
    if "HW9_REDIS_URL" not in os.environ:
        parser.error("set HW9_REDIS_URL explicitly to the owned Redis instance")
    provenance["pipeline_settings"] = runtime_settings(
        log_dir, provenance["measured_source_sha"], settings
    )
    cache = SemanticCache(settings)
    try:
        reset = cache_reset(cache)
        output.mkdir(parents=True)
        provenance.update(
            synthetic=False,
            started_at=datetime.now(UTC).isoformat(),
            cache_namespace=settings.namespace,
            cache_threshold=settings.threshold,
            version_enforced=not settings.allow_stale,
            judge_model=args.judge_model,
            judge_model_digest=args.judge_digest,
        )
        print("Pragya Apurva | DATA 260 HW10 latency benchmark", flush=True)
        with httpx.Client(base_url="http://127.0.0.1:8702", timeout=195, trust_env=False) as client:
            login(client)
            verify_fixtures(client)
            result = collect(
                client,
                question_cases(),
                output,
                target=50,
                max_attempts=args.max_attempts,
                reset_cache=reset,
                provenance=provenance,
                pilot_only=args.pilot_only,
                capture=lambda attempt, directory: export_trace(
                    attempt,
                    directory,
                    log_dir,
                    provenance["measured_source_sha"],
                ),
                evaluate=lambda attempt, directory: evaluate_trace(
                    attempt,
                    directory,
                    args.judge_model,
                    args.judge_digest,
                    python=args.evaluator_python,
                ),
            )
    finally:
        cache.close()
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
