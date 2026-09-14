"""Offline evidence replay and arithmetic, using actual compiled graph traces."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("evaluation_graph_cli", ROOT / "code/agents_graph.py")
cli = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cli)

from src.agent_graph.evaluation import IntegrityError, aggregate_records, classify_result
from src.model_client import CompletionResult, TokenUsage


DRAFT = {"tags": ["apartment", "transit", "parking"], "summary": "An apartment near transit with parking."}
APPROVAL = {"issues": []}
ISSUE = {"issues": ["Parking is not supported.", "Revise the parking tag."]}


class Adapter:
    def __init__(self, responses, usage=TokenUsage(7, 3, 10)):
        self.responses = iter(responses)
        self.usage = usage

    def complete(self, messages):
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return CompletionResult(value if isinstance(value, str) else json.dumps(value), self.usage, None)


def result(responses, ceiling=10, elapsed=100, usage=TokenUsage(7, 3, 10)):
    args = cli.parse_args(["--title", "Apartment", "--content", "Near transit.", "--max-turns", str(ceiling)])
    with patch.object(cli, "_git_metadata", return_value={"commit": "test", "dirty": True}):
        raw = cli.run_graph(args, llm=Adapter(responses, usage))
    raw["elapsed_ms"] = elapsed
    return raw


def schedule():
    slots = []

    def add(cohort, ceiling, input_key="schema"):
        number = sum(slot["cohort"] == cohort for slot in slots) + 1
        slots.append({"trial_id": f"{cohort}-{number:02}", "cohort": cohort,
                      "order": len(slots) + 1, "max_turns": ceiling, "input_key": input_key})

    for _ in range(30):
        add("schema", 10)
    for pair in range(20):
        for ceiling in ((2, 10) if pair % 2 == 0 else (10, 2)):
            add(f"ceiling_{ceiling}", ceiling)
    for _ in range(5):
        add("adversarial", 10, "adversarial")
    return slots


def row(raw, slot):
    return {"schema_version": 1, "campaign_id": "campaign-test", **{key: slot[key] for key in ("trial_id", "cohort", "order")},
            "input_sha256": ("b" if slot["cohort"] == "adversarial" else "a") * 64,
            "config_fingerprint": "c" * 64, "source_fingerprint": "d" * 64,
            "evidence": f"trials/{slot['trial_id']}/result.json", **classify_result(raw)}


class ClassificationTests(unittest.TestCase):
    def test_application_latency_cannot_be_shorter_than_workers(self):
        raw = result([DRAFT, APPROVAL])
        raw["elapsed_ms"] = 0
        raw["trace"][0]["elapsed_ms"] = 100
        with self.assertRaises(IntegrityError):
            classify_result(raw)

    def test_terminal_acceptance_buckets_distinguish_schema_and_semantic_repair(self):
        for responses, category, first_valid, failures in (
            ([DRAFT, APPROVAL], "Valid first attempt", 1, 0),
            ([DRAFT, ISSUE, DRAFT, APPROVAL], "Valid after 1 retry", 1, 0),
            (["bad JSON", DRAFT, APPROVAL], "Valid after 1 retry", 2, 1),
            (["bad JSON", "bad JSON", DRAFT, APPROVAL], "Valid after 2+ retries", 3, 2),
        ):
            with self.subTest(category=category, first_valid=first_valid):
                checked = classify_result(result(responses))
                self.assertEqual(checked["category"], category)
                self.assertEqual(checked["first_schema_valid_attempt"], first_valid)
                self.assertEqual(checked["schema_failure_count"], failures)

    def test_reviewer_retry_counts_executions_after_invalid_feedback_only(self):
        checked = classify_result(result([DRAFT, "bad JSON", "bad JSON", ISSUE, DRAFT, APPROVAL]))
        self.assertEqual(checked["turn_count"], 6)
        self.assertEqual(checked["planner_attempts"], 2)
        self.assertEqual(checked["planner_retries"], 1)
        self.assertEqual(checked["reviewer_attempts"], 4)
        self.assertEqual(checked["reviewer_retry_count"], 2)
        self.assertEqual(checked["reviewer_issue_count"], 2)
        at_ceiling = classify_result(result([DRAFT, "bad JSON"], ceiling=2))
        self.assertEqual(at_ceiling["reviewer_retry_count"], 0)

    def test_valid_unapproved_is_ceiling_and_final_turn_approval_succeeds(self):
        ceiling = classify_result(result([DRAFT], ceiling=1))
        self.assertEqual(ceiling["category"], "Hit turn ceiling")
        self.assertEqual(ceiling["first_schema_valid_attempt"], 1)
        self.assertEqual(classify_result(result([DRAFT, APPROVAL], ceiling=2))["status"], "accepted")

    def test_operational_failure_has_separate_category_and_response_count(self):
        checked = classify_result(result([DRAFT, ConnectionError("offline")]))
        self.assertEqual(checked["category"], "Operational error")
        self.assertEqual(checked["schema_failure_count"], 0)
        self.assertEqual(checked["adapter_response_count"], 1)
        self.assertEqual(checked["total_tokens"], 10)
        evidence_error = result([DRAFT, APPROVAL])
        evidence_error.update(status="error", application_status="accepted", final_output=None,
                              error={"kind": "evidence_error", "message": "disk full"})
        self.assertEqual(classify_result(evidence_error)["category"], "Operational error")

    def test_zero_tokens_cannot_be_claimed_as_known_zero_consumption(self):
        checked = classify_result(result([DRAFT, APPROVAL], usage=TokenUsage(0, 0, 0)))
        self.assertEqual(checked["zero_usage_response_count"], 2)
        self.assertIn("unavailable", checked["usage_note"])

    def test_trace_tampering_is_rejected(self):
        raw = result([DRAFT, APPROVAL])
        mutations = [
            lambda r: r["trace"][0].update(worker="reviewer"),
            lambda r: r["trace"][1].update(attempt=3),
            lambda r: r["trace"][1].update(revision=0),
            lambda r: r["trace"][0].update(outcome="invalid"),
            lambda r: r["trace"][0].update(parsed={**DRAFT, "summary": "Forged"}),
            lambda r: r["trace"][0].update(raw="not JSON"),
            lambda r: r["trace"][1].update(controlled=True),
            lambda r: r.update(proposal_revision=2),
            lambda r: r.update(reviewed_revision=0),
            lambda r: r.update(review={"issues": ["not approved"]}),
            lambda r: r.update(final_output={**DRAFT, "summary": "Forged"}),
            lambda r: r.update(turn_count=1),
            lambda r: r.update(max_turns=1),
            lambda r: r.update(adapter_response_count=3),
            lambda r: r.update(total_tokens=0),
            lambda r: r.update(elapsed_ms=float("nan")),
        ]
        for mutation in mutations:
            tampered = deepcopy(raw)
            mutation(tampered)
            with self.subTest(tampered=tampered), self.assertRaises(IntegrityError):
                classify_result(tampered)

    def test_execution_cannot_continue_after_approval(self):
        raw = result([DRAFT, APPROVAL])
        extra = deepcopy(raw["trace"][0])
        extra.update(attempt=3, revision=2)
        raw["trace"].append(extra)
        raw.update(turn_count=3, worker_attempts=3)
        with self.assertRaises(IntegrityError):
            classify_result(raw)


class AggregationTests(unittest.TestCase):
    def test_empty_and_partial_datasets_keep_expected_denominators(self):
        slots = schedule()
        empty = aggregate_records([], slots)
        self.assertEqual((empty["expected"], empty["started"], empty["pending"]), (75, 0, 75))
        self.assertFalse(empty["complete"])
        self.assertTrue(all(bucket["mean_elapsed_ms"] is None for bucket in empty["schema_categories"]))
        records = [row(result([DRAFT, APPROVAL], elapsed=100), slots[0]),
                   row(result([DRAFT, ISSUE, DRAFT, APPROVAL], elapsed=300), slots[1]),
                   row(result([DRAFT, APPROVAL], ceiling=2, elapsed=200), slots[30])]
        summary = aggregate_records(records, slots)
        self.assertEqual(summary["schema_categories"][0]["mean_elapsed_ms"], 100)
        self.assertEqual(summary["schema_categories"][1]["mean_elapsed_ms"], 300)
        self.assertEqual(summary["cohorts"]["ceiling_2"]["completion_rate_pct"], 5)
        self.assertIsNone(summary["cohorts"]["ceiling_2"]["mean_elapsed_ms"])
        self.assertIsNone(summary["deployment_choice"])

    def test_complete_arithmetic_and_deployment_rule(self):
        slots = schedule()
        records = []
        for slot in slots:
            ceiling = slot["max_turns"]
            is_short_ceiling = slot["cohort"] == "ceiling_2" and slot["trial_id"].endswith("20")
            responses = [DRAFT, ISSUE] if is_short_ceiling else [DRAFT, APPROVAL]
            records.append(row(result(responses, ceiling, elapsed=900 if is_short_ceiling else 100), slot))
        summary = aggregate_records(records, slots)
        self.assertTrue(summary["complete"])
        self.assertEqual((summary["accepted"], summary["ceiling"]), (74, 1))
        short = summary["cohorts"]["ceiling_2"]
        self.assertEqual(short["completion_rate_pct"], 95)
        self.assertEqual(short["mean_elapsed_ms"], 140)
        self.assertEqual(short["accepted_mean_elapsed_ms"], 100)
        self.assertEqual(summary["deployment_choice"]["max_turns"], 10)
        records = [row(result([DRAFT, APPROVAL], s["max_turns"], elapsed=100), s) for s in slots]
        self.assertEqual(aggregate_records(records, slots)["deployment_choice"]["max_turns"], 2)
        for record in records:
            if record["cohort"] == "ceiling_10":
                record["elapsed_ms"] = 99.999
        self.assertEqual(aggregate_records(records, slots)["deployment_choice"]["max_turns"], 10)

    def test_errors_and_unknown_never_make_campaign_complete(self):
        slots = schedule()
        failed = row(result([ConnectionError("offline")]), slots[0])
        unknown = {**failed, **{k: slots[1][k] for k in ("trial_id", "cohort", "order")},
                   "run_id": None, "status": "unknown", "elapsed_ms": None}
        # No terminal evidence means no inferred worker counters.
        for key in tuple(unknown):
            if key in classify_result(result([ConnectionError("offline")])) and key not in {"status", "run_id", "max_turns", "elapsed_ms"}:
                del unknown[key]
        summary = aggregate_records([failed, unknown], slots)
        self.assertEqual((summary["started"], summary["terminal"], summary["error"], summary["unknown"]), (2, 1, 1, 1))
        self.assertFalse(summary["complete"])

    def test_runner_operational_failures_remain_errors_without_invented_metrics(self):
        slots = schedule()
        failed = {"schema_version": 1, "campaign_id": "campaign-test",
                  **{key: slots[0][key] for key in ("trial_id", "cohort", "order", "max_turns")},
                  "run_id": None, "status": "error", "elapsed_ms": None,
                  "operational_error": "Graph subprocess exceeded its outer deadline.",
                  "input_sha256": "a" * 64, "config_fingerprint": "c" * 64,
                  "source_fingerprint": "d" * 64, "evidence": "trials/schema-01/stdout.json"}
        summary = aggregate_records([failed], slots)
        self.assertEqual((summary["terminal"], summary["error"], summary["unknown"]), (1, 1, 0))
        self.assertEqual(summary["latency_observed_count"], 0)
        self.assertEqual(summary["schema_first_valid"]["observed_terminal_count"], 1)
        self.assertEqual(summary["schema_first_valid"]["trace_observed_count"], 0)
        self.assertTrue(all(bucket["count"] == 0 for bucket in summary["schema_categories"]))
        for change in ({"elapsed_ms": 1}, {"turn_count": 0}, {"operational_error": None},
                       {"category": "Hit turn ceiling"}):
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                aggregate_records([{**failed, **change}], slots)

    def test_duplicate_identity_counter_and_provenance_tampering_fail(self):
        slots = schedule()
        first = row(result([DRAFT, APPROVAL]), slots[0])
        second = row(result([DRAFT, APPROVAL]), slots[1])
        for change in ({"run_id": first["run_id"]}, {"trial_id": first["trial_id"]},
                       {"cohort": "adversarial"}, {"order": 999}, {"planner_attempts": 4},
                       {"first_schema_valid_attempt": 2}, {"config_fingerprint": "e" * 64},
                       {"source_fingerprint": "e" * 64}, {"input_sha256": "e" * 64},
                       {"campaign_id": "another-campaign"}, {"schema_version": 2}):
            with self.subTest(change=change), self.assertRaises(IntegrityError):
                aggregate_records([first, {**second, **change}], slots)
        with self.assertRaises(IntegrityError):
            aggregate_records([first], slots[:-1])


if __name__ == "__main__":
    unittest.main()
