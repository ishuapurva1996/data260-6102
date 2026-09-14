"""Exercise the compiled LangGraph and its streamed state transitions."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from src.agent_graph.state import create_initial_state
from src.agent_graph.workflow import build_graph, recursion_limit
from src.model_client import OllamaModelClient


DRAFT = {
    "tags": ["apartment", "parking", "transit"],
    "summary": "Bright apartment with covered parking and convenient light rail access.",
}
REVISED = {
    "tags": ["rental", "parking", "light rail"],
    "summary": "Rental apartment with covered parking near light rail.",
}
APPROVED = {"issues": []}
REJECTED = {"issues": ["Use the listing's exact transit description."]}


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("Unexpected model call beyond the scripted budget")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(
            content=json.dumps(response) if isinstance(response, dict) else response,
            usage_metadata={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
            response_metadata={},
        )


def execute(responses, ceiling, *, controlled=False, graph=None, client=None):
    transport = None
    if client is None:
        transport = ScriptedTransport(responses)
        client = OllamaModelClient(transport)
    initial = create_initial_state(
        title="Apartment near light rail",
        content="Bright apartment with covered parking near light rail.",
        llm=client,
        max_turns=ceiling,
        controlled_reviewer=controlled,
    )
    states = list((graph or build_graph()).stream(
        initial,
        config={"recursion_limit": recursion_limit(ceiling)},
        stream_mode="values",
    ))
    return states[-1], transport, client, states


def human_context(messages):
    message = messages[-1]
    if isinstance(message, tuple):
        content = message[1]
    elif isinstance(message, dict):
        content = message["content"]
    else:
        content = message.content
    return json.loads(content)


class CompiledWorkflowTests(unittest.TestCase):
    def test_two_turn_approval_at_the_exact_ceiling_succeeds(self):
        final, transport, client, states = execute([DRAFT, APPROVED], 2)
        self.assertEqual(final["status"], "accepted")
        self.assertEqual(final["turn_count"], 2)
        self.assertEqual(final["planner_proposal"], DRAFT)
        self.assertEqual(final["reviewed_revision"], final["proposal_revision"])
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(client.stats.turn_count, 2)
        self.assertFalse(final["pending_worker_turn"])
        self.assertGreater(len(states), 2)

    def test_one_turn_stops_with_an_unreviewed_draft(self):
        final, transport, _, _ = execute([DRAFT], 1)
        self.assertEqual(final["status"], "turn_limit")
        self.assertEqual(final["turn_count"], 1)
        self.assertEqual(final["planner_proposal"], DRAFT)
        self.assertIsNone(final["reviewed_revision"])
        self.assertEqual(len(transport.calls), 1)

    def test_rejection_on_last_turn_is_not_acceptance(self):
        final, transport, _, _ = execute([DRAFT, REJECTED], 2)
        self.assertEqual(final["status"], "turn_limit")
        self.assertEqual(final["turn_count"], 2)
        self.assertEqual(final["reviewer_feedback"], REJECTED)
        self.assertEqual(len(transport.calls), 2)

    def test_odd_ceiling_never_reuses_an_old_review_for_a_new_draft(self):
        final, transport, _, _ = execute([DRAFT, REJECTED, REVISED], 3)
        self.assertEqual(final["status"], "turn_limit")
        self.assertEqual(final["turn_count"], 3)
        self.assertEqual(final["proposal_revision"], 2)
        self.assertEqual(final["planner_proposal"], REVISED)
        self.assertIsNone(final["reviewed_revision"])
        self.assertIsNone(final["reviewer_feedback"])
        self.assertEqual(len(transport.calls), 3)

    def test_revision_loop_can_succeed_on_fourth_turn(self):
        final, transport, _, _ = execute([DRAFT, REJECTED, REVISED, APPROVED], 4)
        self.assertEqual(final["status"], "accepted")
        self.assertEqual(final["turn_count"], 4)
        self.assertEqual(final["proposal_revision"], 2)
        self.assertEqual(final["reviewed_revision"], 2)
        self.assertEqual(final["planner_proposal"], REVISED)
        self.assertEqual([event["worker"] for event in final["trace"]],
                         ["planner", "reviewer", "planner", "reviewer"])
        self.assertEqual(len(transport.calls), 4)

    def test_ten_turn_persistent_issues_finish_normally_after_five_pairs(self):
        final, transport, _, _ = execute([DRAFT, REJECTED] * 5, 10)
        self.assertEqual(final["status"], "turn_limit")
        self.assertEqual(final["turn_count"], 10)
        self.assertEqual(final["proposal_revision"], 5)
        self.assertEqual(final["reviewed_revision"], 5)
        self.assertEqual(len(transport.calls), 10)
        self.assertFalse(final["pending_worker_turn"])
        self.assertEqual([event["worker"] for event in final["trace"]],
                         ["planner", "reviewer"] * 5)

    def test_malformed_planner_retries_planner_and_counts_the_bad_response(self):
        bad = "Here is the JSON: " + json.dumps(DRAFT)
        final, transport, client, _ = execute([bad, DRAFT, APPROVED], 3)
        self.assertEqual(final["status"], "accepted")
        self.assertEqual(final["turn_count"], 3)
        self.assertEqual(final["proposal_revision"], 2)
        self.assertEqual([event["worker"] for event in final["trace"]],
                         ["planner", "planner", "reviewer"])
        self.assertEqual(final["trace"][0]["raw"], bad)
        self.assertEqual(final["adapter_response_count"], 3)
        self.assertEqual(client.stats.turn_count, 3)
        self.assertEqual(final["input_tokens"], 15)
        self.assertEqual(final["output_tokens"], 9)
        self.assertEqual(final["total_tokens"], 24)
        self.assertIn(bad, human_context(transport.calls[1]).values())

    def test_missing_reviewer_issues_retries_the_same_revision(self):
        bad = '{"message": "The draft is good"}'
        final, transport, _, _ = execute([DRAFT, bad, APPROVED], 3)
        self.assertEqual(final["status"], "accepted")
        self.assertEqual(final["turn_count"], 3)
        self.assertEqual(final["proposal_revision"], 1)
        self.assertEqual(final["reviewed_revision"], 1)
        self.assertEqual([event["worker"] for event in final["trace"]],
                         ["planner", "reviewer", "reviewer"])
        self.assertEqual(final["trace"][1]["raw"], bad)
        self.assertIn(bad, human_context(transport.calls[2]).values())

    def test_malformed_revision_keeps_the_last_draft_and_critique_in_retry_context(self):
        final, transport, _, _ = execute(
            [DRAFT, REJECTED, "invalid revision", REVISED, APPROVED], 5,
        )
        self.assertEqual(final["status"], "accepted")
        self.assertEqual(final["proposal_revision"], 3)
        self.assertEqual(final["turn_count"], 5)
        retry_context = human_context(transport.calls[3])
        self.assertIn(DRAFT, retry_context.values())
        self.assertIn(REJECTED, retry_context.values())
        self.assertIn("invalid revision", retry_context.values())

    def test_malformed_review_at_the_ceiling_cannot_be_treated_as_approval(self):
        final, transport, _, _ = execute([DRAFT, {}], 2)
        self.assertEqual(final["status"], "turn_limit")
        self.assertEqual(final["turn_count"], 2)
        self.assertIsNone(final["reviewed_revision"])
        self.assertIsNone(final["reviewer_feedback"])
        self.assertEqual(final["planner_proposal"], DRAFT)
        self.assertEqual(len(transport.calls), 2)

    def test_all_malformed_planner_responses_exhaust_instead_of_being_repaired(self):
        final, transport, _, _ = execute(["invalid"] * 4, 4)
        self.assertEqual(final["status"], "turn_limit")
        self.assertEqual(final["turn_count"], 4)
        self.assertEqual(final["proposal_revision"], 4)
        self.assertIsNone(final["planner_proposal"])
        self.assertIsNone(final["reviewed_revision"])
        self.assertEqual(len(transport.calls), 4)

    def test_transport_failure_stops_without_hidden_retries(self):
        final, transport, client, _ = execute(
            [DRAFT, ConnectionError("Ollama is unavailable")], 10,
        )
        self.assertEqual(final["status"], "error")
        self.assertEqual(final["turn_count"], 2)
        self.assertEqual(final["adapter_response_count"], 1)
        self.assertEqual(client.stats.turn_count, 1)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(final["total_tokens"], 8)
        self.assertFalse(final["pending_worker_turn"])

    def test_controlled_issue_mode_performs_real_adapter_calls_and_never_approves(self):
        final, transport, client, _ = execute([DRAFT, APPROVED] * 5, 10, controlled=True)
        self.assertEqual(final["status"], "turn_limit")
        self.assertEqual(final["turn_count"], 10)
        self.assertEqual(final["proposal_revision"], 5)
        self.assertEqual(len(transport.calls), 10)
        self.assertEqual(client.stats.turn_count, 10)
        self.assertTrue(final["reviewer_feedback"]["issues"])
        reviews = [event for event in final["trace"] if event["worker"] == "reviewer"]
        self.assertEqual(len(reviews), 5)
        self.assertTrue(all(event["controlled"] for event in reviews))
        self.assertTrue(all(json.loads(event["raw"]) == APPROVED for event in reviews))

    def test_a_compiled_graph_can_run_twice_without_leaking_state_or_usage(self):
        graph = build_graph()
        transport = ScriptedTransport([DRAFT, APPROVED, REVISED, APPROVED])
        client = OllamaModelClient(transport)
        first, _, _, _ = execute([], 2, graph=graph, client=client)
        second, _, _, states = execute([], 2, graph=graph, client=client)
        self.assertEqual(first["planner_proposal"], DRAFT)
        self.assertEqual(second["planner_proposal"], REVISED)
        self.assertEqual(states[0]["turn_count"], 0)
        self.assertEqual(states[0]["trace"], [])
        self.assertIsNone(states[0]["planner_proposal"])
        self.assertIsNone(states[0]["reviewer_feedback"])
        self.assertEqual(second["turn_count"], 2)
        self.assertEqual(second["adapter_response_count"], 2)
        self.assertEqual(second["total_tokens"], 16)
        self.assertEqual(client.stats.turn_count, 4)
        self.assertEqual(len(transport.calls), 4)
        self.assertEqual(len(first["trace"]), 2)

    def test_framework_recursion_limit_includes_supervisor_steps(self):
        for ceiling in (1, 2, 3, 4, 10):
            with self.subTest(ceiling=ceiling):
                self.assertGreater(recursion_limit(ceiling), 1 + 2 * ceiling)


if __name__ == "__main__":
    unittest.main()
