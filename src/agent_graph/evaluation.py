"""Pure, offline replay and calculations for the frozen Part 4 experiment.

The worker trace is authoritative. Classification never calls a model, repairs
responses, or treats a schema-valid but unapproved proposal as completion.
"""

from __future__ import annotations

from collections import Counter
import math
from statistics import fmean
from typing import Any

from .contracts import ResponseContractError, parse_planner_response, parse_reviewer_response


RESULT_SCHEMA_VERSION = 1
COHORT_SIZES = {"schema": 30, "ceiling_2": 20, "ceiling_10": 20, "adversarial": 5}
CONTENT_CATEGORIES = (
    "Valid first attempt", "Valid after 1 retry", "Valid after 2+ retries", "Hit turn ceiling",
)
USAGE_NOTE = (
    "Reported token counts only. A zero count can mean usage metadata was unavailable; "
    "it does not establish zero token consumption."
)
DEPLOYMENT_RULE = (
    "Higher observed completion rate, then lower mean application-run latency across "
    "all 20 runs, then the smaller ceiling."
)


class IntegrityError(ValueError):
    """Saved evidence contradicts the graph or the frozen experiment protocol."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrityError(message)


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{name} must be an integer >= {minimum}")
    return value


def _duration(value: Any, name: str) -> int | float:
    _require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
             f"{name} must be a finite, nonnegative duration")
    return value


def _text(value: Any, name: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{name} must be nonblank text")
    return value


def _hash(value: Any, name: str) -> str:
    _require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
             f"{name} must be a lowercase SHA-256 digest")
    return value


def _category(status: str, planner_attempts: int) -> str:
    if status == "accepted":
        return CONTENT_CATEGORIES[min(planner_attempts - 1, 2)]
    return {"turn_limit": CONTENT_CATEGORIES[3], "error": "Operational error", "unknown": "Interrupted/unknown"}[status]


def classify_result(result: dict[str, Any]) -> dict[str, Any]:
    """Replay one graph CLI result and return a version-1 row's derived fields.

    Identity and provenance are added by the campaign runner. Unknown/interrupted
    executions have no terminal CLI result and must be represented by the runner,
    rather than passed here. Configuration failures before creation of a graph run
    likewise remain runner-level errors with their original stdout/stderr.
    """

    _require(isinstance(result, dict), "CLI result must be an object")
    run_id = _text(result.get("run_id"), "run_id")
    status = result.get("status")
    _require(status in {"accepted", "turn_limit", "error"}, "CLI result must have a terminal status")
    maximum = _integer(result.get("max_turns"), "max_turns", 1)
    turns = _integer(result.get("turn_count"), "turn_count")
    _require(turns <= maximum, "turn_count exceeds max_turns")
    elapsed = _duration(result.get("elapsed_ms"), "elapsed_ms")
    _require(result.get("controlled_reviewer") is False, "Measured result must use the normal Reviewer")
    config = result.get("config")
    _require(isinstance(config, dict) and config.get("controlled_reviewer") is False,
             "Configuration must explicitly use the normal Reviewer")
    _require(config.get("max_turns") == maximum, "Configuration ceiling disagrees with result")
    trace = result.get("trace")
    _require(isinstance(trace, list), "trace must be an array")
    _require(turns == len(trace) == _integer(result.get("worker_attempts"), "worker_attempts"),
             "Trace, worker attempts and turn_count disagree")

    planner = reviewer = failures = issues = reviewer_retries = responses = zero_usage = 0
    first_valid = None
    tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    worker_elapsed = []
    proposal = review = reviewed_revision = None
    revision = 0
    expected_worker = "planner"
    stopped = False
    worker_error = None
    previous = None
    for index, event in enumerate(trace, 1):
        _require(isinstance(event, dict), f"Trace event {index} must be an object")
        _require(not stopped, "Trace continues after approval or operational failure")
        worker = event.get("worker")
        _require(worker == expected_worker, f"Trace event {index} violates worker routing; expected {expected_worker}")
        _require(type(event.get("attempt")) is int and event["attempt"] == index,
                 f"Trace event {index} has an incorrect attempt number")
        _require(event.get("controlled") is False, f"Trace event {index} uses a controlled worker")
        worker_elapsed.append(_duration(event.get("elapsed_ms"), f"trace[{index}].elapsed_ms"))
        if worker == "planner":
            planner += 1
            revision += 1
            proposal = review = reviewed_revision = None
        else:
            reviewer += 1
            reviewer_retries += int(previous is not None and previous["worker"] == "reviewer" and previous["outcome"] == "invalid")
            review = reviewed_revision = None
        _require(type(event.get("revision")) is int and event["revision"] == revision,
                 f"Trace event {index} has an incorrect proposal revision")
        usage = event.get("usage")
        _require(isinstance(usage, dict), f"Trace event {index} lacks usage counters")
        for key in tokens:
            tokens[key] += _integer(usage.get(key), f"trace[{index}].usage.{key}")
        outcome = event.get("outcome")
        _require(outcome in {"valid", "invalid", "error"}, f"Trace event {index} has an unknown outcome")
        _require("raw" in event, f"Trace event {index} lacks raw response evidence")
        if outcome == "error":
            worker_error = event.get("error")
            _require(isinstance(worker_error, dict) and worker_error.get("kind") in {"model_error", "internal_error"},
                     "Worker error must be a documented operational failure")
            _text(worker_error.get("message"), "worker error message")
            _require("parsed" not in event, "An operational worker error cannot claim parsed output")
            if worker_error["kind"] == "model_error":
                _require(event["raw"] is None and not any(usage.values()),
                         "A failed model request cannot claim a returned response or token usage")
            elif event["raw"] is not None:
                responses += 1
                zero_usage += int(not any(usage.values()))
            stopped = True
        else:
            responses += 1
            zero_usage += int(not any(usage.values()))
            parser = parse_planner_response if worker == "planner" else parse_reviewer_response
            try:
                parsed = parser(event["raw"])
            except ResponseContractError:
                _require(outcome == "invalid", f"Trace event {index} labels a rejected response valid")
                _require("parsed" not in event, "An invalid response cannot have parsed output")
                _text(event.get("error"), "validation feedback")
                failures += int(worker == "planner")
                expected_worker = worker
            else:
                _require(outcome == "valid", f"Trace event {index} labels a valid response invalid")
                _require(event.get("parsed") == parsed, f"Trace event {index} parsed output disagrees with raw response")
                _require(not event.get("error"), "A valid worker result cannot contain an error")
                if worker == "planner":
                    proposal = parsed
                    first_valid = planner if first_valid is None else first_valid
                    expected_worker = "reviewer"
                else:
                    review, reviewed_revision = parsed, revision
                    issues += len(parsed["issues"])
                    expected_worker = "planner"
                    stopped = not parsed["issues"]
        previous = event

    _require(elapsed + len(trace) * 0.001 >= math.fsum(worker_elapsed),
             "Application latency is shorter than summed worker time")
    for name, expected in (("proposal_revision", revision), ("reviewed_revision", reviewed_revision),
                           ("proposal", proposal), ("review", review), ("adapter_response_count", responses)):
        _require(name in result and result[name] == expected, f"Final {name} disagrees with trace replay")
        if name in {"proposal_revision", "adapter_response_count"} or (name == "reviewed_revision" and expected is not None):
            _integer(result[name], name)
    for name, expected in tokens.items():
        _require(_integer(result.get(name), name) == expected, f"Final {name} disagrees with trace usage")
    approved = proposal is not None and review is not None and not review["issues"] and reviewed_revision == revision
    if status == "accepted":
        _require(approved and result.get("error") is None, "Accepted result lacks current-revision approval")
        _require(result.get("final_output") == proposal, "Accepted final_output differs from the approved proposal")
    else:
        _require(result.get("final_output") is None, "Unaccepted results cannot publish a final_output")
        if status == "turn_limit":
            _require(turns == maximum and not approved and result.get("error") is None,
                     "Ceiling result must exhaust its budget without approval or operational error")
        else:
            error = result.get("error")
            _require(isinstance(error, dict), "Operational result lacks error details")
            _text(error.get("kind"), "error kind")
            _text(error.get("message"), "error message")
            if worker_error is not None:
                _require(error == worker_error, "Final error disagrees with the failed worker")
            else:
                _require(error["kind"] in {"internal_error", "evidence_error", "configuration_error"},
                         "Error result lacks a corresponding worker failure")
    return {
        "run_id": run_id, "status": status, "max_turns": maximum, "turn_count": turns,
        "planner_attempts": planner, "planner_retries": max(0, planner - 1),
        "reviewer_attempts": reviewer, "first_schema_valid_attempt": first_valid,
        "schema_failure_count": failures, "reviewer_issue_count": issues,
        "reviewer_retry_count": reviewer_retries, "category": _category(status, planner),
        "elapsed_ms": elapsed, "worker_elapsed_ms": math.fsum(worker_elapsed),
        "adapter_response_count": responses, **tokens,
        "zero_usage_response_count": zero_usage, "usage_note": USAGE_NOTE,
    }


def _validate_schedule(schedule: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    _require(isinstance(schedule, list) and len(schedule) == 75, "Schedule must contain exactly 75 planned trials")
    by_id = {}
    expected_cohorts = ["schema"] * 30
    for pair in range(20):
        expected_cohorts.extend(("ceiling_2", "ceiling_10") if pair % 2 == 0 else ("ceiling_10", "ceiling_2"))
    expected_cohorts.extend(["adversarial"] * 5)
    ordinary_input = None
    adversarial_input = None
    for order, (slot, cohort) in enumerate(zip(schedule, expected_cohorts), 1):
        _require(isinstance(slot, dict), "Schedule slot must be an object")
        trial_id = _text(slot.get("trial_id"), "scheduled trial_id")
        _require(trial_id not in by_id, f"Duplicate scheduled trial_id: {trial_id}")
        _require(type(slot.get("order")) is int and slot["order"] == order, "Schedule order must be consecutive from 1")
        _require(slot.get("cohort") == cohort, "Schedule violates the frozen 30/alternating-pairs/5 cohort order")
        _require(type(slot.get("max_turns")) is int and slot["max_turns"] == (2 if cohort == "ceiling_2" else 10),
                 "Schedule has the wrong cohort ceiling")
        input_key = _text(slot.get("input_key"), "scheduled input_key")
        if cohort == "adversarial":
            adversarial_input = input_key if adversarial_input is None else adversarial_input
            _require(input_key == adversarial_input, "Adversarial trials must use one frozen input")
        else:
            ordinary_input = input_key if ordinary_input is None else ordinary_input
            _require(input_key == ordinary_input, "Ordinary cohorts must share one frozen input")
        by_id[trial_id] = slot
    _require(adversarial_input != ordinary_input, "The adversarial case must be a separate frozen case")
    return by_id


def _validate_counters(row: dict[str, Any]) -> None:
    if row["status"] == "unknown" or (row["status"] == "error" and row.get("run_id") is None):
        _require(row.get("run_id") is None, "A trial without terminal CLI evidence cannot claim a run_id")
        _require(row.get("elapsed_ms") is None, "A trial without terminal CLI evidence cannot claim application-run latency")
        if row["status"] == "error":
            _text(row.get("operational_error"), "runner operational_error")
        _require(row.get("category") in (None, _category(row["status"], 0)),
                 "An incomplete/operational wrapper cannot claim a content-outcome category")
        for name in ("turn_count", "planner_attempts", "planner_retries", "reviewer_attempts",
                     "first_schema_valid_attempt", "schema_failure_count", "reviewer_issue_count",
                     "reviewer_retry_count", "worker_elapsed_ms", "adapter_response_count",
                     "input_tokens", "output_tokens", "total_tokens", "zero_usage_response_count"):
            _require(row.get(name) is None, f"A trial without terminal CLI evidence cannot infer {name}")
        return
    _text(row.get("run_id"), "run_id")
    turns = _integer(row.get("turn_count"), "turn_count")
    maximum = _integer(row.get("max_turns"), "max_turns", 1)
    planner = _integer(row.get("planner_attempts"), "planner_attempts")
    reviewer = _integer(row.get("reviewer_attempts"), "reviewer_attempts")
    retries = _integer(row.get("planner_retries"), "planner_retries")
    failures = _integer(row.get("schema_failure_count"), "schema_failure_count")
    reviewer_retries = _integer(row.get("reviewer_retry_count"), "reviewer_retry_count")
    issues = _integer(row.get("reviewer_issue_count"), "reviewer_issue_count")
    responses = _integer(row.get("adapter_response_count"), "adapter_response_count")
    zero_usage = _integer(row.get("zero_usage_response_count"), "zero_usage_response_count")
    _require(turns == planner + reviewer and turns <= maximum, "Impossible worker/turn counters")
    _require(retries == max(0, planner - 1), "Impossible Planner retry count")
    _require(failures <= planner and reviewer_retries <= max(0, reviewer - 1), "Impossible failure/retry counts")
    _require(responses <= turns and zero_usage <= responses, "Impossible adapter response/usage counts")
    _require(issues == 0 or reviewer > 0, "Reviewer issues require a Reviewer execution")
    first = row.get("first_schema_valid_attempt")
    if first is not None:
        _integer(first, "first_schema_valid_attempt", 1)
        _require(first <= planner and first - 1 <= failures < planner, "Impossible first schema-valid attempt")
    else:
        _require(reviewer == 0, "Reviewer cannot run without a schema-valid proposal")
    if row["status"] in {"accepted", "turn_limit"}:
        _require(responses == turns, "Content terminal outcomes require a response for every worker")
        _require(first is not None or failures == planner, "Missing schema validity disagrees with Planner failures")
    if row["status"] == "accepted":
        _require(planner >= 1 and reviewer >= 1 and first is not None, "Accepted row lacks valid Planner and Reviewer attempts")
    if row["status"] == "turn_limit":
        _require(turns == maximum, "Ceiling row did not reach max_turns")
    _require(row.get("category") == _category(row["status"], planner), "Category disagrees with terminal status and Planner attempts")
    _duration(row.get("elapsed_ms"), "elapsed_ms")
    _duration(row.get("worker_elapsed_ms"), "worker_elapsed_ms")
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        _integer(row.get(name), name)
    _require(row.get("usage_note") == USAGE_NOTE, "Token-usage caveat is missing or changed")


def _counts(rows: list[dict[str, Any]], expected: int) -> dict[str, Any]:
    statuses = Counter(row["status"] for row in rows)
    latencies = [row["elapsed_ms"] for row in rows if row.get("elapsed_ms") is not None]
    accepted_times = [row["elapsed_ms"] for row in rows if row["status"] == "accepted"]
    terminal = sum(statuses[status] for status in ("accepted", "turn_limit", "error"))
    return {
        "expected": expected, "started": len(rows), "pending": expected - len(rows),
        "terminal": terminal, "accepted": statuses["accepted"], "ceiling": statuses["turn_limit"],
        "error": statuses["error"], "unknown": statuses["unknown"],
        "complete": len(rows) == expected and statuses["accepted"] + statuses["turn_limit"] == expected,
        "completion_rate_pct": statuses["accepted"] / expected * 100,
        "latency_observed_count": len(latencies),
        # The required mean refers to all scheduled runs, never a partial sample.
        "mean_elapsed_ms": fmean(latencies) if len(latencies) == expected else None,
        "observed_mean_elapsed_ms": fmean(latencies) if latencies else None,
        "accepted_mean_elapsed_ms": fmean(accepted_times) if accepted_times else None,
    }


def aggregate_records(records: list[dict[str, Any]], schedule: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate versioned rows and calculate unrounded, fixed-denominator tables.

    Missing never-started slots are pending, while explicit unknown rows represent
    started trials with no terminal evidence. Both prevent a complete claim. Full
    evidence-file/hash checks belong to the runner/verifier; this function checks
    row identities, provenance compatibility, counters, and calculation inputs.
    """

    slots = _validate_schedule(schedule)
    _require(isinstance(records, list), "records must be an array")
    seen_trials: set[str] = set()
    seen_runs: set[str] = set()
    fingerprints: dict[str, str] = {}
    input_hashes: dict[str, str] = {}
    for row in records:
        _require(isinstance(row, dict), "Result row must be an object")
        _require(type(row.get("schema_version")) is int and row["schema_version"] == RESULT_SCHEMA_VERSION,
                 "Unsupported result-record schema_version")
        trial_id = _text(row.get("trial_id"), "trial_id")
        _require(trial_id in slots and trial_id not in seen_trials, f"Unexpected or duplicate trial_id: {trial_id}")
        slot = slots[trial_id]
        for name in ("cohort", "order", "max_turns"):
            _require(row.get(name) == slot[name] and type(row.get(name)) is type(slot[name]),
                     f"Row {trial_id} disagrees with scheduled {name}")
        seen_trials.add(trial_id)
        _require(row.get("status") in {"accepted", "turn_limit", "error", "unknown"}, "Row has unknown lifecycle status")
        _validate_counters(row)
        if row.get("run_id") is not None:
            _require(row["run_id"] not in seen_runs, f"Duplicate graph run_id: {row['run_id']}")
            seen_runs.add(row["run_id"])
        for key in ("campaign_id", "config_fingerprint", "source_fingerprint"):
            value = _text(row.get(key), key) if key == "campaign_id" else _hash(row.get(key), key)
            _require(value == fingerprints.setdefault(key, value), f"Incompatible {key} across measured rows")
        input_hash = _hash(row.get("input_sha256"), "input_sha256")
        _require(input_hash == input_hashes.setdefault(slot["input_key"], input_hash), "Input hashes differ within a frozen input")
        _text(row.get("evidence"), "evidence reference")

    _require(len(set(input_hashes.values())) == len(input_hashes),
             "Ordinary and adversarial inputs must have distinct hashes")
    cohorts = {name: _counts([row for row in records if row["cohort"] == name], expected)
               for name, expected in COHORT_SIZES.items()}
    schema_rows = [row for row in records if row["cohort"] == "schema"]
    buckets = []
    for category in CONTENT_CATEGORIES:
        matching = [row for row in schema_rows if row.get("category") == category]
        buckets.append({"category": category, "count": len(matching),
                        "mean_elapsed_ms": fmean(row["elapsed_ms"] for row in matching) if matching else None})
    observed_schema = [row for row in schema_rows if row.get("run_id") is not None]
    first_valid = Counter(row["first_schema_valid_attempt"] for row in observed_schema if row["first_schema_valid_attempt"] is not None)
    schema_supplement = {
        "observed_terminal_count": sum(row["status"] != "unknown" for row in schema_rows),
        "trace_observed_count": len(observed_schema),
        "attempt_counts": {str(attempt): first_valid[attempt] for attempt in sorted(first_valid)},
        "never_valid_count": sum(row["first_schema_valid_attempt"] is None for row in observed_schema),
        "schema_failure_count": sum(row["schema_failure_count"] for row in observed_schema),
        "runs_with_schema_failures": sum(row["schema_failure_count"] > 0 for row in observed_schema),
        "planner_retries": sum(row["planner_retries"] for row in observed_schema),
        "reviewer_issue_count": sum(row["reviewer_issue_count"] for row in observed_schema),
        "reviewer_retry_count": sum(row["reviewer_retry_count"] for row in observed_schema),
    }
    comparison = {name: cohorts[name] for name in ("ceiling_2", "ceiling_10")}
    choice = None
    if all(value["complete"] and value["mean_elapsed_ms"] is not None for value in comparison.values()):
        winner = min((2, 10), key=lambda ceiling: (-comparison[f"ceiling_{ceiling}"]["completion_rate_pct"],
                                                 comparison[f"ceiling_{ceiling}"]["mean_elapsed_ms"], ceiling))
        short, long = comparison["ceiling_2"], comparison["ceiling_10"]
        reason = ("higher completion rate" if short["accepted"] != long["accepted"] else
                  "lower mean application-run latency" if short["mean_elapsed_ms"] != long["mean_elapsed_ms"] else
                  "smaller ceiling after tied completion and latency")
        choice = {"max_turns": winner, "reason": reason, "rule": DEPLOYMENT_RULE, "cohorts": comparison,
                  "scope": "Observed results for this frozen model, ordinary input, configuration, and 20-run sample per ceiling."}
    return {
        "schema_version": RESULT_SCHEMA_VERSION, **_counts(records, 75),
        "campaign_id": fingerprints.get("campaign_id"),
        "config_fingerprint": fingerprints.get("config_fingerprint"),
        "source_fingerprint": fingerprints.get("source_fingerprint"),
        "missing_trial_ids": [slot["trial_id"] for slot in schedule if slot["trial_id"] not in seen_trials],
        "cohorts": cohorts, "schema_categories": buckets, "schema_first_valid": schema_supplement,
        "deployment_choice": choice,
        "metric": "application-run latency (elapsed_ms); display rounding only; empty or incomplete all-run means are N/A",
        "usage_note": USAGE_NOTE,
    }
