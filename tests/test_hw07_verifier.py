"""Offline evidence checks for the HW7 Parts 2/3 task verifier."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tool_agent import verification
from src.tool_agent.verification import verify_task


def rental(rental_id, *, manager_id=7):
    return {
        "id": rental_id,
        "listingTitle": f"Garden home {rental_id}",
        "propertyAddress": f"{rental_id} Garden Street",
        "propertyType": "apartment",
        "managerId": manager_id,
        "description": f"Public description for home {rental_id}.",
    }


def summary(row):
    return {key: value for key, value in row.items() if key != "description"}


def task(task_id):
    expected = [rental(11)] if task_id == "A" else [rental(11), rental(12)]
    if task_id == "B":
        expected = [summary(row) for row in expected]
    return {
        "id": task_id,
        "query": "Garden",
        "manager_id": 7 if task_id == "B" else None,
        "expected": {"rentals": expected, "count": 3 if task_id == "B" else None},
    }


def observation(name, inputs, data, *, call_id=None, ok=True):
    return {
        "call_id": call_id or f"{name}-{inputs}",
        "model_response_index": 2 if name == "get_rental" else 1,
        "name": name,
        "inputs": inputs,
        "result": {"ok": ok, "data": data, "error": None if ok else "Unavailable."},
    }


def search(rows=None, *, query="Garden"):
    rows = [rental(11), rental(12)] if rows is None else rows
    return observation(
        "search_rentals",
        {"query": query, "limit": 5},
        {
            "items": [summary(row) for row in rows],
            "returnedCount": len(rows),
            "limit": 5,
        },
    )


def detail(rental_id):
    return observation("get_rental", {"rental_id": rental_id}, rental(rental_id))


def count(*, manager_id=7, total=3):
    return observation(
        "count_rentals",
        {"manager_id": manager_id},
        {
            "managerId": manager_id,
            "managerName": "Fixture manager",
            "count": total,
        },
    )


def answer(task_id, *, example_id=11):
    rows = task(task_id)["expected"]["rentals"]
    if task_id == "B":
        rows = [row for row in rows if row["id"] == example_id]
    return {"rentals": rows, "count": 3 if task_id == "B" else None}


def trace(task_id):
    if task_id == "A":
        return [search(), detail(11)]
    if task_id == "B":
        return [count(), search()]
    return [search(), detail(11), detail(12)]


def check(task_id, payload=None, observations=None):
    payload = answer(task_id) if payload is None else payload
    observations = trace(task_id) if observations is None else observations
    return verify_task(task(task_id), json.dumps(payload), observations)


@pytest.mark.parametrize("task_id", ["A", "B", "C"])
def test_complete_task_has_no_unsupported_claims(task_id):
    result = check(task_id)
    assert result == {
        "passed": True,
        "failures": [],
        "unsupported_claims": [],
        "parsed": answer(task_id),
    }


@pytest.mark.parametrize("task_id", ["A", "C"])
def test_detail_proposed_before_search_observation_cannot_pass(task_id):
    observations = trace(task_id)
    for row in observations:
        row["model_response_index"] = 1
    result = check(task_id, observations=observations)
    assert not result["passed"] and "trace.chain" in result["failures"]
    assert result["unsupported_claims"] == []


@pytest.mark.parametrize("task_id", ["A", "C"])
def test_missing_response_provenance_cannot_prove_dependent_chain(task_id):
    observations = trace(task_id)
    observations[-1].pop("model_response_index")
    assert not check(task_id, observations=observations)["passed"]


@pytest.mark.parametrize(
    "payload,passed",
    [
        ('{"rental_id":2147483000,"found":false}', True),
        ('{"rental_id":2147483000,"found":false,"propertyType":"house"}', False),
        ("Rental 1 was not found, but rental 2147483000 is a house.", False),
        ('{"rental_id":1,"found":false}', False),
        ('{"rental_id":2147483000,"found":0}', False),
    ],
)
def test_missing_id_recovery_requires_observed_absence_without_invented_fields(payload, passed):
    missing_id = 2147483000
    observed = [
        {
            "name": "get_rental",
            "inputs": {"rental_id": missing_id},
            "result": {"ok": False, "data": None, "error": f"Rental {missing_id} was not found."},
        }
    ]
    result = verification.verify_missing_id(missing_id, payload, observed)
    assert result["passed"] is passed


def test_harmless_json_key_order_and_whitespace_are_accepted():
    payload = answer("A")
    text = (
        " \n"
        + json.dumps({"count": None, "rentals": payload["rentals"]}, sort_keys=True, indent=2)
        + "\n "
    )
    assert verify_task(task("A"), text, trace("A"))["passed"]


@pytest.mark.parametrize("example_id", [11, 12])
def test_b_accepts_either_frozen_search_example(example_id):
    assert check("B", answer("B", example_id=example_id))["passed"]


def test_b_accepts_example_from_a_later_supporting_search():
    observations = [count(), search([rental(11)]), search([rental(12)])]
    assert check("B", answer("B", example_id=12), observations)["passed"]


def test_c_details_can_be_obtained_in_either_order_after_search():
    assert check("C", observations=[search(), detail(12), detail(11)])["passed"]


def test_search_query_uses_the_service_trim_and_case_insensitive_semantics():
    assert check("A", observations=[search(query="  gArDeN  "), detail(11)])["passed"]


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "I found Garden home 11.",
        "```json\n{}\n```",
        "[]",
        '{"rentals":[],"count":null} trailing explanation',
        '{"rentals":[],"count":NaN}',
        '{"rentals":[],"count":1e400}',
        '{"rentals":[],"count":null,"count":3}',
    ],
)
def test_only_one_strict_json_object_is_an_answer(text):
    result = verify_task(task("A"), text, trace("A"))
    assert not result["passed"]
    assert result["parsed"] is None
    assert any(failure.startswith("answer.") for failure in result["failures"])


@pytest.mark.parametrize("task_id", ["A", "B", "C"])
def test_plausible_correct_final_without_actual_calls_fails(task_id):
    result = check(task_id, observations=[])
    assert not result["passed"]
    assert "trace.minimum_successful_calls" in result["failures"]
    assert "trace.chain" in result["failures"]
    assert result["unsupported_claims"]


@pytest.mark.parametrize(
    "task_id,observations",
    [
        ("A", [detail(11), search()]),
        ("B", [search(), count()]),
        ("C", [detail(11), search(), detail(12)]),
    ],
)
def test_tools_must_form_the_required_ordered_chain(task_id, observations):
    result = check(task_id, observations=observations)
    assert not result["passed"]
    assert "trace.chain" in result["failures"]
    assert result["unsupported_claims"] == []


def test_wrong_query_cannot_supply_search_evidence():
    result = check("A", observations=[search(query="Unrelated"), detail(11)])
    assert not result["passed"]
    assert "trace.search" in result["failures"]


def test_a_must_get_the_first_result_of_the_matching_search():
    result = check("A", observations=[search(), detail(12)])
    assert not result["passed"]
    assert "trace.chain" in result["failures"]


def test_wrong_detail_id_preserves_factual_support_for_the_five_search_fields():
    payload = answer("A")
    payload["rentals"][0]["description"] = rental(1)["description"]
    result = check("A", payload, [search(), detail(1)])
    assert not result["passed"]
    assert "trace.chain" in result["failures"]
    assert result["unsupported_claims"] == [
        {"path": "rentals[0].description", "reason": "fixture_mismatch"},
    ]


def test_frozen_first_result_cannot_be_overridden_by_a_different_trace_order():
    result = check("A", observations=[search([rental(12), rental(11)]), detail(11)])
    assert not result["passed"]
    assert "trace.chain" in result["failures"]


def test_c_requires_two_distinct_detail_lookups():
    result = check("C", observations=[search(), detail(11), detail(11)])
    assert not result["passed"]
    assert "trace.chain" in result["failures"]


def test_failed_tools_never_supply_facts_or_successful_call_credit():
    observations = trace("A")
    observations[1]["result"]["ok"] = False
    observations[1]["result"]["error"] = "Unavailable."
    result = check("A", observations=observations)
    assert not result["passed"]
    assert "trace.minimum_successful_calls" in result["failures"]
    assert "trace.chain" in result["failures"]
    assert result["unsupported_claims"] == [
        {"path": "rentals[0].description", "reason": "missing_tool_support"},
    ]


def test_b_requires_the_requested_manager_count():
    result = check("B", observations=[count(manager_id=8), search()])
    assert not result["passed"]
    assert "trace.count" in result["failures"]
    assert result["unsupported_claims"] == [
        {"path": "count", "reason": "missing_tool_support"},
    ]


def test_b_search_example_must_belong_to_the_counted_manager():
    observations = [count(), search([rental(11, manager_id=8)])]
    result = check("B", observations=observations)
    assert not result["passed"]
    assert "trace.chain" in result["failures"]


@pytest.mark.parametrize("task_id", ["A", "C"])
def test_full_detail_answers_require_description(task_id):
    payload = answer(task_id)
    del payload["rentals"][0]["description"]
    result = check(task_id, payload)
    assert not result["passed"]
    assert "answer.rental_fields" in result["failures"]


@pytest.mark.parametrize("task_id", ["A", "B", "C"])
def test_partial_rental_answer_fails(task_id):
    payload = answer(task_id)
    payload["rentals"].pop()
    result = check(task_id, payload)
    assert not result["passed"]
    assert "answer.rental_count" in result["failures"]


def test_b_emits_exactly_one_supporting_example():
    payload = {"rentals": task("B")["expected"]["rentals"], "count": 3}
    assert "answer.rental_count" in check("B", payload)["failures"]


def test_c_final_rentals_preserve_the_frozen_search_order():
    payload = answer("C")
    payload["rentals"].reverse()
    assert "answer.rental_ids" in check("C", payload)["failures"]


@pytest.mark.parametrize("value", [2, "3", True, None])
def test_wrong_counts_are_unsupported_claims(value):
    payload = answer("B")
    payload["count"] = value
    result = check("B", payload)
    assert not result["passed"]
    assert {"path": "count", "reason": "fixture_mismatch"} in result["unsupported_claims"]


def test_correct_fixture_count_also_requires_matching_tool_evidence():
    result = check("B", observations=[count(total=4), search()])
    assert not result["passed"]
    assert {"path": "count", "reason": "missing_tool_support"} in result["unsupported_claims"]


def test_fabricated_public_field_fails_even_if_the_tool_also_says_it():
    payload = answer("A")
    payload["rentals"][0]["propertyType"] = "castle"
    observations = trace("A")
    observations[1]["result"]["data"]["propertyType"] = "castle"
    result = check("A", payload, observations)
    assert not result["passed"]
    assert {"path": "rentals[0].propertyType", "reason": "fixture_mismatch"} in result[
        "unsupported_claims"
    ]


def test_correct_fixture_fields_require_matching_detail_evidence():
    observations = trace("A")
    observations[1]["result"]["data"]["description"] = "Different description."
    result = check("A", observations=observations)
    assert not result["passed"]
    assert {"path": "rentals[0].description", "reason": "missing_tool_support"} in result[
        "unsupported_claims"
    ]


def test_extra_factual_fields_are_reported_without_echoing_the_value():
    payload = answer("A")
    payload["rentals"][0]["submitterEmail"] = "private-value-do-not-echo@example.test"
    payload["confidence"] = 1
    result = check("A", payload)
    assert not result["passed"]
    assert result["unsupported_claims"] == [
        {"path": "confidence", "reason": "unsupported_field"},
        {"path": "rentals[0].submitterEmail", "reason": "unsupported_field"},
    ]
    assert "private-value-do-not-echo" not in json.dumps(result["unsupported_claims"])


def test_missing_root_fields_and_wrong_rental_types_fail():
    for payload in (
        {"rentals": answer("A")["rentals"]},
        {"rentals": {}, "count": None},
        {"rentals": [11], "count": None},
    ):
        assert not check("A", payload)["passed"]


def test_wrong_rentals_container_is_an_unsupported_value():
    result = check("A", {"rentals": {"invented": "home"}, "count": None})
    assert {"path": "rentals", "reason": "unsupported_rentals"} in result["unsupported_claims"]


def test_integer_ids_are_not_interchangeable_with_floats_or_booleans():
    for value in (11.0, True):
        payload = answer("A")
        payload["rentals"][0]["id"] = value
        assert not check("A", payload)["passed"]


def test_failed_or_unrelated_observations_do_not_create_false_unsupported_claims():
    failed = deepcopy(detail(11))
    failed["result"] = {"ok": False, "data": None, "error": "Unavailable."}
    observations = [failed, count(manager_id=8), *trace("A")]
    result = check("A", observations=observations)
    assert result["passed"] and result["unsupported_claims"] == []
