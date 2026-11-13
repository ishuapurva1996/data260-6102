"""Score one HW10 pipeline trace or run the frozen judge validation study."""

import argparse
import math
import os
import time
from pathlib import Path
from uuid import uuid4

from .evaluation_evidence import (
    EvaluationError,
    append_row,
    canonical_json,
    case_deadline,
    load_linked_case,
    nonempty_text,
    utc_now,
)
from .evaluation_judge import MODEL, OLLAMA_URL, LocalJudge, score_metric
from .evaluation_validation import validate_judge


def interpret(draft, final, delta, scores):
    direction = (
        f"The final scored {delta:+d} points versus the draft."
        if delta
        else "Both scores are equal."
    )
    if draft == final:
        variation = " The score changed across judge calls on identical text." if delta else ""
        return f"{direction} The Reviewer kept the draft verbatim.{variation}"
    draft_words, final_words = draft.split(), final.split()
    if draft_words == final_words:
        return f"{direction} The Reviewer changed only whitespace."
    start = 0
    while (
        start < min(len(draft_words), len(final_words)) and draft_words[start] == final_words[start]
    ):
        start += 1
    draft_end, final_end = len(draft_words), len(final_words)
    while (
        draft_end > start
        and final_end > start
        and draft_words[draft_end - 1] == final_words[final_end - 1]
    ):
        draft_end -= 1
        final_end -= 1

    def excerpt(words, end):
        text = " ".join(words[start : min(end, start + 12)])
        return repr(text + ("…" if end - start > 12 else ""))

    reasons = []
    for stage in ("writer", "reviewer"):
        reason = " ".join(scores[stage]["reason"].split())
        reasons.append(repr(reason if len(reason) <= 180 else reason[:177] + "…"))
    return (
        f"{direction} The changed excerpt went from {excerpt(draft_words, draft_end)} to "
        f"{excerpt(final_words, final_end)}. The judge described the draft as {reasons[0]} "
        f"and the final as {reasons[1]}."
    )


def run_pipeline(args, judge_factory, output):
    evaluation_id = str(uuid4())
    start_time, started = utc_now(), time.monotonic()
    trace_id, case_id = args.trace_id, args.case_id
    selector, identity = ("trace_id", trace_id) if trace_id is not None else ("case_id", case_id)
    error_code = error = None
    stage = None
    try:
        with case_deadline(args.case_timeout):
            case = load_linked_case(
                args.evidence_root / "tracing" / "linked_cases.jsonl",
                selector,
                identity,
                args.link_timeout,
            )
            trace_id, case_id = case["trace_id"], case["case_id"]
            judge = judge_factory(args)
            scores = {}
            for stage, criterion, field in (
                ("planner", "plan_quality", "plan"),
                ("writer", "helpfulness", "draft"),
                ("reviewer", "helpfulness", "final_answer"),
            ):
                scores[stage] = score_metric(
                    judge, criterion, case["question"], case["reference_facts"], case[field]
                )
            delta = scores["reviewer"]["score"] - scores["writer"]["score"]
            result = {
                **case,
                "final": case["final_answer"],
                "evaluation_id": evaluation_id,
                "scores": scores,
                "final_minus_draft": delta,
                "interpretation": interpret(case["draft"], case["final_answer"], delta, scores),
                "judge": judge.metadata,
            }
    except EvaluationError as exc:
        if trace_id is None and nonempty_text(exc.trace_id):
            trace_id = exc.trace_id
        error_code, error = exc.code, str(exc)

    span = {
        "evaluation_id": evaluation_id,
        "trace_id": trace_id,
        "case_id": case_id,
        "stage": "evaluation",
        "start_time": start_time,
        "end_time": utc_now(),
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
        "status": "error" if error_code else "ok",
        "error": error,
        "error_code": error_code,
    }
    if error_code:
        append_row(
            output / "pipeline_failures.jsonl",
            {
                **span,
                "failed_metric": stage,
            },
        )
    else:
        append_row(output / "pipeline_scores.jsonl", result)
    if trace_id is not None:
        append_row(output / "spans.jsonl", span)
    return span


def positive_seconds(value):
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected seconds") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("Seconds must be positive and finite")
    return seconds


def main(argv=None, *, judge_factory=LocalJudge):
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    pipeline = subcommands.add_parser("pipeline", help="Score one linked trace")
    validate = subcommands.add_parser("validate", help="Score the 20 frozen drafts in three passes")
    for command in (pipeline, validate):
        command.add_argument("--evidence-root", type=Path, default=Path("reports/hw10/raw"))
        command.add_argument("--output-dir", type=Path)
        command.add_argument("--model", default=MODEL)
        command.add_argument("--model-digest")
        command.add_argument("--ollama-url", default=os.getenv("OLLAMA_BASE_URL", OLLAMA_URL))
        command.add_argument("--request-timeout", type=positive_seconds, default=45.0)
        command.add_argument("--case-timeout", type=positive_seconds, default=180.0)
    pipeline.add_argument("--link-timeout", type=positive_seconds, default=5.0)
    identity = pipeline.add_mutually_exclusive_group(required=True)
    identity.add_argument("--trace-id")
    identity.add_argument("--case-id")
    for arg in ("tracing-sha", "freeze-sha", "cases-sha256", "labels-sha256"):
        validate.add_argument(f"--{arg}", required=True)
    args = parser.parse_args(argv)
    output = args.output_dir or args.evidence_root / "evaluation"
    try:
        output.mkdir(parents=True, exist_ok=True)
        if args.command == "pipeline":
            result = run_pipeline(args, judge_factory, output)
        else:
            summary = validate_judge(args, judge_factory, output)
            result = {key: summary[key] for key in ("study_id", "status", "scored_count")}
    except (EvaluationError, OSError) as exc:
        result = {
            "status": "error",
            "error_code": getattr(exc, "code", "output_error"),
            "error": str(exc),
        }
    print(canonical_json(result))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
