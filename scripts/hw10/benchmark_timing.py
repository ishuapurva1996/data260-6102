"""Validate complete HW10 traces and compute the six benchmark timing rows."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.kafka_service.config import DRAFTS, FINAL, INBOX, TASKS

QUEUE_TOPICS = {"inbox": INBOX, "tasks": TASKS, "drafts": DRAFTS, "final": FINAL}
STAGES = ("cache_lookup", "planner", "writer", "reviewer", "queue_wait", "evaluation")
PATH = ("cache_lookup", "inbox", "planner", "tasks", "writer", "drafts", "reviewer", "final")


class EvidenceError(ValueError):
    """The evidence is insufficient to include the trace in the benchmark."""


@dataclass(frozen=True)
class Attempt:
    case_id: str
    question: str
    status_code: int | None
    trace_id: str | None
    is_cached: bool | None
    api_latency_ms: float | None
    http_latency_ms: float
    error: str | None = None


def unique_spans(spans):
    result = []
    for span in spans:
        if span not in result:
            result.append(span)
    return result


def one_span(spans, stage):
    matches = [span for span in spans if span.get("stage") == stage]
    if len(matches) != 1:
        raise EvidenceError(f"expected one {stage} span, found {len(matches)}")
    return matches[0]


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("expected a UTC timestamp")
    return parsed.astimezone(UTC)


def duration(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("expected a finite nonnegative duration")
    return value


def completed_span(spans, stage):
    span = one_span(spans, stage)
    if span.get("status") != "ok" or "error" not in span or span["error"] is not None:
        raise EvidenceError(f"{stage} did not complete successfully")
    try:
        start, end = timestamp(span["start_time"]), timestamp(span["end_time"])
        elapsed = duration(span["duration_ms"])
        if end < start:
            raise ValueError("negative wall-clock interval")
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError(f"invalid {stage} timing") from exc
    return span, start, end, elapsed


def queue_interval(span, start, end):
    stage = span["stage"]
    try:
        if (
            span.get("operation") != "queue_wait"
            or span.get("topic") != QUEUE_TOPICS[stage]
            or any(
                type(span.get(field)) is not int or span[field] < 0
                for field in ("partition", "offset")
            )
            or timestamp(span["enqueue_time"]) != start
            or timestamp(span["receive_time"]) != end
            or timestamp(span["ack_time"]) < start
        ):
            raise ValueError("inconsistent handoff")
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError(f"{stage} has no matched Kafka enqueue and receipt") from exc
    # The acknowledgement confirms publication and may follow the receipt.
    return (end - start).total_seconds() * 1000


def timing_row(attempt, spans):
    if attempt.status_code != 200 or attempt.error or not attempt.trace_id:
        raise EvidenceError("missing successful HTTP response with request_id")
    if attempt.is_cached is not False:
        raise EvidenceError("API response is_cached must be false")
    spans = unique_spans(span for span in spans if span.get("trace_id") == attempt.trace_id)
    api, ingress, response_end, api_latency_ms = completed_span(spans, "api_request")
    if api.get("cache_outcome") != "miss":
        raise EvidenceError("api_request did not record a miss")
    try:
        duration(attempt.api_latency_ms)
    except ValueError as exc:
        raise EvidenceError("missing valid API response latency_ms") from exc

    row = {
        "trace_id": attempt.trace_id,
        "case_id": attempt.case_id,
        "api_latency_ms": api_latency_ms,
        "response_latency_ms": attempt.api_latency_ms,
        "http_latency_ms": attempt.http_latency_ms,
    }
    waits = []
    prior_end = ingress
    for stage in PATH:
        span, start, end, elapsed = completed_span(spans, stage)
        if not prior_end <= start <= end <= response_end:
            raise EvidenceError(f"{stage} falls outside its ordered API path")
        prior_end = end
        if stage == "cache_lookup" and span.get("cache_outcome") != "miss":
            raise EvidenceError("cache_lookup did not record a miss")
        if stage in QUEUE_TOPICS:
            waits.append(queue_interval(span, start, end))
        else:
            row[f"{stage}_ms"] = elapsed

    _, evaluation_start, evaluation_end, evaluation_ms = completed_span(spans, "evaluation")
    if evaluation_start < response_end:
        raise EvidenceError("evaluation began before API completion")
    full_trace_ms = (evaluation_end - ingress).total_seconds() * 1000
    if full_trace_ms <= 0:
        raise EvidenceError("full-trace duration must be positive")
    return {
        **row,
        "queue_wait_ms": math.fsum(waits),
        "evaluation_ms": evaluation_ms,
        "full_trace_ms": full_trace_ms,
    }


def example_summary(hit, miss, failed):
    """Validate three independently captured (HTTP receipt, spans) pairs."""
    hit_attempt, hit_spans = hit
    miss_attempt, miss_spans = miss
    failed_attempt, failed_spans = failed
    trace_ids = {item.trace_id for item in (hit_attempt, miss_attempt, failed_attempt)}
    if None in trace_ids or len(trace_ids) != 3:
        raise EvidenceError("examples require three distinct request trace IDs")
    hit_spans = unique_spans(
        span for span in hit_spans if span.get("trace_id") == hit_attempt.trace_id
    )
    hit_api, _, _, hit_ms = completed_span(hit_spans, "api_request")
    hit_cache, _, _, _ = completed_span(hit_spans, "cache_lookup")
    if (
        hit_attempt.status_code != 200
        or hit_attempt.is_cached is not True
        or hit_api.get("cache_outcome") != "hit"
        or hit_cache.get("cache_outcome") != "hit"
        or any(span["stage"] in PATH[1:] for span in hit_spans)
    ):
        raise EvidenceError("hit example did not short-circuit the agent path")
    miss_row = timing_row(miss_attempt, miss_spans)
    failed_spans = unique_spans(
        span for span in failed_spans if span.get("trace_id") == failed_attempt.trace_id
    )
    failed_api = one_span(failed_spans, "api_request")
    failed_cache, _, _, _ = completed_span(failed_spans, "cache_lookup")
    writers = [
        span
        for span in failed_spans
        if span.get("stage") == "writer" and span.get("status") == "error" and span.get("error")
    ]
    if (
        failed_attempt.status_code is None
        or failed_attempt.status_code < 400
        or failed_api.get("status") != "error"
        or failed_api.get("cache_outcome") != "miss"
        or failed_cache.get("cache_outcome") != "miss"
        or not writers
    ):
        raise EvidenceError("failed example requires an API error and a recorded Writer failure")
    writer = max(writers, key=lambda span: timestamp(span["end_time"]))
    return {
        "hit": {"trace_id": hit_attempt.trace_id, "api_latency_ms": hit_ms},
        "miss": {"trace_id": miss_attempt.trace_id, "api_latency_ms": miss_row["api_latency_ms"]},
        "failed": {
            "trace_id": failed_attempt.trace_id,
            "stage": "writer",
            "error": writer["error"],
            "http_status": failed_attempt.status_code,
        },
    }


def percentile(values, fraction):
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    lower = math.floor(rank)
    return ordered[lower] + (rank - lower) * (ordered[math.ceil(rank)] - ordered[lower])


def distribution(rows, key):
    values = [row[key] for row in rows]
    return {"p50_ms": percentile(values, 0.5), "p95_ms": percentile(values, 0.95)}


def timing_summary(rows):
    if len({row["trace_id"] for row in rows}) != len(rows):
        raise EvidenceError("duplicate trace IDs in timing rows")
    if not rows:
        raise EvidenceError("no admitted traces to summarize")

    total_ms = math.fsum(row["full_trace_ms"] for row in rows)
    stages = [
        {
            "stage": stage,
            **distribution(rows, f"{stage}_ms"),
            "percent_of_full_trace": (
                100 * math.fsum(row[f"{stage}_ms"] for row in rows) / total_ms
            ),
        }
        for stage in STAGES
    ]
    shares = math.fsum(row["percent_of_full_trace"] for row in stages)
    return {
        "stages": stages,
        "api_latency": distribution(rows, "api_latency_ms"),
        "http_latency": distribution(rows, "http_latency_ms"),
        "full_trace": distribution(rows, "full_trace_ms"),
        "full_trace_total_ms": total_ms,
        "stage_share_total_percent": shares,
        "unallocated_or_overlapping_percent": 100 - shares,
        "dominant_stage": max(stages, key=lambda row: row["percent_of_full_trace"])["stage"],
    }
