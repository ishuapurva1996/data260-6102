"""Controlled native responses prove repair/budget behavior, not live model quality."""

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.model_client import CompletionResult, TokenUsage
from src.tool_agent.budget import Budget
from src.tool_agent.loop import run_agent


def response(content="", calls=None, invalid=None):
    return CompletionResult(
        content,
        TokenUsage(1, 1, 2),
        SimpleNamespace(tool_calls=calls or [], invalid_tool_calls=invalid or [], content=content),
    )


def call(name, args, ident):
    return {"id": ident, "name": name, "args": args, "type": "tool_call"}


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, messages, tools=None):
        self.requests.append(list(messages))
        return next(self.responses)


def execute(model, **options):
    stream = io.StringIO()
    invoked = []

    def executor(name, inputs):
        invoked.append((name, inputs))
        return '{"ok":true,"data":{"count":3},"error":null}'

    result = run_agent(
        "Count manager 98 rentals.",
        model=model,
        executor=executor,
        log_stream=stream,
        code_revision="controlled-unit",
        **options,
    )
    return result, invoked, [json.loads(line) for line in stream.getvalue().splitlines()]


def test_invalid_operation_gets_one_repair_and_preserves_both_native_ids():
    bad = response(calls=[call("missing_tool", {}, "original-native")])
    repaired = response(calls=[call("count_rentals", {"manager_id": 98}, "repaired-native")])
    model = Model([bad, repaired, response("There are three rentals.")])
    result, invoked, events = execute(model)
    assert result.stop_reason == "completed" and result.tool_calls == 1
    assert invoked == [("count_rentals", {"manager_id": 98})]
    assert model.requests[1][2] is bad.raw_response
    assert any(
        m.get("tool_call_id") == "original-native" for m in model.requests[1] if isinstance(m, dict)
    )
    assert any(
        m.get("tool_call_id") == "repaired-native" for m in model.requests[2] if isinstance(m, dict)
    )
    proposals = [e for e in events if e["event"] == "proposal"]
    repairs = [e for e in events if e["event"] == "repair"]
    assert len(proposals) == 1 and proposals[0]["initial_valid"] is False
    assert len(repairs) == 1 and repairs[0]["final_valid"] is True
    assert repairs[0]["proposal_id"] == proposals[0]["proposal_id"]


def test_second_invalid_operation_stops_without_executor_or_third_prompt():
    model = Model(
        [
            response(calls=[call("get_rental", {"rental_id": "bad"}, "one")]),
            response(calls=[call("get_rental", {"rental_id": "still bad"}, "two")]),
        ]
    )
    result, invoked, events = execute(model)
    assert result.stop_reason == "repair_failed" and result.steps == 2
    assert invoked == [] and len(model.requests) == 2
    assert any(e["event"] == "repair" and not e["final_valid"] for e in events)


def test_parser_rejected_arguments_can_be_repaired_once():
    model = Model(
        [
            response(invalid=[{"id": "broken", "name": "count_rentals", "args": "{"}]),
            response(calls=[call("count_rentals", {"manager_id": 98}, "fixed")]),
            response("Three rentals."),
        ]
    )
    result, invoked, events = execute(model)
    assert result.stop_reason == "completed" and len(invoked) == 1
    assert (
        next(e for e in events if e["event"] == "proposal")["failure_category"]
        == "malformed arguments"
    )


def test_premature_structured_answer_without_chain_is_a_failed_task():
    path = Path(__file__).resolve().parents[1] / "reports/hw07/cases/agent_tasks.json"
    task = json.loads(path.read_text())["tasks"][0]
    model = Model([response(json.dumps(task["expected"]))])
    result, invoked, events = execute(model, task=task)
    assert result.stop_reason == "verification_failed" and result.tool_calls == 0
    assert invoked == []
    terminal = events[-1]
    assert not terminal["verification"]["passed"]
    assert "text when a tool was required" in terminal["failure_categories"]


def test_tool_ceiling_stops_before_second_executor_invocation():
    model = Model(
        [
            response(
                calls=[
                    call("count_rentals", {"manager_id": 98}, "one"),
                    call("count_rentals", {"manager_id": 98}, "two"),
                ]
            )
        ]
    )
    result, invoked, _ = execute(model, max_tools=1)
    assert result.stop_reason == "budget_exhausted" and len(invoked) == result.tool_calls == 1


def test_tool_ceiling_keeps_every_emitted_proposal_in_the_denominator():
    model = Model(
        [response(calls=[call("count_rentals", {"manager_id": 98}, str(i)) for i in range(3)])]
    )
    result, invoked, events = execute(model, max_tools=1)
    assert result.stop_reason == "budget_exhausted" and len(invoked) == 1
    assert len([e for e in events if e["event"] == "proposal"]) == 3


def test_model_output_cap_cannot_exceed_the_shared_reservation():
    with pytest.raises(ValueError, match="budget.*model"):
        execute(Model([]), budget=Budget(output_limit=128), output_limit=512)


def test_dispatched_timeout_charges_unknown_usage_to_shared_ledger():
    class TimeoutModel:
        def complete(self, messages, tools=None):
            raise TimeoutError("private transport detail")

    budget = Budget()
    result, invoked, events = execute(TimeoutModel(), budget=budget)
    snapshot = budget.snapshot()
    assert result.stop_reason == "model_error" and invoked == []
    assert snapshot["total_tokens"] is None and snapshot["unknown_usage_calls"] == 1
    assert snapshot["charged_tokens"] == next(
        e["reservation"]["total_tokens"] for e in events if e["event"] == "model_request"
    )
    assert "private transport detail" not in json.dumps(events)


@pytest.mark.parametrize("overrun", [False, True])
def test_aborted_response_keeps_identifiable_emitted_proposals(overrun):
    proposed = response(
        calls=[
            call("count_rentals", {"manager_id": 98}, str(i)) for i in range(1 if overrun else 4)
        ]
    )
    if overrun:
        proposed = CompletionResult(
            proposed.content, TokenUsage(25000, 1, 25001), proposed.raw_response
        )
    result, invoked, events = execute(Model([proposed]))
    assert result.stop_reason == ("budget_exhausted" if overrun else "malformed_response")
    assert invoked == []
    assert len([e for e in events if e["event"] == "proposal"]) == (1 if overrun else 4)


def test_parser_repair_history_has_serialized_assistant_call_for_each_tool_id():
    from langchain_core.messages import AIMessage, convert_to_messages
    from langchain_ollama import ChatOllama

    bad = CompletionResult(
        "",
        TokenUsage(1, 1, 2),
        AIMessage(
            content="", invalid_tool_calls=[{"id": "broken", "name": "count_rentals", "args": "{"}]
        ),
    )
    fixed = CompletionResult(
        "",
        TokenUsage(1, 1, 2),
        AIMessage(content="", tool_calls=[call("count_rentals", {"manager_id": 98}, "fixed")]),
    )
    model = Model([bad, fixed, response("Three rentals.")])
    result, _, events = execute(model)
    assert result.stop_reason == "completed"
    history = ChatOllama(model="offline")._convert_messages_to_ollama_messages(
        convert_to_messages(model.requests[1])
    )
    preceding = set()
    for message in history:
        preceding.update(c["id"] for c in message.get("tool_calls", []))
        if message["role"] == "tool":
            assert message["tool_call_id"] in preceding
    assert "broken" in preceding
    assert next(e for e in events if e["event"] == "proposal")["inputs"] == "{"


@pytest.mark.parametrize("guessed", [False, True])
def test_dependent_details_need_a_later_model_response(guessed):
    from langchain_core.messages import AIMessage

    task = json.loads(
        (Path(__file__).resolve().parents[1] / "reports/hw07/cases/agent_tasks.json").read_text()
    )["tasks"][2]
    search_call = call("search_rentals", {"query": task["query"], "limit": 5}, "search")
    details = [
        call("get_rental", {"rental_id": row["id"]}, str(row["id"]))
        for row in task["expected"]["rentals"]
    ]
    batches = [[search_call, *details]] if guessed else [[search_call], details]
    replies = [
        CompletionResult("", TokenUsage(1, 1, 2), AIMessage(content="", tool_calls=batch))
        for batch in batches
    ]
    model = Model([*replies, response(json.dumps(task["expected"]))])
    stream = io.StringIO()

    def executor(name, inputs):
        rows = task["expected"]["rentals"]
        data = (
            {
                "items": [{k: v for k, v in row.items() if k != "description"} for row in rows],
                "returnedCount": 2,
                "limit": 5,
            }
            if name == "search_rentals"
            else next(row for row in rows if row["id"] == inputs["rental_id"])
        )
        return json.dumps({"ok": True, "data": data, "error": None})

    result = run_agent(task["prompt"], task=task, model=model, executor=executor, log_stream=stream)
    assert result.stop_reason == ("verification_failed" if guessed else "success")
    assert result.tool_calls == 3
    terminal = json.loads(stream.getvalue().splitlines()[-1])
    assert terminal["verification"]["unsupported_claims"] == []
    if guessed:
        assert "trace.chain" in terminal["verification"]["failures"]
