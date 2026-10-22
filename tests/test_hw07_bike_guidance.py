"""Controlled observations verify phase hints; these are not model measurements."""

import json
from pathlib import Path

import pytest

from src.bikeshare.guidance import next_action
from src.bikeshare.policies import MEMBERSHIP_URL, SINGLE_TRIP_URL


@pytest.mark.parametrize(
    "accounts,minutes,overage,pay,member,decision",
    [
        (10, 7351, 117, 1602.65, 255.85, "Buy Monthly Membership"),
        (125, 1935, 0, 790.25, 3125, "Pay Per Ride/Minute"),
    ],
)
def test_final_hint_uses_both_observed_calculations(
    accounts, minutes, overage, pay, member, decision
):
    snapshots = json.loads((Path(__file__).parent / "fixtures/hw07_bike_policy.json").read_text())
    urls = ["https://capitalbikeshare.com/pricing", SINGLE_TRIP_URL, MEMBERSHIP_URL]
    events = [
        {"name": "policy_retriever", "inputs": {"url": url}, "result": {"success": True}}
        for url in urls
    ]
    aggregate = {
        "rides": 500,
        "accounts": accounts,
        "classic_rides": 500,
        "ebike_rides": 0,
        "classic_minutes": minutes,
        "ebike_minutes": 0,
        "classic_overage_minutes": overage,
    }
    events.append(
        {
            "name": "csv_sql",
            "inputs": {},
            "result": {"success": True, "data": {"rows": [aggregate]}},
        }
    )
    cache = {s["url"]: s for s in snapshots}
    assert "use calculator" in next_action(events, cache, urls)
    events.append(
        {
            "name": "calculator",
            "inputs": {"expression": f"500*1.00+{minutes}*0.15+0*1.00+0*0.35"},
            "result": {"success": True, "data": {"value": pay}},
        }
    )
    assert "use calculator" in next_action(events, cache, urls)
    events.append(
        {
            "name": "calculator",
            "inputs": {"expression": f"{accounts}*25.00+{overage}*0.05+0*0.15"},
            "result": {"success": True, "data": {"value": member}},
        }
    )
    hint = next_action(events, cache, urls)
    assert "decision exactly " + decision in hint
    assert "actual calculator observations" in hint
