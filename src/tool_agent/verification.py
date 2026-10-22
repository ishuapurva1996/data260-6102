"""Deterministic HW7 task checks against frozen fixtures and actual tool results.

Failure strings are stable assertion IDs. Unsupported claims name their JSON
path and reason without copying untrusted values into a second evidence field.
"""

import json
from typing import Any

SEARCH_FIELDS = ("id", "listingTitle", "propertyAddress", "propertyType", "managerId")
DETAIL_FIELDS = (*SEARCH_FIELDS, "description")
TOOL_NAMES = {"search_rentals", "get_rental", "count_rentals"}


def _same(actual: Any, expected: Any) -> bool:
    return type(actual) is type(expected) and actual == expected


def _fail(failures: list[str], assertion_id: str) -> None:
    if assertion_id not in failures:
        failures.append(assertion_id)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Nonfinite JSON number.")


def _parse_answer(answer: str | None, failures: list[str]) -> dict | None:
    if not isinstance(answer, str) or not answer.strip():
        _fail(failures, "answer.present")
        return None
    try:
        parsed = json.loads(
            answer, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
        json.dumps(parsed, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError):
        _fail(failures, "answer.json")
        return None
    if not isinstance(parsed, dict):
        _fail(failures, "answer.object")
        return None
    return parsed


def _successful_calls(observations: list[dict]) -> list[tuple[int, dict]]:
    calls = []
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            continue
        result = observation.get("result")
        if (
            observation.get("name") in TOOL_NAMES
            and isinstance(observation.get("call_id"), str)
            and observation["call_id"]
            and isinstance(observation.get("inputs"), dict)
            and isinstance(result, dict)
            and result.get("ok") is True
            and result.get("error") is None
            and isinstance(result.get("data"), dict)
        ):
            calls.append((index, observation))
    return calls


def _matching_searches(calls: list[tuple[int, dict]], query: str) -> list[tuple[int, dict]]:
    searches = []
    for index, call in calls:
        actual_query = call["inputs"].get("query")
        if (
            call["name"] == "search_rentals"
            and isinstance(actual_query, str)
            and actual_query.strip().casefold() == query.strip().casefold()
            and isinstance(call["result"]["data"].get("items"), list)
        ):
            searches.append((index, call))
    return searches


def _add_evidence(evidence: dict[int, list[dict]], row: dict) -> None:
    rental_id = row.get("id")
    if type(rental_id) is int:
        evidence.setdefault(rental_id, []).append(row)


def _matching_counts(calls: list[tuple[int, dict]], manager_id: int) -> list[tuple[int, dict]]:
    return [
        (index, call)
        for index, call in calls
        if call["name"] == "count_rentals"
        and _same(call["inputs"].get("manager_id"), manager_id)
        and _same(call["result"]["data"].get("managerId"), manager_id)
    ]


def _later_response(detail: dict, search: dict) -> bool:
    proposed = detail.get("model_response_index")
    observed = search.get("model_response_index")
    return type(proposed) is int and type(observed) is int and proposed > observed > 0


def _tool_evidence(task: dict, calls: list[tuple[int, dict]]) -> tuple[dict, list]:
    rentals: dict[int, list[dict]] = {}
    for _, call in calls:
        data = call["result"]["data"]
        if call["name"] == "get_rental":
            _add_evidence(rentals, data)
        elif call["name"] == "search_rentals" and isinstance(data.get("items"), list):
            for row in data["items"]:
                if isinstance(row, dict):
                    _add_evidence(rentals, row)
    counts = (
        [call["result"]["data"] for _, call in _matching_counts(calls, task["manager_id"])]
        if task["id"] == "B"
        else []
    )
    return rentals, counts


def _check_trace(task: dict, calls: list[tuple[int, dict]], failures: list[str]) -> None:
    if len(calls) < (3 if task["id"] == "C" else 2):
        _fail(failures, "trace.minimum_successful_calls")
    searches = _matching_searches(calls, task["query"])
    if not searches:
        _fail(failures, "trace.search")
    chain_found = False

    if task["id"] == "B":
        matching_counts = _matching_counts(calls, task["manager_id"])
        if not matching_counts:
            _fail(failures, "trace.count")
        for count_index, _ in matching_counts:
            for search_index, search_call in searches:
                if search_index <= count_index:
                    continue
                examples = [
                    row
                    for row in search_call["result"]["data"]["items"]
                    if isinstance(row, dict) and _same(row.get("managerId"), task["manager_id"])
                ]
                if examples:
                    chain_found = True
    else:
        expected_ids = [row["id"] for row in task["expected"]["rentals"]]
        for search_index, search_call in searches:
            first_rows = search_call["result"]["data"]["items"][: len(expected_ids)]
            if len(first_rows) != len(expected_ids) or any(
                not isinstance(row, dict) or not _same(row.get("id"), rental_id)
                for row, rental_id in zip(first_rows, expected_ids)
            ):
                continue
            for rental_id in expected_ids:
                matching_details = [
                    call["result"]["data"]
                    for index, call in calls
                    if index > search_index
                    and call["name"] == "get_rental"
                    and _later_response(call, search_call)
                    and _same(call["inputs"].get("rental_id"), rental_id)
                    and _same(call["result"]["data"].get("id"), rental_id)
                ]
                if not matching_details:
                    break
            else:
                chain_found = True
    if not chain_found:
        _fail(failures, "trace.chain")


def verify_missing_id(missing_id: int, answer: str | None, observations: list[dict]) -> dict:
    """Require observed absence and a typed final result without invented fields."""
    failures, claims = [], []
    observed = any(
        isinstance(row, dict)
        and row.get("name") == "get_rental"
        and isinstance(row.get("inputs"), dict)
        and _same(row["inputs"].get("rental_id"), missing_id)
        and isinstance(row.get("result"), dict)
        and row["result"].get("ok") is False
        and row["result"].get("data") is None
        and row["result"].get("error") == f"Rental {missing_id} was not found."
        for row in observations
    )
    if not observed:
        failures.append("trace.missing_id_error")
    parsed = _parse_answer(answer, failures)
    if parsed is not None:
        if set(parsed) != {"rental_id", "found"}:
            failures.append("answer.fields")
            claims.extend(
                {"path": key, "reason": "unsupported_field"}
                for key in sorted(set(parsed) - {"rental_id", "found"})
            )
        if not _same(parsed.get("rental_id"), missing_id):
            failures.append("answer.missing_id")
        if parsed.get("found") is not False:
            failures.append("answer.absence")
    return {
        "passed": not failures,
        "failures": failures,
        "unsupported_claims": claims,
        "parsed": parsed,
    }


def _claim_reason(value: Any, field: str, fixture: dict | None, sources: list[dict]) -> str | None:
    if fixture is None or field not in fixture or not _same(value, fixture[field]):
        return "fixture_mismatch"
    if not any(field in source and _same(value, source[field]) for source in sources):
        return "missing_tool_support"
    return None


def _audit_answer(
    task: dict, parsed: dict, evidence: dict, counts: list, failures: list[str], claims: list[dict]
) -> None:
    if set(parsed) != {"rentals", "count"}:
        _fail(failures, "answer.fields")
    for field in sorted(set(parsed) - {"rentals", "count"}):
        claims.append({"path": field, "reason": "unsupported_field"})

    expected = task["expected"]
    if "count" in parsed:
        count_fixture = {"count": expected["count"]}
        count_sources = counts if task["id"] == "B" else [{"count": None}]
        reason = _claim_reason(parsed["count"], "count", count_fixture, count_sources)
        if reason:
            claims.append({"path": "count", "reason": reason})
            _fail(failures, "answer.count")

    rows = parsed.get("rentals")
    if not isinstance(rows, list):
        _fail(failures, "answer.rentals")
        if "rentals" in parsed:
            claims.append({"path": "rentals", "reason": "unsupported_rentals"})
        return
    required_count = 1 if task["id"] == "B" else len(expected["rentals"])
    if len(rows) != required_count:
        _fail(failures, "answer.rental_count")
    expected_ids = [row["id"] for row in expected["rentals"]]
    actual_ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
    if task["id"] == "B":
        ids_match = len(actual_ids) == 1 and any(
            _same(actual_ids[0], value) for value in expected_ids
        )
    else:
        ids_match = len(actual_ids) == len(expected_ids) and all(
            _same(actual, frozen) for actual, frozen in zip(actual_ids, expected_ids)
        )
    if not ids_match:
        _fail(failures, "answer.rental_ids")

    fields = SEARCH_FIELDS if task["id"] == "B" else DETAIL_FIELDS
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            _fail(failures, "answer.rental_fields")
            claims.append({"path": f"rentals[{index}]", "reason": "unsupported_rental"})
            continue
        if set(row) != set(fields):
            _fail(failures, "answer.rental_fields")
        for field in sorted(set(row) - set(fields)):
            claims.append({"path": f"rentals[{index}].{field}", "reason": "unsupported_field"})
        fixture = next(
            (item for item in expected["rentals"] if _same(row.get("id"), item["id"])), None
        )
        sources = evidence.get(row.get("id"), []) if type(row.get("id")) is int else []
        for field in fields:
            if field not in row:
                continue
            reason = _claim_reason(row[field], field, fixture, sources)
            if reason:
                claims.append({"path": f"rentals[{index}].{field}", "reason": reason})


def verify_task(task: dict, answer: str | None, observations: list[dict]) -> dict:
    """Verify A/B/C using only frozen public facts and successful actual calls.

    The caller supplies executor observations in invocation order, excluding
    proposals rejected before execution. B's fixture may list multiple allowed
    search examples; its final answer must select exactly one of those rows.
    Factual support uses every successful observation independently of whether
    those calls complete the required chain.
    """
    failures: list[str] = []
    claims: list[dict] = []
    parsed = _parse_answer(answer, failures)
    calls = _successful_calls(observations)
    _check_trace(task, calls, failures)
    evidence, counts = _tool_evidence(task, calls)
    if parsed is not None:
        _audit_answer(task, parsed, evidence, counts, failures, claims)
    if claims:
        _fail(failures, "claims.supported")
    return {
        "passed": not failures,
        "failures": failures,
        "unsupported_claims": claims,
        "parsed": parsed,
    }
