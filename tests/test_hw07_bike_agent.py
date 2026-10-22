"""Controlled model responses exercise the real framework/tools, not model measurements."""

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from src.bikeshare.agent import BikeConfig, run_bike_agent
from src.model_client import CompletionResult, TokenUsage

FIXTURES = Path(__file__).parent / "fixtures/hw07_bike_policy.json"


def csv_input():
    fields = "ride_id rideable_type started_at ended_at start_station_name start_station_id end_station_name end_station_id start_lat start_lng end_lat end_lng member_casual scenario_account_id coverage_start coverage_end scenario_account_assumption".split()
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for ride, account, start, end in [
        ("r1", "a", "10:00:00", "10:01:00"),
        ("r2", "b", "11:00:00", "11:15:00"),
    ]:
        row = dict.fromkeys(fields, "")
        row.update(
            ride_id=ride,
            rideable_type="classic_bike",
            started_at="2024-01-01 " + start,
            ended_at="2024-01-01 " + end,
            scenario_account_id=account,
            coverage_start="2024-01-01T00:00:00",
            coverage_end="2024-01-31T00:00:00",
            scenario_account_assumption="hypothetical account; not observed rider history",
        )
        writer.writerow(row)
    return stream.getvalue().encode()


class Model:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.histories = []

    def complete(self, messages, tools=None):
        self.histories.append(list(messages))
        raw = next(self.replies)
        return CompletionResult(raw.content, TokenUsage(100, 20, 120, True), raw)


def call(name, args, identifier):
    return {"name": name, "args": args, "id": identifier, "type": "tool_call"}


def scripted(answer=None):
    snapshots = json.loads(FIXTURES.read_text())
    first = [
        call(
            "policy_retriever",
            {
                "url": s["url"],
                "query": "membership classic unlock included minutes rounding prices",
                "k": 5,
            },
            f"policy-{i}",
        )
        for i, s in enumerate(snapshots)
    ]
    first.append(
        call(
            "csv_sql",
            {
                "sql": "SELECT COUNT(*) AS rides, COUNT(DISTINCT scenario_account_id) AS accounts, SUM(billable_minutes) AS billed_minutes FROM trips"
            },
            "sql-1",
        )
    )
    answer = answer or {
        "decision": "Pay Per Ride/Minute",
        "pay_per_use_total": "4.40",
        "membership_total": "50.00",
        "justification": "Pay per use costs $4.40 for 2 rides across 2 hypothetical accounts [2]. The membership alternative totals $50.00 including ride charges for 2 separate accounts [3]. Each account pays $25.00 for a 30-day membership with 45 included classic minutes per ride and $0.05 per extra minute [3]. Ride minutes are rounded up separately for every ride [3]. Pay Per Ride/Minute is the recommendation for this assumed 30-day cohort [2][3].",
    }
    return snapshots, Model(
        [
            AIMessage(content="", tool_calls=first),
            AIMessage(
                content="",
                tool_calls=[
                    call("calculator", {"expression": "2+0.15*16", "units": "USD"}, "calc-pay"),
                    call(
                        "calculator", {"expression": "2*25+0*0.05", "units": "USD"}, "calc-member"
                    ),
                ],
            ),
            AIMessage(content=json.dumps(answer)),
        ]
    )


def execute(tmp_path, *, answer=None, config=None):
    snapshots, model = scripted(answer)
    lookup = {s["url"]: s for s in snapshots}
    result = run_bike_agent(
        csv_input(),
        snapshots[0]["url"],
        model=model,
        fetcher=lookup.__getitem__,
        config=config or BikeConfig(),
        run_id="a" * 32,
        user_id=17,
        run_dir=tmp_path,
    )
    return result, model


def test_framework_uses_actual_tools_and_verifies_costs(tmp_path):
    result, model = execute(tmp_path)
    assert result["verification"]["passed"]
    assert result["decision"] == "Pay Per Ride/Minute"
    assert result["pay_per_use_total"] == "4.40"
    assert result["membership_total"] == "50.00"
    assert result["metrics"]["model_requests"] == 3
    assert result["metrics"]["stop_reason"] == "success"
    assert {e["name"] for e in result["trace"] if e["event"] == "tool_result"} == {
        "csv_sql",
        "calculator",
        "policy_retriever",
    }
    second = model.histories[1]
    assistant = next(m for m in second if isinstance(m, AIMessage) and m.tool_calls)
    tool_ids = {getattr(m, "tool_call_id", None) for m in second}
    assert {c["id"] for c in assistant.tool_calls} <= tool_ids
    assert result["input_sha256"] == hashlib.sha256(csv_input()).hexdigest()


def test_wrong_model_cost_is_rejected_without_rewriting_the_model_answer(tmp_path):
    answer = {
        "decision": "Buy Monthly Membership",
        "pay_per_use_total": "400",
        "membership_total": "1",
        "justification": "Membership wins [1]. It costs $1 [2]. The alternative is $400 [1].",
    }
    result, _ = execute(tmp_path, answer=answer)
    assert not result["verification"]["passed"]
    assert result["decision"] is None
    assert json.loads(result["model_answer"]) == answer
    assert result["metrics"]["stop_reason"] == "human_review"


def test_a_tool_batch_cannot_exceed_shared_hard_limit(tmp_path):
    result, model = execute(tmp_path, config=BikeConfig(max_tools=2))
    assert result["metrics"]["stop_reason"] == "budget_exhausted"
    assert result["metrics"]["tool_calls"] == 0
    assert len(model.histories) == 1


def test_premature_final_text_fails_without_tools(tmp_path):
    snapshots = json.loads(FIXTURES.read_text())
    model = Model([AIMessage(content="Membership is always better.")])
    result = run_bike_agent(
        csv_input(),
        snapshots[0]["url"],
        model=model,
        fetcher=lambda _: pytest.fail("No policy tool called"),
        config=BikeConfig(),
        run_id="b" * 32,
        user_id=18,
        run_dir=tmp_path,
    )
    assert not result["verification"]["passed"]
    assert result["metrics"]["tool_calls"] == 0
    assert result["metrics"]["stop_reason"] == "human_review"


def test_correct_structured_totals_cannot_hide_false_justification(tmp_path):
    answer = {
        "decision": "Pay Per Ride/Minute",
        "pay_per_use_total": "4.40",
        "membership_total": "50.00",
        "justification": "Membership costs $999 and covers all citywide riders [3]. Casual rides are free [2]. Buy Monthly Membership is cheaper [2][3].",
    }
    result, _ = execute(tmp_path, answer=answer)
    assert not result["verification"]["passed"]
    assert result["decision"] is None
    assert result["metrics"]["stop_reason"] == "human_review"


def test_model_request_exception_charges_unknown_usage_and_stops(tmp_path):
    class FailingModel:
        def complete(self, messages, tools=None):
            raise TimeoutError("controlled unavailable provider")

    result = run_bike_agent(
        csv_input(),
        "https://capitalbikeshare.com/pricing",
        model=FailingModel(),
        config=BikeConfig(),
        run_id="c" * 32,
        user_id=19,
        run_dir=tmp_path,
        fetcher=lambda _: pytest.fail("No tool should run after request failure"),
    )
    assert result["metrics"]["stop_reason"] == "human_review"
    assert result["metrics"]["tool_calls"] == 0
    assert result["metrics"]["model_requests"] == 1
    assert result["metrics"]["total_tokens"] is None
    usages = [e["budget"] for e in result["trace"] if e["event"] == "usage"]
    assert usages[0]["charged_tokens"] > 0
    assert usages[0]["unknown_usage_calls"] == 1


@pytest.mark.parametrize("amount", ["$4.40", "4.40"])
def test_correct_currency_formatting_preserves_original_answer(tmp_path, amount):
    _, model = scripted()
    answer = json.loads(list(model.replies)[-1].content)
    answer["pay_per_use_total"] = amount
    result, _ = execute(tmp_path, answer=answer)
    assert result["verification"]["passed"]
    assert json.loads(result["model_answer"])["pay_per_use_total"] == amount


def test_subcent_rate_claim_cannot_be_rounded_into_a_verified_fact(tmp_path):
    _, model = scripted()
    answer = json.loads(list(model.replies)[-1].content)
    answer["justification"] = answer["justification"].replace("$0.05 per extra", "$0.054 per extra")
    result, _ = execute(tmp_path, answer=answer)
    assert not result["verification"]["passed"]
    assert "answer.justification_claims" in result["verification"]["failures"]
    assert json.loads(result["model_answer"]) == answer
