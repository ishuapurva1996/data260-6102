"""Money and account boundaries are independent of model-generated SQL or arithmetic."""

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "reports/hw07/cases/bikeshare"
ORIGINAL = [
    "ride_id",
    "rideable_type",
    "started_at",
    "ended_at",
    "start_station_name",
    "start_station_id",
    "end_station_name",
    "end_station_id",
    "start_lat",
    "start_lng",
    "end_lat",
    "end_lng",
    "member_casual",
]
SCENARIO = [
    "scenario_account_id",
    "coverage_start",
    "coverage_end",
    "scenario_account_assumption",
]


def csv_bytes(durations=(2700,), accounts=None, bike="classic_bike"):
    rows = []
    for index, seconds in enumerate(durations):
        start = datetime(2024, 1, 1, 1) + timedelta(hours=index * 2)
        row = dict.fromkeys(ORIGINAL, "")
        row.update(
            ride_id=f"ride-{index}",
            rideable_type=bike,
            started_at=start.isoformat(),
            ended_at=(start + timedelta(seconds=seconds)).isoformat(),
            member_casual="member",
            scenario_account_id=(accounts or ["account-1"] * len(durations))[index],
            coverage_start="2024-01-01T00:00:00",
            coverage_end="2024-01-31T00:00:00",
            scenario_account_assumption="hypothetical account; not observed rider history",
        )
        rows.append(row)
    return encode(rows)


def encode(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def snapshots():
    texts = [
        (
            "https://capitalbikeshare.com/pricing/30-day",
            "30-Day Membership. You can take as many 45-minute trips on classic bikes as you "
            "want while your membership is active. Ride longer than 45 minutes and pay "
            "$0.05/minute. A 30-Day membership means you don't pay to unlock bikes and enjoy "
            "a discounted rate of $0.15/min on ebikes. $25 / 30-Days. "
            "First 45 minutes included.",
        ),
        (
            "https://capitalbikeshare.com/pricing/single-trip",
            "The Single Trip costs $1 to unlock and $0.15/min on a classic bike or $0.35/min "
            "on an ebike. Ebike parking is free at Capital Bikeshare stations.",
        ),
        (
            "https://help.capitalbikeshare.com/hc/en-us/articles/360039401111-30-Day-Membership",
            "$25 / 30-Day Membership includes: Unlimited 45-minute rides on classic bikes for "
            "30 days from purchase. Members pay $0.15 per minute for ebikes and avoid unlock "
            "fees. If you need more time than what’s covered, pay $0.05 per minute. All per "
            "minute ride prices are rounded up to the nearest minute. Please note that your "
            "ride will incur standard sales taxes according to the start location of your ride.",
        ),
    ]
    return [
        {
            "url": url,
            "text": text,
            "captured_at": "2026-10-22T06:45:26+00:00",
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
        for url, text in texts
    ]


def policy():
    from src.bikeshare.pricing import parse_policy

    return parse_policy(snapshots())


def dataset(payload):
    from src.bikeshare.trips import parse_trips

    return parse_trips(payload)


def calculate(payload):
    from src.bikeshare.costs import calculate_costs

    return calculate_costs(dataset(payload), policy())


@pytest.mark.parametrize(
    "seconds, billed, extra, casual, residual",
    [
        (1, 1, 0, "1.15", "0.00"),
        (2700, 45, 0, "7.75", "0.00"),
        (2701, 46, 1, "7.90", "0.05"),
        (2760, 46, 1, "7.90", "0.05"),
    ],
)
def test_rounding_and_included_minutes_apply_per_ride(seconds, billed, extra, casual, residual):
    result = calculate(csv_bytes((seconds,)))
    assert result["summary"]["billed_minutes"] == billed
    assert result["summary"]["classic_overage_minutes"] == extra
    assert result["pay_per_use_total"] == casual
    assert result["membership_fee_total"] == "25.00"
    assert result["membership_residual_total"] == residual


def test_each_account_pays_one_fee_and_small_rides_are_not_rounded_together():
    same = calculate(csv_bytes((1, 1), ["a", "a"]))
    separate = calculate(csv_bytes((1, 1), ["a", "b"]))
    assert same["pay_per_use_total"] == separate["pay_per_use_total"] == "2.30"
    assert same["membership_total"] == "25.00"
    assert separate["membership_total"] == "50.00"
    assert len(separate["per_account"]) == 2


def test_ebike_base_transportation_excludes_unobserved_parking_explicitly():
    result = calculate(csv_bytes((61,), bike="electric_bike"))
    assert result["pay_per_use_total"] == "1.70"
    assert result["membership_residual_total"] == "0.30"
    assert any(
        "parking" in item.lower() and "exclud" in item.lower() for item in result["assumptions"]
    )


@pytest.mark.parametrize("field", SCENARIO)
def test_account_and_coverage_assumptions_cannot_be_invented(field):
    rows = list(csv.DictReader(io.StringIO(csv_bytes().decode())))
    rows[0].pop(field)
    with pytest.raises(ValueError, match="account|coverage|assumption"):
        dataset(encode(rows))


@pytest.mark.parametrize(
    "change", ["long_window", "mixed_window", "out_of_window", "overlap", "turnaround"]
)
def test_unusable_account_windows_are_rejected(change):
    rows = list(csv.DictReader(io.StringIO(csv_bytes((120, 120)).decode())))
    if change == "long_window":
        for row in rows:
            row["coverage_end"] = "2024-02-01T00:00:00"
    elif change == "mixed_window":
        rows[1]["coverage_start"] = "2024-01-02T00:00:00"
        rows[1]["coverage_end"] = "2024-02-01T00:00:00"
    elif change == "out_of_window":
        rows[0]["started_at"] = "2023-12-31T23:59:00"
    elif change == "overlap":
        rows[1]["started_at"] = "2024-01-01T01:01:00"
        rows[1]["ended_at"] = "2024-01-01T01:03:00"
    else:
        rows[1]["started_at"] = "2024-01-01T01:03:00"
        rows[1]["ended_at"] = "2024-01-01T01:05:00"
    with pytest.raises(ValueError, match="30.day|coverage|overlap|2.minute"):
        dataset(encode(rows))


def test_sqlite_preserves_original_text_and_exposes_derived_values():
    from src.bikeshare.trips import open_trip_database

    parsed = dataset(csv_bytes((2701,)))
    connection = open_trip_database(parsed)
    try:
        observed = connection.execute(
            "SELECT ride_id, member_casual, duration_seconds, billable_minutes FROM trips"
        ).fetchone()
        assert tuple(observed) == ("ride-0", "member", 2701, 46)
    finally:
        connection.close()


def test_policy_is_derived_from_verified_snapshot_bytes_and_has_citations():
    result = policy()
    assert result["membership_fee"] == "25.00"
    assert result["classic_included_minutes"] == 45
    assert result["rounding"] == "ceil_per_ride"
    assert result["casual_unlock"] == "1.00"
    assert len(result["citations"]) >= 3
    assert all(
        item["excerpt"] and item["sha256"] and item["captured_at"] for item in result["citations"]
    )


def test_official_product_specific_help_can_supply_complete_membership_policy():
    from src.bikeshare.pricing import parse_policy

    source = snapshots()
    result = parse_policy(source[1:])
    assert result["membership_fee"] == "25.00"
    assert result["classic_included_minutes"] == 45
    assert result["classic_overage_per_minute"] == "0.05"
    assert result["member_ebike_per_minute"] == "0.15"
    assert result["member_unlock"] == "0.00"
    assert result["rounding"] == "ceil_per_ride"
    with pytest.raises(ValueError, match="30-day|membership"):
        parse_policy(source[1:2])


@pytest.mark.parametrize(
    "kind", ["missing", "tampered", "contradiction", "overage_boundary", "unofficial"]
)
def test_missing_or_contradictory_policy_never_uses_planning_prices(kind):
    from src.bikeshare.pricing import parse_policy

    source = snapshots()
    if kind == "missing":
        source = source[:1]
    elif kind == "tampered":
        source[0]["text"] += " altered"
    elif kind == "contradiction":
        source[2]["text"] = source[2]["text"].replace("45-minute", "30-minute")
        source[2]["sha256"] = hashlib.sha256(source[2]["text"].encode()).hexdigest()
    elif kind == "overage_boundary":
        source[0]["text"] = source[0]["text"].replace("longer than 45", "longer than 30")
        source[0]["sha256"] = hashlib.sha256(source[0]["text"].encode()).hexdigest()
    else:
        source[0]["url"] = "https://unofficial.example/pricing/30-day"
    with pytest.raises(ValueError):
        parse_policy(source)


@pytest.mark.parametrize(
    "name, accounts, minutes, extra, payg, member, decision, threshold",
    [
        ("frequent", 10, 7351, 117, "1602.65", "255.85", "Buy Monthly Membership", 8),
        ("occasional", 125, 1935, 0, "790.25", "3125.00", "Pay Per Ride/Minute", 16),
    ],
)
def test_genuine_500_row_scenarios_match_independent_integer_cent_expectations(
    name, accounts, minutes, extra, payg, member, decision, threshold
):
    payload = (CASES / f"{name}.csv").read_bytes()
    result = calculate(payload)
    assert result["row_count"] == 500
    assert result["account_count"] == accounts
    assert result["summary"]["billed_minutes"] == minutes
    assert result["summary"]["classic_overage_minutes"] == extra
    assert result["pay_per_use_total"] == payg
    assert result["membership_total"] == member
    assert result["decision"] == decision
    assert result["break_even"]["rides_at_sample_mix"] == threshold
    assert sum(Decimal(row["pay_per_use"]) for row in result["weekly"]) == Decimal(payg)
    assert sum(Decimal(row["membership_total"]) for row in result["weekly"]) == Decimal(member)
    assert sum(row["ride_count"] for row in result["weekly"]) == 500
    assert sum(Decimal(row["membership_total"]) for row in result["per_account"]) == Decimal(member)
    manifest = json.loads((CASES / "manifest.json").read_text())
    assert manifest["scenarios"][name]["sha256"] == hashlib.sha256(payload).hexdigest()
    rows = dataset(payload)["rows"]
    assert all(row["source_csv_sha256"] == manifest["source"]["csv_sha256"] for row in rows)
    assert len({row["source_row_number"] for row in rows}) == 500
    assert all("not observed" in row["scenario_account_assumption"] for row in rows)
    originals = manifest["source"]["original_fields"]
    provenance = {
        row["ride_id"]: row for row in manifest["scenarios"][name]["original_row_provenance"]
    }
    for row in rows:
        original_values = {key: row[key] for key in originals}
        digest = hashlib.sha256(
            json.dumps(
                original_values, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode()
        ).hexdigest()
        assert digest == provenance[row["ride_id"]]["original_values_sha256"]
        assert int(row["source_row_number"]) == provenance[row["ride_id"]]["source_row_number"]


def test_tie_uses_pay_per_use_and_distinguishes_weak_from_strict_break_even():
    selected_policy = policy()
    selected_policy["membership_fee"] = "1.15"
    from src.bikeshare.costs import calculate_costs

    result = calculate_costs(dataset(csv_bytes((1,))), selected_policy)
    assert result["decision"] == "Pay Per Ride/Minute"
    assert result["savings"] == "0.00"
    assert result["break_even"]["rides_at_sample_mix"] == 1
    assert result["break_even"]["strictly_cheaper_rides_at_sample_mix"] == 2


def test_naive_window_crossing_dst_requires_explicit_offsets():
    rows = list(csv.DictReader(io.StringIO(csv_bytes().decode())))
    rows[0].update(
        started_at="2024-03-10T01:55:00",
        ended_at="2024-03-10T03:05:00",
        coverage_start="2024-03-01T00:00:00",
        coverage_end="2024-03-31T00:00:00",
    )
    with pytest.raises(ValueError, match="daylight-saving"):
        dataset(encode(rows))
