"""Audit the submitted HW10 evidence and exercise the integrated dashboard."""

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path

from scripts.hw10.benchmark_timing import (
    QUEUE_TOPICS,
    STAGES,
    Attempt,
    example_summary,
    timestamp,
    timing_row,
)

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/hw10"
RAW = REPORT / "raw"
A1 = "2cfb15d5eaa589c195c3f8b42168fd9fe5caec41"
A2 = "7893184b8296862a4bfb04f9e8c6461aa89a6de8"
B1 = "fc375db61d24243b7a54d900ec6245f043c2afe2"
C1 = "f08da13a9cff5ae915174b36a8b77da8484bc6c0"
D1 = "5e227abbe5576af032fab1e5794517c31e2d1ee7"
BASE = "53af679f111016ca4b6b0614274cbf11dcd88faf"
PATHS = ("code", "src", "scripts/hw08", "scripts/hw09", "scripts/run_hw09_web.py")
EXECUTION = (
    *PATHS,
    "scripts/hw10/benchmark.py",
    "scripts/hw10/export_traces.py",
    "scripts/hw10/collect_drafts.py",
    "scripts/hw10/evaluate.py",
    "scripts/hw10/evaluation_evidence.py",
    "scripts/hw10/evaluation_judge.py",
    "scripts/hw10/evaluation_validation.py",
    "requirements-hw09*",
    "requirements-hw08*",
    "requirements-hw10-evaluation.txt",
)
HANDOFF_MESSAGES = dict(zip(QUEUE_TOPICS, ("inbox", "planner", "writer", "reviewer")))
SCREENSHOTS = (
    "01-summary.png",
    "02-evaluation.png",
    "03-trace-cache-hit.png",
    "04-trace-successful-miss.png",
    "05-trace-writer-failure.png",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_number(actual, expected, label):
    require(math.isclose(float(actual), expected, abs_tol=1e-8), f"Mismatch in {label}")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def document(path):
    return json.loads(path.read_text())


def json_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def csv_rows(path):
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def indexed(records, key):
    result = {r[key]: r for r in records}
    require(len(result) == len(records), f"Duplicate {key}")
    return result


def group_spans(records):
    grouped = defaultdict(list)
    for row in records:
        grouped[row["trace_id"]].append(row)
    return grouped


def verify_provenance(study, benchmark):
    head = git("rev-parse", "HEAD").decode().strip()
    measured = benchmark["measured_source_sha"]
    scored = git("rev-parse", f"{B1}^").decode().strip()
    for older, newer in (
        (BASE, A1),
        (A1, A2),
        (A2, scored),
        (scored, B1),
        (B1, measured),
        (measured, D1),
        (D1, head),
        (C1, head),
    ):
        git("merge-base", "--is-ancestor", older, newer)
    for source, paths in (
        (measured, EXECUTION),
        (D1, (*EXECUTION, "scripts/hw10/benchmark_timing.py")),
        (B1, ("reports/hw10/raw/evaluation",)),
        (
            C1,
            (
                "scripts/hw10/dashboard.py",
                "scripts/hw10/dashboard_evidence.py",
            ),
        ),
        (D1, ("reports/hw10/raw/benchmark", "reports/hw10/raw/tracing")),
    ):
        git("diff", "--exit-code", source, "--", *paths)
    require(study["freeze_sha"] == benchmark["a2"] == A2, "Unexpected label freeze")
    require(study["tracing_sha"] == benchmark["a1"] == A1, "Unexpected tracing revision")
    require(benchmark["b1"] == B1, "Unexpected evaluator evidence revision")
    freeze_commit_time = datetime.fromisoformat(
        git("show", "-s", "--format=%cI", A2).decode().strip()
    )
    require(freeze_commit_time < timestamp(study["start_time"]), "Judge ran before freeze")

    frozen = {}
    for name in ("eval_cases.json", "human_labels.csv"):
        path = (REPORT / name).relative_to(ROOT).as_posix()
        data = (ROOT / path).read_bytes()
        require(data == git("show", f"{A2}:{path}"), f"Frozen blob changed: {name}")
        digest = hashlib.sha256(data).hexdigest()
        require(digest == study["input_sha256"][path], f"Wrong frozen checksum: {name}")
        frozen[name] = {"blob": git("rev-parse", f"{A2}:{path}").decode().strip(), "sha256": digest}
    screenshot_dir = REPORT / "screenshots"
    screenshots = {}
    for name in SCREENSHOTS:
        data = (screenshot_dir / name).read_bytes()
        require(data.startswith(b"\x89PNG\r\n\x1a\n"), f"Expected a PNG screenshot: {name}")
        screenshots[name] = hashlib.sha256(data).hexdigest()
    return {
        "verified_checkout": head,
        "hw9_base": BASE,
        "milestones": {"A1": A1, "A2": A2, "B1": B1, "C1": C1, "D1": D1},
        "frozen": frozen,
        "judge_source": scored,
        "benchmark_source": measured,
        "measured_execution_files_match": True,
        "benchmark_admission_matches": D1,
        "screenshots": screenshots,
    }


def midranks(values):
    ranks = [0.0] * len(values)
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    start = 1
    for _, tied in groupby(ordered, key=lambda item: item[1]):
        group = list(tied)
        end = start + len(group) - 1
        for index, _ in group:
            ranks[index] = (start + end) / 2
        start = end + 1
    return ranks


def verify_judge(study):
    cases = indexed(document(REPORT / "eval_cases.json"), "case_id")
    labels = indexed(csv_rows(REPORT / "human_labels.csv"), "case_id")
    require(len(cases) == 20 and cases.keys() == labels.keys(), "Wrong human reference set")
    require(len({case["trace_id"] for case in cases.values()}) == 20, "Duplicate draft trace")
    rows = csv_rows(RAW / "evaluation/judge_scores.csv")
    passes = indexed(study["passes"], "pass")
    require(len(rows) == study["scored_count"] == 60, "Expected 60 raw scores")
    require(study["status"] == "ok" and set(passes) == {1, 2, 3}, "Invalid study")
    require(study["primary_pass"] == 1 and study["case_count"] == 20, "Invalid study design")
    require(len({run["run_id"] for run in passes.values()}) == 3, "Duplicate judge run")
    scores = {}
    for row in rows:
        case_id, number = row["case_id"], int(row["pass"])
        key = case_id, number
        case, run = cases[case_id], passes[number]
        normalized, score = float(row["normalized_score"]), int(row["score"])
        require(
            key not in scores
            and row["study_id"] == study["study_id"]
            and row["trace_id"] == case["trace_id"] == case["correlation_id"]
            and row["run_id"] == run["run_id"]
            and run["status"] == row["status"] == "ok"
            and run["scored_count"] == 20
            and 0 <= normalized <= 1
            and score == math.floor(1.5 + 4 * normalized)
            and row["reason"].strip(),
            f"Invalid raw judge row: {key}",
        )
        scores[key] = score

    saved = indexed(study["comparisons"], "case_id")
    comparisons = []
    for case_id in sorted(cases):
        label = int(labels[case_id]["helpfulness"])
        require(1 <= label <= 5, f"Invalid human rating: {case_id}")
        ratings = [scores[case_id, number] for number in (1, 2, 3)]
        entry = {
            "case_id": case_id,
            "human_score": label,
            "judge_scores": ratings,
            "pass_1_absolute_difference": abs(label - ratings[0]),
            "score_change": max(ratings) - min(ratings),
        }
        require(saved[case_id] == entry, f"Saved judge comparison differs: {case_id}")
        comparisons.append(entry)

    human = [row["human_score"] for row in comparisons]
    primary = [row["judge_scores"][0] for row in comparisons]
    differences = [row["pass_1_absolute_difference"] for row in comparisons]
    changes = [row["score_change"] for row in comparisons]
    spearman = statistics.correlation(midranks(human), midranks(primary))
    mean_difference = statistics.mean(differences)
    repeatability = {
        "changed_count": sum(change > 0 for change in changes),
        "changed_rate": sum(change > 0 for change in changes) / len(changes),
        "mean_score_change": statistics.mean(changes),
        "max_score_change": max(changes),
    }
    same_number(study["spearman"], spearman, "Spearman")
    same_number(study["mean_absolute_difference"], mean_difference, "mean absolute difference")
    require(study["repeatability"] == repeatability, "Saved repeatability differs")
    return {
        "case_count": len(cases),
        "score_count": len(scores),
        "spearman": spearman,
        "mean_absolute_difference": mean_difference,
        "exact_agreements": differences.count(0),
        "pass_1_score_counts": dict(sorted(Counter(primary).items())),
        "repeatability": repeatability,
        "comparisons": comparisons,
    }


def check_handoffs(spans, score, receipt):
    trace_id = receipt["trace_id"]
    require(
        score["trace_id"] == score["correlation_id"] == trace_id
        and score["question"] == receipt["question"],
        f"Wrong score linkage: {trace_id}",
    )
    for stage, sender in HANDOFF_MESSAGES.items():
        span = spans[stage]
        message = score["messages"][sender]
        fields = ("topic", "partition", "offset", "enqueue_time", "receive_time", "ack_time")
        require(
            message["payload"]["correlation_id"] == trace_id
            and all(message[field] == span[field] for field in fields),
            f"Wrong {stage} linkage: {trace_id}",
        )
    require(
        score["evaluation_id"] == spans["evaluation"]["evaluation_id"],
        f"Wrong evaluation linkage: {trace_id}",
    )


def distribution(samples):
    return {
        "p50_ms": statistics.median(samples),
        "p95_ms": statistics.quantiles(samples, n=20, method="inclusive")[-1],
    }


def verify_benchmark(saved, judge_settings):
    root = RAW / "benchmark"
    measured_rows = csv_rows(root / "latency_rows.csv")
    by_trace = indexed(measured_rows, "trace_id")
    attempts = indexed(json_rows(root / "attempts.jsonl"), "case_id")
    excluded = indexed(json_rows(root / "exclusions.jsonl"), "case_id")
    examples = document(root / "examples.json")
    example_ids = {key: examples[key] for key in ("hit", "miss", "failure")}
    require(
        len(by_trace) == saved["admitted_count"] == saved["target_count"] == 50
        and saved["complete"]
        and saved["synthetic"] is False
        and not saved["pilot_only"]
        and saved["cache_threshold"] == 0.85
        and saved["version_enforced"] is True,
        "Expected the complete 50-miss experiment",
    )
    require(
        len(excluded) == saved["exclusion_count"] == 7
        and len(attempts) == len(excluded) + len(by_trace)
        and {r["case_id"] for r in measured_rows}.isdisjoint(excluded)
        and {r["case_id"] for r in measured_rows} | set(excluded) == set(attempts)
        and {row["trace_id"] for row in excluded.values()}.isdisjoint(by_trace),
        "Attempt accounting differs",
    )
    spans = group_spans(json_rows(root / "spans.jsonl"))
    scores = indexed(json_rows(root / "pipeline_scores.jsonl"), "trace_id")
    require(
        len(set(example_ids.values())) == 3
        and not set(example_ids.values()) & set(by_trace)
        and set(spans) == set(by_trace) | set(example_ids.values())
        and set(scores) == set(by_trace) | {example_ids["miss"]},
        "Wrong measured or example trace membership",
    )

    values = defaultdict(list)
    intervals = []
    questions = set()
    for trace_id, recorded in by_trace.items():
        receipt = attempts[recorded["case_id"]]
        raw_spans = spans[trace_id]
        score = scores[trace_id]
        stages = indexed(raw_spans, "stage")
        api, evaluation = stages["api_request"], stages["evaluation"]
        require(
            trace_id == receipt["trace_id"]
            and api["http_status"] == 200
            and api["request_outcome"] == "success"
            and all(
                s["source_commit"] == saved["measured_source_sha"]
                and s["correlation_id"] == trace_id
                for s in raw_spans
                if s["stage"] != "evaluation"
            )
            and score["case_id"] == receipt["case_id"]
            and score["judge"] == judge_settings,
            f"Wrong receipt/source: {trace_id}",
        )
        check_handoffs(stages, score, receipt)
        computed = timing_row(Attempt(**receipt), raw_spans)
        require(recorded.keys() == computed.keys(), f"Wrong timing columns: {trace_id}")
        for key in computed.keys() - {"case_id", "trace_id"}:
            same_number(recorded[key], computed[key], f"{trace_id} {key}")
            values[key].append(computed[key])
        intervals.append((timestamp(api["start_time"]), timestamp(evaluation["end_time"])))
        questions.add(receipt["question"])
    intervals.sort()
    require(len(questions) == 50, "Expected 50 distinct benchmark questions")
    require(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), "Overlapping trials")

    total = math.fsum(values["full_trace_ms"])
    summary = {"stages": []}
    same_number(saved["full_trace_total_ms"], total, "total full-trace ms")
    for stage, entry in zip(STAGES, saved["stages"], strict=True):
        samples = values[f"{stage}_ms"]
        expected = {
            **distribution(samples),
            "percent_of_full_trace": 100 * math.fsum(samples) / total,
        }
        require(entry["stage"] == stage, "Saved stage order differs")
        for key, value in expected.items():
            same_number(entry[key], value, f"{stage} {key}")
        summary["stages"].append({"stage": stage, **expected})
    for name, key in (
        ("api_latency", "api_latency_ms"),
        ("http_latency", "http_latency_ms"),
        ("full_trace", "full_trace_ms"),
    ):
        summary[name] = distribution(values[key])
        for stat, value in summary[name].items():
            same_number(saved[name][stat], value, f"{name} {stat}")
    shares = math.fsum(row["percent_of_full_trace"] for row in summary["stages"])
    same_number(saved["stage_share_total_percent"], shares, "sum of stage shares")
    same_number(saved["unallocated_or_overlapping_percent"], 100 - shares, "unallocated share")
    summary.update(
        confirmed_misses=len(by_trace),
        excluded_attempts=len(excluded),
        unallocated_percent=100 - shares,
    )

    receipts = document(root / "example_receipts.json")["http"]
    pairs = []
    for name in ("hit", "miss", "failed"):
        receipt = receipts[name]
        trace_id = example_ids["failure" if name == "failed" else name]
        require(receipt["trace_id"] == trace_id, f"Wrong {name} receipt")
        pairs.append((Attempt(**receipt), spans[trace_id]))
    checked = example_summary(*pairs)
    for name, page in checked.items():
        require(
            all(examples["details"][name][k] == v for k, v in page.items()), f"Wrong {name} details"
        )
    hit = indexed(spans[example_ids["hit"]], "stage")
    require(
        set(hit) == {"api_request", "cache_lookup"}
        and hit["cache_lookup"]["source_request_id"] == example_ids["miss"],
        "Hit example did not reuse the successful miss",
    )
    miss = example_ids["miss"]
    check_handoffs(indexed(spans[miss], "stage"), scores[miss], receipts["miss"])
    failed_writers = [s for s in spans[example_ids["failure"]] if s["stage"] == "writer"]
    require(
        [s["attempt"] for s in failed_writers] == [1, 2, 3]
        and all(s["error"] == checked["failed"]["error"] for s in failed_writers),
        "Writer failure did not show all three attempts",
    )
    return summary, example_ids, spans


def verify_dashboard(example_ids, spans, judge):
    from streamlit.testing.v1 import AppTest

    os.environ["HW10_EVIDENCE_ROOT"] = str(RAW)
    entry_point = ROOT / "scripts/hw10/dashboard.py"
    sys.path.insert(0, str(entry_point.parent))
    app = AppTest.from_file(str(entry_point), default_timeout=30).run()
    require(not app.exception and not app.warning, "Recorded Summary failed to load")
    metrics = {item.label: item.value for item in app.metric}
    require(
        [metrics[k] for k in ("Completed requests", "Cache hits", "Cache misses")]
        == ["53", "1", "52"],
        "Unexpected recorded Summary counts",
    )
    app.radio(key="page").set_value("Evaluation").run()
    require(not app.exception and not app.warning, "Recorded Evaluation failed to load")
    displayed = {item.label: item.value for item in app.metric}
    require(
        app.dataframe[0].value["Score / 5"].tolist() == [5, 4, 4]
        and displayed["Final − draft"] == "+0"
        and displayed["Spearman correlation"] == f"{judge['spearman']:.3f}"
        and displayed["Mean absolute difference"] == f"{judge['mean_absolute_difference']:.2f} pts"
        and displayed["Cases with score changes"] == "0 / 20 (0.0%)",
        "Unexpected recorded Evaluation scores",
    )
    app.radio(key="page").set_value("Trace Lookup").run()
    results = {}
    banners = {
        "hit": ("success", "Cache hit"),
        "miss": ("info", "Successful cache miss"),
        "failure": ("error", "Failed request"),
    }
    for name, trace_id in example_ids.items():
        app.text_input(key="trace_id").set_value(trace_id).run()
        kind, label = banners[name]
        require(not app.exception and not app.warning, f"Streamlit failed for {trace_id}")
        banner = next((item.value for item in getattr(app, kind) if label in item.value), "")
        require(banner, f"Missing {label} outcome")
        table = app.dataframe[0].value
        raw = sorted(spans[trace_id], key=lambda row: timestamp(row["start_time"]))
        require(len(table) == len(raw), f"Missing spans in Streamlit: {trace_id}")
        for displayed, row in zip(table.to_dict("records"), raw, strict=True):
            require(
                displayed["Stage"] == row["stage"]
                and displayed["Status"] == row["status"]
                and displayed["Cache"] == (row.get("cache_outcome") or "—")
                and displayed["Error"] == (row["error"] or "—"),
                f"Displayed span differs: {trace_id} {row['stage']}",
            )
            for column, field in (("Start (UTC)", "start_time"), ("End (UTC)", "end_time")):
                expected = timestamp(row[field]).isoformat(sep=" ", timespec="milliseconds")
                require(displayed[column] == expected.replace("+00:00", "Z"), column)
            same_number(displayed["Duration (ms)"], row["duration_ms"], "Streamlit duration")
        results[name] = {"trace_id": trace_id, "shown_spans": len(table), "outcome": label}
    return {"summary_metrics": metrics, "example_trace_lookup": results}


def verify_smoke(root, expected_source):
    tracing = root / "tracing"
    http = document(root / "smoke.json")
    spans = group_spans(json_rows(tracing / "spans.jsonl"))
    [linked] = json_rows(tracing / "linked_cases.jsonl")
    [score] = json_rows(root / "evaluation/pipeline_scores.jsonl")
    [judge_span] = json_rows(root / "evaluation/spans.jsonl")
    miss_id, hit_id = (http[name]["request_id"] for name in ("miss", "hit"))
    require(set(spans) == {miss_id, hit_id}, "Missing distinct live smoke traces")
    for trace_id, rows in spans.items():
        require(
            all(
                row["source_commit"] == expected_source
                and row["status"] == "ok"
                and row["error"] is None
                and row["correlation_id"] == trace_id
                for row in rows
            ),
            f"Unexpected runtime source or failing span: {trace_id}",
        )
    hit = indexed(spans[hit_id], "stage")
    miss = indexed([*spans[miss_id], judge_span], "stage")
    require(set(hit) == {"api_request", "cache_lookup"}, "Live hit did not stop at cache")
    require(
        http["hit"]["is_cached"] is True
        and hit["cache_lookup"]["source_request_id"] == miss_id
        and all(row["cache_outcome"] == "hit" for row in hit.values())
        and hit["api_request"]["http_status"] == miss["api_request"]["http_status"] == 200
        and len(miss) == 10
        and linked["trace_id"] == judge_span["trace_id"] == miss_id
        and http["hit"]["answer"]
        == http["miss"]["answer"]
        == score["final_answer"]
        == linked["final_answer"],
        "Unexpected live hit/miss or answer linkage",
    )
    check_handoffs(miss, score, {"trace_id": miss_id, "question": http["question"]})
    receipt = Attempt(
        linked["case_id"],
        http["question"],
        200,
        miss_id,
        http["miss"]["is_cached"],
        http["miss"]["latency_ms"],
        0.0,
    )
    computed = timing_row(receipt, list(miss.values()))
    return {
        "source_commit": expected_source,
        "question": http["question"],
        "miss": {
            "trace_id": miss_id,
            "is_cached": False,
            "spans": len(miss),
            "api_ms": computed["api_latency_ms"],
            "evaluation_ms": computed["evaluation_ms"],
        },
        "hit": {
            "trace_id": hit_id,
            "is_cached": True,
            "spans": len(hit),
            "api_ms": hit["api_request"]["duration_ms"],
        },
        "scores": {key: item["score"] for key, item in score["scores"].items()},
        "model_digest": score["judge"]["model_digest"],
        "evaluation_end_utc": judge_span["end_time"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="Write the verification JSON here"
    )
    parser.add_argument(
        "--smoke-evidence",
        type=Path,
        help="Directory containing fresh collect, export and evaluate outputs",
    )
    args = parser.parse_args()
    started = time.monotonic()
    study = document(RAW / "evaluation/judge_validation.json")
    benchmark = document(RAW / "benchmark/latency_summary.json")
    provenance = verify_provenance(study, benchmark)
    judge = verify_judge(study)
    timing, example_ids, spans = verify_benchmark(benchmark, study["judge"])
    dashboard = verify_dashboard(example_ids, spans, judge)
    live = (
        verify_smoke(args.smoke_evidence, provenance["verified_checkout"])
        if args.smoke_evidence
        else None
    )
    report = {
        "status": "passed",
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "provenance": provenance,
        "judge_validation": judge,
        "latency": timing,
        "streamlit": dashboard,
        "live_smoke": live,
    }
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        f"PASS 20 frozen cases, 60 scores, Spearman {judge['spearman']:.4f}, "
        f"mean absolute difference {judge['mean_absolute_difference']:.2f}"
    )
    print(f"PASS {timing['confirmed_misses']}/50 confirmed misses and six latency rows")
    print("PASS all three recorded trace IDs opened in Streamlit")
    if live:
        print(f"PASS live miss {live['miss']['trace_id']} and hit {live['hit']['trace_id']}")
    print(f"PASS combined verifier ({time.monotonic() - started:.2f}s)")


if __name__ == "__main__":
    main()
