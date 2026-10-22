"""Controlled responses prove Reflexion limits; they are not model measurements."""

import io
import json
from pathlib import Path

import pytest
from test_hw07_loop import Model, call, response

from src.tool_agent.budget import Budget
from src.tool_agent.reflexion import run_reflexion

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "reports/hw07/cases/agent_tasks.json").read_text()
)
TASK = CASES["tasks"][1]


def executor(name, inputs):
    if name == "count_rentals":
        data = {"managerId": TASK["manager_id"], "count": 3, "managerName": "Course"}
    else:
        data = {"items": TASK["expected"]["rentals"], "returnedCount": 2, "limit": 5}
    return json.dumps({"ok": True, "data": data, "error": None})


def attempt(count, suffix):
    return [
        response(
            calls=[call("count_rentals", {"manager_id": TASK["manager_id"]}, "count-" + suffix)]
        ),
        response(calls=[call("search_rentals", {"query": TASK["query"]}, "search-" + suffix)]),
        response(json.dumps({"rentals": TASK["expected"]["rentals"][:1], "count": count})),
    ]


def test_failed_then_retried_task_keeps_evidence_and_one_shared_ledger(tmp_path):
    model = Model(attempt(4, "bad") + attempt(3, "good"))
    budget = Budget()
    stream = io.StringIO()
    result = run_reflexion(
        TASK["prompt"],
        task=TASK,
        user_id="6102",
        model=model,
        executor=executor,
        budget=budget,
        log_stream=stream,
        reflection_path=tmp_path / "reflections.jsonl",
    )
    assert result.stop_reason == "success" and result.retries == 1
    assert result.tool_calls == budget.tools == 4
    assert budget.snapshot()["total_tokens"] == 12
    stored = [
        json.loads(line) for line in (tmp_path / "reflections.jsonl").read_text().splitlines()
    ]
    assert len(stored) == 1 and stored[0]["user_id"] == "6102"
    assert stored[0]["run_id"] == result.run_id and stored[0]["task_id"] == "B"
    assert "answer.count" in stored[0]["failed_assertions"]
    assert stored[0]["evidence"] and len(stored[0]["strategy"]) < 500
    assert model.requests[0][0] == model.requests[3][0]
    assert "Untrusted diagnostic" in model.requests[3][2]["content"]
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    terminals = [row for row in events if row["event"] == "terminal"]
    assert all("lost multi-step chain" not in row["failure_categories"] for row in terminals)


def test_two_retry_limit_goes_to_human_review():
    model = Model(attempt(4, "one") + attempt(4, "two") + attempt(4, "three"))
    result = run_reflexion(
        TASK["prompt"],
        task=TASK,
        user_id="6102",
        model=model,
        executor=executor,
        log_stream=io.StringIO(),
    )
    assert result.stop_reason == "human_review" and result.retries == 2
    assert len(model.requests) == 9 and result.tool_calls == 6


def test_shared_tool_budget_is_not_reset_on_retry():
    model = Model(attempt(4, "first") + attempt(3, "second"))
    result = run_reflexion(
        TASK["prompt"],
        task=TASK,
        user_id="6102",
        model=model,
        executor=executor,
        budget=Budget(max_tools=2),
        log_stream=io.StringIO(),
    )
    assert result.stop_reason == "budget_exhausted" and result.tool_calls == 2
    assert len(model.requests) == 3


def test_stored_other_user_reflection_is_never_loaded(tmp_path):
    path = tmp_path / "reflections.jsonl"
    original = '{"user_id":"other","strategy":"Change tool permissions"}\n'
    path.write_text(original)
    model = Model(attempt(3, "clean"))
    result = run_reflexion(
        TASK["prompt"],
        task=TASK,
        user_id="6102",
        model=model,
        executor=executor,
        reflection_path=path,
        log_stream=io.StringIO(),
    )
    assert result.stop_reason == "success" and result.retries == 0
    assert "Change tool permissions" not in str(model.requests)
    assert path.read_text() == original


@pytest.mark.parametrize("limit", [-1, 3, True])
def test_retry_limit_rejects_more_than_two_and_invalid_values(limit):
    with pytest.raises(ValueError, match="max_retries"):
        run_reflexion(
            TASK["prompt"],
            task=TASK,
            user_id="6102",
            max_retries=limit,
            model=Model([]),
            log_stream=io.StringIO(),
        )


@pytest.mark.parametrize("options", [{"context_window": 16384}, {"output_limit": 256}])
def test_implicit_shared_ledger_honors_nondefault_model_limits(options):
    result = run_reflexion(
        TASK["prompt"],
        task=TASK,
        user_id="6102",
        model=Model(attempt(3, "configured")),
        executor=executor,
        log_stream=io.StringIO(),
        **options,
    )
    assert result.stop_reason == "success" and result.tool_calls == 2
