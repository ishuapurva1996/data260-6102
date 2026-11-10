"""Verify the input freeze and compare three fresh judge passes with human labels."""

import csv
import fcntl
import hashlib
import io
import os
import re
import subprocess
from math import sqrt
from pathlib import Path
from statistics import mean
from tempfile import NamedTemporaryFile
from uuid import uuid4

from .evaluation_evidence import (
    EvaluationError,
    append_row,
    canonical_json,
    case_deadline,
    json_value,
    nonempty_text,
    utc_now,
    valid_facts,
)
from .evaluation_judge import score_metric

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES = "reports/hw10/eval_cases.json"
LABELS = "reports/hw10/human_labels.csv"
CASE_COUNT = 20
PASS_COUNT = 3


def freeze_inputs(repo, tracing_sha, freeze_sha, cases_hash, labels_hash):
    def git(*args):
        try:
            return subprocess.run(
                ["git", "-C", str(repo), *args], check=True, capture_output=True, timeout=5
            ).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise EvaluationError(
                "invalid_freeze", f"Could not verify git {' '.join(args)}"
            ) from exc

    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (tracing_sha, freeze_sha)):
        raise EvaluationError("invalid_freeze", "A1 and A2 must be full commit SHAs")
    if tracing_sha == freeze_sha:
        raise EvaluationError("invalid_freeze", "A1 and A2 must be separate commits")
    git("merge-base", "--is-ancestor", tracing_sha, freeze_sha)
    git("merge-base", "--is-ancestor", freeze_sha, "HEAD")
    changed = git("diff", "--name-only", f"{freeze_sha}^", freeze_sha, "--", CASES, LABELS)
    if set(changed.decode("utf-8").splitlines()) != {CASES, LABELS}:
        raise EvaluationError("invalid_freeze", "A2 must commit both input files together")

    frozen = {}
    for path, checksum in ((CASES, cases_hash), (LABELS, labels_hash)):
        blob = git("show", f"{freeze_sha}:{path}")
        if hashlib.sha256(blob).hexdigest() != checksum:
            raise EvaluationError(
                "invalid_freeze", f"SHA-256 does not match the freeze receipt for {path}"
            )
        try:
            matches = (repo / path).read_bytes() == blob
        except OSError as exc:
            raise EvaluationError("invalid_freeze", f"Cannot read {path} in the checkout") from exc
        if not matches:
            raise EvaluationError("invalid_freeze", f"The checkout differs from A2 for {path}")
        frozen[path] = blob
    return parse_inputs(frozen[CASES], frozen[LABELS])


def parse_inputs(cases_blob, labels_blob):
    try:
        document = json_value(cases_blob)
        label_rows = csv.DictReader(
            io.StringIO(labels_blob.decode("utf-8-sig"), newline=""), strict=True
        )
        if not label_rows.fieldnames or not {"case_id", "helpfulness"} <= set(
            label_rows.fieldnames
        ):
            raise ValueError("human_labels.csv requires case_id and helpfulness columns")
        labels = {}
        for row in label_rows:
            identity, label = row["case_id"], row["helpfulness"]
            if (
                None in row
                or not nonempty_text(identity)
                or identity in labels
                or label not in {"1", "2", "3", "4", "5"}
            ):
                raise ValueError("Human labels require unique case IDs and integers from 1 to 5")
            labels[identity] = int(label)
    except (ValueError, csv.Error, RecursionError) as exc:
        raise EvaluationError("invalid_freeze", f"Invalid frozen inputs: {exc}") from exc

    cases = document.get("cases") if isinstance(document, dict) else document
    if not isinstance(cases, list) or len(cases) != CASE_COUNT:
        raise EvaluationError("invalid_freeze", f"Expected exactly {CASE_COUNT} original drafts")
    required_text = ("case_id", "trace_id", "question", "draft")
    for case in cases:
        if (
            not isinstance(case, dict)
            or not all(nonempty_text(case.get(field)) for field in required_text)
            or case.get("correlation_id", case["trace_id"]) != case["trace_id"]
            or not valid_facts(case.get("reference_facts"))
        ):
            raise EvaluationError("invalid_freeze", "Invalid frozen draft or reference facts")
    if (
        len({case["trace_id"] for case in cases}) != CASE_COUNT
        or set(labels) != {case["case_id"] for case in cases}
        or len(labels) != CASE_COUNT
    ):
        raise EvaluationError(
            "invalid_freeze", "Draft IDs, traces and human labels must match one-to-one"
        )
    return cases, labels


def average_ranks(values):
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(ordered)
    start = 0
    while start < len(ordered):
        stop = start + 1
        while stop < len(ordered) and ordered[stop][1] == ordered[start][1]:
            stop += 1
        for position, _ in ordered[start:stop]:
            ranks[position] = (start + 1 + stop) / 2
        start = stop
    return ranks


def spearman(first, second):
    x, y = average_ranks(first), average_ranks(second)
    x_mean, y_mean = mean(x), mean(y)
    x_centered = [rank - x_mean for rank in x]
    y_centered = [rank - y_mean for rank in y]
    divisor = sqrt(sum(rank**2 for rank in x_centered) * sum(rank**2 for rank in y_centered))
    if divisor == 0:
        return None
    return sum(a * b for a, b in zip(x_centered, y_centered)) / divisor


def compare_scores(labels, passes):
    if (
        not labels
        or len(passes) != PASS_COUNT
        or any(scores.keys() != labels.keys() for scores in passes)
    ):
        raise ValueError("Three complete passes must match the human labels by case_id")
    comparisons = []
    for identity, human in labels.items():
        scores = [result[identity] for result in passes]
        comparisons.append(
            {
                "case_id": identity,
                "human_score": human,
                "judge_scores": scores,
                "pass_1_absolute_difference": abs(scores[0] - human),
                "score_change": max(scores) - min(scores),
            }
        )
    changes = [row["score_change"] for row in comparisons]
    changed_count = sum(change > 0 for change in changes)
    return {
        "spearman": spearman(list(labels.values()), [passes[0][identity] for identity in labels]),
        "mean_absolute_difference": mean(row["pass_1_absolute_difference"] for row in comparisons),
        "repeatability": {
            "changed_count": changed_count,
            "changed_rate": changed_count / len(changes),
            "mean_score_change": mean(changes),
            "max_score_change": max(changes),
        },
        "comparisons": comparisons,
    }


def atomic_text(path, contents):
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as temporary:
        temp_path = Path(temporary.name)
        try:
            temporary.write(contents)
            temporary.close()
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)


def validate_judge(args, judge_factory, output):
    descriptor = os.open(output, os.O_RDONLY)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise EvaluationError(
                "output_busy", "A validation study is writing to this directory"
            ) from exc
        return run_study(args, judge_factory, output)
    finally:
        os.close(descriptor)


def run_study(args, judge_factory, output):
    cases, labels = freeze_inputs(
        REPO_ROOT, args.tracing_sha, args.freeze_sha, args.cases_sha256, args.labels_sha256
    )
    study_id = str(uuid4())
    started = utc_now()
    try:
        with case_deadline(args.case_timeout):
            judge = judge_factory(args)
    except EvaluationError as exc:
        append_row(
            output / "judge_failures.jsonl",
            {
                "study_id": study_id,
                "freeze_sha": args.freeze_sha,
                "status": "error",
                "error_code": exc.code,
                "error": str(exc),
                "recorded_at": utc_now(),
            },
        )
        raise

    raw_scores = []
    passes = []
    pass_scores = []
    for pass_number in range(1, PASS_COUNT + 1):
        run_id = str(uuid4())
        pass_start = utc_now()
        scores = {}
        for case in cases:
            identity = case["case_id"]
            row = {
                "study_id": study_id,
                "run_id": run_id,
                "pass": pass_number,
                "case_id": identity,
                "trace_id": case["trace_id"],
                "status": "ok",
            }
            try:
                with case_deadline(args.case_timeout):
                    score = score_metric(
                        judge,
                        "helpfulness",
                        case["question"],
                        case["reference_facts"],
                        case["draft"],
                    )
            except EvaluationError as exc:
                append_row(
                    output / "judge_failures.jsonl",
                    {
                        **row,
                        "status": "error",
                        "error_code": exc.code,
                        "error": str(exc),
                        "recorded_at": utc_now(),
                    },
                )
            else:
                scores[identity] = score["score"]
                raw_scores.append(
                    {**row, **score, "retry_errors": canonical_json(score["retry_errors"])}
                )
        pass_scores.append(scores)
        passes.append(
            {
                "pass": pass_number,
                "run_id": run_id,
                "start_time": pass_start,
                "end_time": utc_now(),
                "status": "ok" if len(scores) == CASE_COUNT else "incomplete",
                "scored_count": len(scores),
            }
        )

    complete = len(raw_scores) == CASE_COUNT * PASS_COUNT
    summary = {
        "study_id": study_id,
        "status": "ok" if complete else "incomplete",
        "start_time": started,
        "end_time": utc_now(),
        "case_count": CASE_COUNT,
        "scored_count": len(raw_scores),
        "freeze_sha": args.freeze_sha,
        "tracing_sha": args.tracing_sha,
        "input_sha256": {CASES: args.cases_sha256, LABELS: args.labels_sha256},
        "judge": judge.metadata,
        "passes": passes,
        "primary_pass": 1,
    }
    if complete:
        summary.update(compare_scores(labels, pass_scores))
    else:
        summary.update(spearman=None, mean_absolute_difference=None, repeatability=None)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "study_id",
            "run_id",
            "pass",
            "case_id",
            "trace_id",
            "status",
            "score",
            "normalized_score",
            "reason",
            "attempts",
            "retry_errors",
        ],
    )
    writer.writeheader()
    writer.writerows(raw_scores)
    atomic_text(output / "judge_scores.csv", buffer.getvalue())
    atomic_text(output / "judge_validation.json", canonical_json(summary) + "\n")
    return summary
