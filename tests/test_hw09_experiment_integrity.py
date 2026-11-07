"""Negative controls for certifying the saved experiment, without live services."""

import hashlib
import json
import shutil
from pathlib import Path

import httpx
import pytest

from scripts.hw09 import analyze_cache_experiments as analysis
from scripts.hw09.cache_experiments import request, unambiguous_units

EVIDENCE = Path(__file__).resolve().parents[1] / "reports/hw09/raw/part3"


@pytest.fixture
def bundle(tmp_path):
    shutil.copytree(EVIDENCE, tmp_path / "bundle")
    return tmp_path / "bundle"


def edit_json(path, transform):
    value = json.loads(path.read_text())
    transform(value)
    path.write_text(json.dumps(value))


def test_saved_successful_run_verifies_offline(bundle):
    _, rows, summaries, _, _ = analysis.verify(bundle)
    assert len(rows) == 200
    assert [s["total_cost"] for s in summaries] == [6310, 5130, 3950, 4555, 4555]


@pytest.mark.parametrize(
    "field,value", [("question", "changed"), ("expected", {}), ("should_hit", False)]
)
def test_changed_frozen_case_is_rejected(bundle, field, value):
    path = bundle / "scored-requests.jsonl"
    rows = analysis.read_rows(path)
    rows[0][field] = value
    path.write_text("\n".join(json.dumps(r) for r in rows))
    with pytest.raises(AssertionError):
        analysis.verify(bundle)


def test_swapping_categories_is_rejected_even_with_same_totals(bundle):
    path = bundle / "scored-requests.jsonl"
    rows = analysis.read_rows(path)
    rows[0]["category"], rows[10]["category"] = (
        rows[10]["category"],
        rows[0]["category"],
    )
    path.write_text("\n".join(json.dumps(r) for r in rows))
    with pytest.raises(AssertionError):
        analysis.verify(bundle)


def test_cache_event_from_another_request_is_rejected(bundle):
    path = bundle / "scored-requests.jsonl"
    rows = analysis.read_rows(path)
    rows[0]["cache_event"]["request_id"] = rows[1]["response"]["request_id"]
    path.write_text("\n".join(json.dumps(r) for r in rows))
    with pytest.raises(AssertionError):
        analysis.verify(bundle)


def test_partial_chosen_smoke_is_rejected(bundle):
    path = bundle / "chosen-smoke.jsonl"
    path.write_text(path.read_text().splitlines()[0] + "\n")
    with pytest.raises(AssertionError):
        analysis.verify(bundle)


def test_hit_source_from_another_pass_is_rejected(bundle):
    path = bundle / "scored-requests.jsonl"
    rows = analysis.read_rows(path)
    foreign = next(r for r in rows if r["threshold"] == 0.9 and r["case_id"] == "P02")
    target = next(r for r in rows if r["threshold"] == 0.95 and r["case_id"] == "P04")
    foreign_id = foreign["response"]["request_id"]
    target["cache_event"]["matched_request_id"] = foreign_id
    path.write_text("\n".join(json.dumps(r) for r in rows))
    log = bundle / "api-c-sweep-095-01-enforced.log"
    lines = log.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("{"):
            event = json.loads(line)
            if (
                event.get("event") == "semantic_cache_result"
                and event["request_id"] == target["response"]["request_id"]
            ):
                event["matched_request_id"] = foreign_id
                lines[i] = json.dumps(event)
    log.write_text("\n".join(lines))
    with pytest.raises(AssertionError):
        analysis.verify(bundle)


def test_negated_or_conflicting_counts_are_not_demo_success():
    answer = "For S6102-R-9199, 1 is incorrect; there are 3 available units."
    assert not unambiguous_units(answer, 1)
    assert not unambiguous_units(answer, 3)
    assert unambiguous_units("At S6102-R-9199, there is 1 unit available.", 1)


def test_contradictory_stale_answer_is_rejected_after_rebinding_audit_hash(bundle):
    answer = "For S6102-R-9199, 1 is incorrect; there are 3 available units."
    edit_json(
        bundle / "stale-trace.json",
        lambda rows: rows[2]["response"].update(answer=answer),
    )
    request_id = json.loads((bundle / "stale-trace.json").read_text())[2]["response"][
        "request_id"
    ]

    def rebind(audit):
        next(d for d in audit["decisions"] if d["request_id"] == request_id)[
            "answer_sha256"
        ] = hashlib.sha256(answer.encode()).hexdigest()

    edit_json(bundle / "demonstration-audit.json", rebind)
    with pytest.raises(AssertionError):
        analysis.verify(bundle)


@pytest.mark.parametrize("failure", ["timeout", "non_json"])
def test_failed_http_attempt_is_retained_once_without_retry(tmp_path, failure):
    def transport(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("controlled timeout", request=request)
        return httpx.Response(502, text="controlled gateway failure")

    path = tmp_path / "attempts.jsonl"
    with httpx.Client(
        base_url="http://offline.test", transport=httpx.MockTransport(transport)
    ) as client:
        with pytest.raises((httpx.HTTPError, ValueError)):
            request(client, "controlled question", path)
    rows = analysis.read_rows(path)
    assert len(rows) == 1
    assert rows[0]["question"] == "controlled question"
    assert rows[0]["error"]
    assert rows[0]["http_latency_ms"] >= 0


def test_manifest_remains_valid_after_regeneration(tmp_path):
    (tmp_path / "result.txt").write_text("captured evidence")
    analysis.write_manifest(tmp_path)
    analysis.write_manifest(tmp_path)
    manifest = json.loads((tmp_path / "evidence-sha256.json").read_text())
    assert set(manifest) == {"result.txt"}
    assert manifest["result.txt"] == hashlib.sha256(b"captured evidence").hexdigest()
