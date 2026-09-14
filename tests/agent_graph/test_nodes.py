"""Deterministic node and response-contract checks; no Ollama service needed."""

from __future__ import annotations

import copy
import json
import unittest
from types import SimpleNamespace

from src.agent_graph.contracts import (
    ResponseContractError,
    parse_planner_response,
    parse_reviewer_response,
    validate_planner_proposal,
)
from src.agent_graph.nodes import planner_node, reviewer_node, supervisor_node
from src.agent_graph.router import router_logic
from src.agent_graph.state import create_initial_state
from src.model_client import OllamaModelClient


PROPOSAL = {
    "tags": ["apartment", "parking", "transit"],
    "summary": "Bright apartment with covered parking and convenient light rail access.",
}
APPROVAL = {"issues": [], "message": "The proposal is supported by the listing."}


class ScriptedModel:
    """Fake the transport underneath the real HW1 adapter, including usage."""

    def __init__(self, *responses, with_usage=True):
        self.responses = list(responses)
        self.calls = []
        self.with_usage = with_usage

    def invoke(self, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("The graph attempted an unexpected extra model call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        text = json.dumps(response) if isinstance(response, dict) else response
        return SimpleNamespace(
            content=text,
            usage_metadata=(
                {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
                if self.with_usage else None
            ),
            response_metadata={},
        )


def make_state(*responses, max_turns=10, controlled_reviewer=False, with_usage=True):
    model = ScriptedModel(*responses, with_usage=with_usage)
    client = OllamaModelClient(model)
    state = create_initial_state(
        title="Apartment near light rail",
        content="Bright apartment with covered parking and convenient light rail access.",
        llm=client,
        max_turns=max_turns,
        controlled_reviewer=controlled_reviewer,
    )
    return state, model, client


def snapshot(state):
    """The adapter intentionally records calls; state containers must not change."""
    return copy.deepcopy({key: value for key, value in state.items() if key != "llm"})


def prompt_text(messages):
    chunks = []
    for message in messages:
        if isinstance(message, tuple):
            chunks.append(str(message[1]))
        elif isinstance(message, dict):
            chunks.append(str(message.get("content", "")))
        else:
            chunks.append(str(getattr(message, "content", message)))
    return "\n".join(chunks)


class ResponseContractTests(unittest.TestCase):
    def test_valid_outputs_are_preserved(self):
        self.assertEqual(parse_planner_response(json.dumps(PROPOSAL)), PROPOSAL)
        self.assertEqual(parse_reviewer_response(json.dumps(APPROVAL)), APPROVAL)

    def test_planner_rejects_invalid_shapes_without_repairing_them(self):
        invalid = [
            "Here is your answer: " + json.dumps(PROPOSAL),
            "```json\n" + json.dumps(PROPOSAL) + "\n```",
            json.dumps(PROPOSAL) + " trailing prose",
            json.dumps([PROPOSAL]),
            "null",
            "{}",
            json.dumps({**PROPOSAL, "tags": ["one", "two"]}),
            json.dumps({**PROPOSAL, "tags": ["one", "two", "three", "four"]}),
            json.dumps({**PROPOSAL, "tags": ["one", "two", 3]}),
            json.dumps({**PROPOSAL, "tags": ["one", "two", True]}),
            json.dumps({**PROPOSAL, "tags": "one two three"}),
            json.dumps({**PROPOSAL, "tags": ["one", "two", "  "]}),
            json.dumps({**PROPOSAL, "tags": ["one", "two", " \t "]}),
            json.dumps({**PROPOSAL, "summary": None}),
            json.dumps({**PROPOSAL, "summary": 17}),
            json.dumps({**PROPOSAL, "summary": True}),
            json.dumps({**PROPOSAL, "summary": "   "}),
            json.dumps({**PROPOSAL, "summary": " ".join(["word"] * 26)}),
            json.dumps({**PROPOSAL, "extra": "not allowed"}),
            json.dumps({"tags": PROPOSAL["tags"]}),
            json.dumps({"summary": PROPOSAL["summary"]}),
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ResponseContractError):
                parse_planner_response(raw)

    def test_summary_boundary_counts_whitespace_delimited_words(self):
        proposal = {**PROPOSAL, "summary": "\t".join(["word"] * 25)}
        self.assertEqual(parse_planner_response(json.dumps(proposal)), proposal)

    def test_part4_tag_character_boundaries(self):
        for length in (3, 30):
            proposal = {**PROPOSAL, "tags": ["x" * length, "parking", "transit"]}
            with self.subTest(length=length):
                parsed = parse_planner_response(json.dumps(proposal))
                self.assertEqual(parsed, proposal)
                self.assertIs(type(parsed), dict)
                self.assertIs(type(parsed["tags"]), list)
        for length in (2, 31):
            proposal = {**PROPOSAL, "tags": ["x" * length, "parking", "transit"]}
            with self.subTest(length=length):
                with self.assertRaises(ResponseContractError) as error:
                    parse_planner_response(json.dumps(proposal))
                self.assertIn("tags.0", str(error.exception))
                self.assertIn("3" if length == 2 else "30", str(error.exception))

    def test_original_unicode_and_whitespace_are_counted_and_preserved(self):
        proposal = {
            "tags": [" a ", "e\u0301x", "\U0001f3e0" * 30],
            "summary": " \t" + "\u2003".join(["résumé"] * 25) + "\n",
        }
        self.assertEqual(parse_planner_response(json.dumps(proposal)), proposal)
        for tag in ("\U0001f3e0" * 2, "e\u0301", " " + "x" * 30):
            with self.subTest(tag=tag), self.assertRaises(ResponseContractError):
                parse_planner_response(json.dumps({**proposal, "tags": [tag, "two", "three"]}))
        with self.assertRaises(ResponseContractError):
            parse_planner_response(json.dumps({**proposal, "summary": proposal["summary"] + "word"}))

    def test_direct_validation_does_not_coerce_a_tuple_or_bytes(self):
        for value in (
            {**PROPOSAL, "tags": tuple(PROPOSAL["tags"])},
            {**PROPOSAL, "tags": [b"one", "two", "three"]},
            {**PROPOSAL, "summary": b"A summary"},
        ):
            with self.subTest(value=value), self.assertRaises(ResponseContractError):
                validate_planner_proposal(value)

    def test_strict_json_loader_rejects_duplicate_keys_and_nonfinite_constants(self):
        for raw in (
            '{"tags":["one","two","three"],"summary":"first","summary":"second"}',
            '{"tags":["one","two","three"],"summary":NaN}',
            '{"tags":["one","two","three"],"summary":Infinity}',
            '{"tags":["one","two","three"],"summary":-Infinity}',
        ):
            with self.subTest(raw=raw), self.assertRaises(ResponseContractError):
                parse_planner_response(raw)

    def test_reviewer_requires_an_explicit_list_of_string_issues(self):
        invalid = [
            "{}", "null", "[]", '{"issues": null}', '{"issues": "none"}',
            '{"issues": [1]}', '{"issues": [], "message": 7}',
            "```json\n{\"issues\": []}\n```", '{"issues": []} Approved!',
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_reviewer_response(raw)

    def test_empty_issue_list_does_not_require_an_explanation(self):
        self.assertEqual(parse_reviewer_response('{"issues": []}'), {"issues": []})


class NodeTests(unittest.TestCase):
    def test_planner_returns_a_partial_update_without_mutating_state(self):
        state, model, _ = make_state(PROPOSAL)
        before = snapshot(state)
        update = planner_node(state)
        self.assertEqual(snapshot(state), before)
        self.assertNotIn("llm", update)
        self.assertNotIn("title", update)
        self.assertEqual(update["planner_proposal"], PROPOSAL)
        self.assertEqual(update["proposal_revision"], 1)
        self.assertTrue(update["pending_worker_turn"])
        self.assertEqual(state["turn_count"], 0)
        self.assertEqual(len(model.calls), 1)

    def test_reviewer_returns_update_without_mutating_proposal_or_state(self):
        state, _, _ = make_state(PROPOSAL, APPROVAL)
        state.update(planner_node(state))
        state.update(supervisor_node(state))
        before = snapshot(state)
        update = reviewer_node(state)
        self.assertEqual(snapshot(state), before)
        self.assertEqual(update["reviewer_feedback"], APPROVAL)
        self.assertEqual(update["reviewed_revision"], state["proposal_revision"])
        self.assertNotIn("planner_proposal", update)

    def test_supervisor_consumes_worker_marker_exactly_once(self):
        state, _, _ = make_state(PROPOSAL)
        state.update(supervisor_node(state))
        self.assertEqual(state["turn_count"], 0)
        state.update(planner_node(state))
        state.update(supervisor_node(state))
        self.assertEqual(state["turn_count"], 1)
        self.assertFalse(state["pending_worker_turn"])
        state.update(supervisor_node(state))
        self.assertEqual(state["turn_count"], 1)

    def test_malformed_planner_preserves_raw_usage_and_requests_visible_retry(self):
        raw = "Invalid wrapped answer: " + json.dumps(PROPOSAL)
        state, _, client = make_state(raw)
        update = planner_node(state)
        self.assertIsNone(update["planner_proposal"])
        self.assertEqual(update["planner_raw"], raw)
        self.assertEqual(update["retry_target"], "planner")
        self.assertTrue(update["retry_feedback"])
        self.assertEqual(update["adapter_response_count"], 1)
        self.assertEqual(update["input_tokens"], 11)
        self.assertEqual(update["output_tokens"], 7)
        self.assertEqual(update["total_tokens"], 18)
        self.assertEqual(client.stats.turn_count, 1)
        self.assertEqual(update["trace"][-1]["raw"], raw)
        self.assertEqual(update["trace"][-1]["outcome"], "invalid")

    def test_every_new_planner_attempt_invalidates_old_approval_even_on_failure(self):
        state, _, _ = make_state({**PROPOSAL, "tags": ["AI", "parking", "transit"]})
        state.update(
            planner_proposal=copy.deepcopy(PROPOSAL),
            proposal_revision=4,
            reviewer_feedback=copy.deepcopy(APPROVAL),
            reviewed_revision=4,
        )
        state.update(planner_node(state))
        self.assertEqual(state["proposal_revision"], 5)
        self.assertIsNone(state["planner_proposal"])
        self.assertIsNone(state["reviewer_feedback"])
        self.assertIsNone(state["reviewed_revision"])
        state.update(supervisor_node(state))
        self.assertNotEqual(state["status"], "accepted")
        self.assertEqual(router_logic(state), "planner")

    def test_a_current_review_cannot_approve_a_schema_invalid_draft(self):
        state, _, _ = make_state()
        state.update(
            planner_proposal={**PROPOSAL, "tags": ["AI", "parking", "transit"]},
            proposal_revision=1,
            reviewer_feedback=copy.deepcopy(APPROVAL),
            reviewed_revision=1,
        )
        state.update(supervisor_node(state))
        self.assertNotEqual(state["status"], "accepted")

    def test_malformed_reviewer_invalidates_old_review_but_keeps_draft(self):
        state, _, _ = make_state('{"message": "Looks good"}')
        state.update(
            planner_proposal=copy.deepcopy(PROPOSAL),
            proposal_revision=3,
            reviewer_feedback=copy.deepcopy(APPROVAL),
            reviewed_revision=2,
        )
        before = snapshot(state)
        update = reviewer_node(state)
        self.assertEqual(snapshot(state), before)
        state.update(update)
        self.assertEqual(state["planner_proposal"], PROPOSAL)
        self.assertEqual(state["proposal_revision"], 3)
        self.assertIsNone(state["reviewer_feedback"])
        self.assertIsNone(state["reviewed_revision"])
        self.assertEqual(state["retry_target"], "reviewer")
        self.assertEqual(state["reviewer_raw"], '{"message": "Looks good"}')

    def test_planner_prompt_receives_previous_draft_and_reviewer_issue(self):
        issue = "Remove the unsupported pet-friendly claim."
        state, model, _ = make_state(PROPOSAL)
        previous = {**PROPOSAL, "tags": ["pet-friendly", "parking", "transit"]}
        state.update(
            planner_proposal=previous,
            proposal_revision=1,
            reviewer_feedback={"issues": [issue]},
            reviewed_revision=1,
        )
        planner_node(state)
        prompt = prompt_text(model.calls[0])
        self.assertIn(issue, prompt)
        self.assertIn("pet-friendly", prompt)
        self.assertIn(state["title"], prompt)
        self.assertIn(state["content"], prompt)

    def test_transport_failure_counts_attempt_but_not_successful_adapter_response(self):
        state, model, client = make_state(TimeoutError("Ollama request timed out"))
        state.update(planner_node(state))
        state.update(supervisor_node(state))
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["turn_count"], 1)
        self.assertEqual(state["adapter_response_count"], 0)
        self.assertEqual(client.stats.turn_count, 0)
        self.assertEqual(len(model.calls), 1)
        self.assertTrue(state["error"])
        self.assertFalse(state["pending_worker_turn"])

    def test_missing_usage_is_zero_without_erasing_the_response_count(self):
        state, _, _ = make_state(PROPOSAL, with_usage=False)
        update = planner_node(state)
        self.assertEqual(update["adapter_response_count"], 1)
        self.assertEqual(update["input_tokens"], 0)
        self.assertEqual(update["output_tokens"], 0)
        self.assertEqual(update["total_tokens"], 0)

    def test_router_is_pure_and_does_not_make_model_calls(self):
        state, model, _ = make_state()
        before = snapshot(state)
        for _ in range(3):
            self.assertEqual(router_logic(state), "planner")
        self.assertEqual(snapshot(state), before)
        self.assertEqual(model.calls, [])

    def test_stale_review_cannot_approve_the_current_draft(self):
        state, _, _ = make_state()
        state.update(
            planner_proposal=copy.deepcopy(PROPOSAL),
            proposal_revision=2,
            reviewer_feedback=copy.deepcopy(APPROVAL),
            reviewed_revision=1,
        )
        state.update(supervisor_node(state))
        self.assertEqual(state["status"], "running")
        self.assertEqual(router_logic(state), "reviewer")

    def test_fatal_error_takes_precedence_over_approval(self):
        state, _, _ = make_state()
        state.update(
            planner_proposal=copy.deepcopy(PROPOSAL),
            proposal_revision=1,
            reviewer_feedback=copy.deepcopy(APPROVAL),
            reviewed_revision=1,
            error={"type": "internal", "message": "Unexpected failure"},
        )
        state.update(supervisor_node(state))
        self.assertEqual(state["status"], "error")

    def test_initial_states_own_fresh_mutable_collections(self):
        first, _, _ = make_state()
        second, _, _ = make_state()
        first["trace"].append({"worker": "sentinel"})
        self.assertEqual(second["trace"], [])
        self.assertEqual(second["turn_count"], 0)
        self.assertIsNone(second["planner_proposal"])
        self.assertIsNone(second["reviewer_feedback"])

    def test_invalid_ceiling_fails_before_any_model_work(self):
        for ceiling in (0, -1, True, 1.5):
            with self.subTest(ceiling=ceiling), self.assertRaises(ValueError):
                make_state(max_turns=ceiling)


if __name__ == "__main__":
    unittest.main()
