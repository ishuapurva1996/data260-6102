import csv
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from scripts.hw10 import benchmark
from scripts.hw10.benchmark import Attempt, Case, cache_reset, collect, login, question_cases
from scripts.hw10.benchmark_timing import EvidenceError, example_summary, timing_row, timing_summary

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
QUESTION = "How many units are available at S6102-R-9101?"


def span(trace_id, stage, start, end, **fields):
    return {
        "trace_id": trace_id,
        "stage": stage,
        "start_time": (EPOCH + timedelta(milliseconds=start)).isoformat(),
        "end_time": (EPOCH + timedelta(milliseconds=end)).isoformat(),
        "duration_ms": end - start,
        "status": "ok",
        "error": None,
        **fields,
    }


def utc_ms(value):
    return (EPOCH + timedelta(milliseconds=value)).isoformat()


def trace(trace_id="trace-1", waits=(2, 8, 1, 9), judge=30):
    spans = [
        span(trace_id, "api_request", 0, 100, cache_outcome="miss"),
        span(trace_id, "cache_lookup", 1, 11, cache_outcome="miss"),
    ]
    cursor = 12
    for offset, (stage, wait, agent) in enumerate(
        zip(("inbox", "tasks", "drafts", "final"), waits, ("planner", "writer", "reviewer", None))
    ):
        spans.append(
            span(
                trace_id,
                stage,
                cursor,
                cursor + wait,
                topic=f"s6102_{stage}",
                partition=0,
                offset=offset,
                attempt=1,
                operation="queue_wait",
                enqueue_time=utc_ms(cursor),
                receive_time=utc_ms(cursor + wait),
                ack_time=utc_ms(cursor + wait + 1),
            )
        )
        cursor += wait
        if agent:
            spans.append(span(trace_id, agent, cursor, cursor + 15, attempt=1))
            cursor += 15
    spans.append(span(trace_id, "evaluation", 105, 105 + judge))
    return spans


def attempt(trace_id="trace-1", *, is_cached=False):
    return Attempt(
        case_id="test-case",
        question=QUESTION,
        status_code=200,
        trace_id=trace_id,
        is_cached=is_cached,
        api_latency_ms=100,
        http_latency_ms=101,
    )


def test_sums_waits_per_trace_and_uses_ingress_to_evaluation_for_share():
    first = trace(waits=(2, 8, 1, 9), judge=30)
    second = trace("trace-2", waits=(8, 2, 9, 1), judge=45)
    rows = [
        timing_row(attempt(), first + [first[2].copy()]),
        timing_row(attempt("trace-2"), second),
    ]
    assert rows[0]["queue_wait_ms"] == 20
    assert rows[0]["api_latency_ms"] == 100
    assert rows[0]["http_latency_ms"] == 101
    assert rows[0]["full_trace_ms"] == 135
    summary = timing_summary(rows)
    assert [stage["stage"] for stage in summary["stages"]] == [
        "cache_lookup",
        "planner",
        "writer",
        "reviewer",
        "queue_wait",
        "evaluation",
    ]
    queue = summary["stages"][4]
    assert queue["p50_ms"] == queue["p95_ms"] == 20
    assert queue["percent_of_full_trace"] == pytest.approx(100 * 40 / 285)
    assert summary["stages"][5]["p95_ms"] == pytest.approx(44.25)
    assert summary["dominant_stage"] == "evaluation"
    assert summary["api_latency"]["p95_ms"] == 100


@pytest.mark.parametrize(
    ("stage", "change", "message"),
    [
        ("cache_lookup", {"cache_outcome": "hit"}, "cache_lookup"),
        ("cache_lookup", {"status": "error"}, "cache_lookup"),
        ("api_request", {"cache_outcome": "hit"}, "api_request"),
        ("planner", None, "planner"),
        ("writer", {"status": "error", "error": "writer failure"}, "writer"),
        ("reviewer", None, "reviewer"),
        ("drafts", {"offset": None}, "drafts"),
        ("final", {"topic": "s6102_tasks"}, "final"),
        ("final", {"receive_time": utc_ms(99)}, "final"),
        ("final", {"ack_time": None}, "final"),
        ("final", None, "final"),
        ("evaluation", {"status": "error"}, "evaluation"),
        ("evaluation", {"trace_id": "another"}, "evaluation"),
    ],
)
def test_rejects_incomplete_or_mismatched_path(stage, change, message):
    spans = trace()
    target = next(item for item in spans if item["stage"] == stage)
    if change is None:
        spans.remove(target)
    else:
        target.update(change)
    with pytest.raises(EvidenceError, match=message):
        timing_row(attempt(), spans)


@pytest.mark.parametrize("is_cached", [True, None, 0])
def test_requires_explicit_false_in_api_response(is_cached):
    with pytest.raises(EvidenceError, match="is_cached"):
        timing_row(attempt(is_cached=is_cached), trace())


def test_conflicting_receipt_is_rejected():
    spans = trace()
    spans.append({**spans[2], "end_time": spans[2]["start_time"]})
    with pytest.raises(EvidenceError, match="inbox"):
        timing_row(attempt(), spans)


def test_examples_keep_distinct_hit_miss_and_writer_failure():
    hit = attempt("hit", is_cached=True)
    hit_spans = [
        span("hit", "api_request", 0, 12, cache_outcome="hit"),
        span("hit", "cache_lookup", 1, 11, cache_outcome="hit"),
    ]
    miss = attempt("miss")
    failure = replace(attempt("failure", is_cached=None), status_code=504)
    failure_spans = [
        span(
            "failure", "api_request", 0, 100, status="error", cache_outcome="miss", error="Timeout"
        ),
        span("failure", "cache_lookup", 1, 11, cache_outcome="miss"),
        span("failure", "writer", 20, 35, status="error", error="Controlled Writer failure"),
    ]
    result = example_summary((hit, hit_spans), (miss, trace("miss")), (failure, failure_spans))
    assert [result[key]["trace_id"] for key in ("hit", "miss", "failed")] == [
        "hit",
        "miss",
        "failure",
    ]
    assert result["hit"]["api_latency_ms"] == 12
    assert result["failed"]["error"] == "Controlled Writer failure"
    with pytest.raises(EvidenceError, match="recorded Writer failure"):
        example_summary((hit, hit_spans), (miss, trace("miss")), (failure, failure_spans[:2]))


def test_questions_use_approved_facts():
    cases = question_cases()
    assert len(cases) == len({case.question for case in cases}) == 50
    assert {case.listing_code for case in cases} == {f"S6102-R-{i}" for i in range(9101, 9111)}
    assert all(case.listing_code in case.question for case in cases)


def test_serial_authenticated_collection_replaces_exclusions(tmp_path, monkeypatch):
    monkeypatch.setenv("HW7_MODERATOR_USERNAME", "fixture-user")
    monkeypatch.setenv("HW7_MODERATOR_PASSWORD", "fixture-password")
    operations = []
    outcomes = iter([("pilot", False), ("hit", True), ("no-score", False), ("measured", False)])

    def respond(request):
        if request.url.path == "/auth/login":
            assert json.loads(request.content) == {
                "username": "fixture-user",
                "password": "fixture-password",
            }
            return httpx.Response(200, json={"access_token": "fixture-token"})
        assert request.headers["Authorization"] == "Bearer fixture-token"
        assert request.method == "POST" and request.url.path == "/api/kafka/questions"
        assert json.loads(request.content) == {"question": QUESTION}
        trace_id, cached = next(outcomes)
        operations.append(("http", trace_id))
        return httpx.Response(
            200, json={"request_id": trace_id, "is_cached": cached, "latency_ms": 100}
        )

    def capture(receipt, _directory):
        operations.append(("capture", receipt.trace_id))
        if receipt.is_cached:
            return [
                span(receipt.trace_id, "api_request", 0, 100, cache_outcome="hit"),
                span(receipt.trace_id, "cache_lookup", 1, 11, cache_outcome="hit"),
            ]
        return trace(receipt.trace_id)[:-1]

    def evaluate(receipt, _directory):
        operations.append(("evaluate", receipt.trace_id))
        return [] if receipt.trace_id == "no-score" else [trace(receipt.trace_id)[-1]]

    with httpx.Client(
        base_url="http://127.0.0.1:8702", transport=httpx.MockTransport(respond)
    ) as client:
        login(client)
        summary = collect(
            client,
            [Case("S6102-R-9101", QUESTION)],
            tmp_path,
            target=1,
            max_attempts=3,
            reset_cache=lambda previous: operations.append(("reset", previous)),
            capture=capture,
            evaluate=evaluate,
            provenance={"synthetic": True},
        )

    assert operations == [
        ("reset", None),
        ("http", "pilot"),
        ("capture", "pilot"),
        ("evaluate", "pilot"),
        ("reset", "pilot"),
        ("http", "hit"),
        ("capture", "hit"),
        ("reset", "hit"),
        ("http", "no-score"),
        ("capture", "no-score"),
        ("evaluate", "no-score"),
        ("reset", "no-score"),
        ("http", "measured"),
        ("capture", "measured"),
        ("evaluate", "measured"),
    ]
    with (tmp_path / "latency_rows.csv").open() as raw:
        assert [row["trace_id"] for row in csv.DictReader(raw)] == ["measured"]
    assert summary["admitted_count"] == 1
    assert summary["exclusion_count"] == 3
    exclusions = [
        json.loads(line) for line in (tmp_path / "exclusions.jsonl").read_text().splitlines()
    ]
    assert [(row["trace_id"], row["reason"]) for row in exclusions] == [
        ("pilot", "pilot"),
        ("hit", "API response is_cached must be false"),
        ("no-score", "expected one evaluation span, found 0"),
    ]
    assert {
        json.loads(line)["trace_id"] for line in (tmp_path / "spans.jsonl").read_text().splitlines()
    } == {"measured"}


def test_cache_reset_cannot_delete_an_unexpected_entry():
    prefix = "s6102:hw9:semantic:hw10-benchmark-test:entry:"
    outside = b"s6102:hw9:semantic:other:entry:do-not-delete"
    entries = {outside}

    class Redis:
        def scan_iter(self, match):
            return (key for key in entries if key.startswith(match[:-1].encode()))

        def execute_command(self, *args):
            assert args == ("FT.SEARCH", "owned-index", "*", "LIMIT", 0, 0)
            return [sum(key.startswith(prefix.encode()) for key in entries)]

        def delete(self, *keys):
            entries.difference_update(keys)

    cache = SimpleNamespace(
        entry_prefix=prefix,
        index="owned-index",
        redis=Redis(),
        settings=SimpleNamespace(
            namespace="hw10-benchmark-test", threshold=0.85, allow_stale=False
        ),
    )
    reset = cache_reset(cache)
    entries.add((prefix + "last-trace").encode())
    reset("last-trace")
    assert entries == {outside}
    unexpected = (prefix + "unknown").encode()
    entries.add(unexpected)
    with pytest.raises(EvidenceError, match="unexpected key"):
        reset("last-trace")
    assert entries == {outside, unexpected}


def test_evaluator_command_reads_the_same_trace_and_case(tmp_path, monkeypatch):
    def run(module, args, _log, timeout):
        assert module == "scripts.hw10.evaluate"
        assert args == [
            "pipeline",
            "--evidence-root",
            str(tmp_path),
            "--trace-id",
            "trace-1",
            "--model",
            "judge:test",
            "--model-digest",
            "test-digest",
        ]
        assert timeout > 0
        output = tmp_path / "evaluation"
        output.mkdir(exist_ok=True)
        benchmark.jsonl(
            output / "spans.jsonl",
            [{**trace()[-1], "evaluation_id": "eval-1"}],
        )
        benchmark.jsonl(
            output / "pipeline_scores.jsonl",
            [{"trace_id": "trace-1", "case_id": "test-case", "evaluation_id": "eval-1"}],
        )
        return 0

    monkeypatch.setattr(benchmark, "run_command", run)
    [result] = benchmark.evaluate_trace(attempt(), tmp_path, "judge:test", "test-digest")
    assert result["evaluation_id"] == "eval-1"
    with pytest.raises(EvidenceError, match="linked score and span"):
        benchmark.evaluate_trace(attempt(), tmp_path, "judge:test", "test-digest")
