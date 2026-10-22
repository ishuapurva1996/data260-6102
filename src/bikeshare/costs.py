from collections import defaultdict
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def _money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def calculate_costs(dataset, policy):
    """Round each ride's minutes and money before summing account memberships."""
    if policy["rounding"] != "ceil_per_ride" or policy["membership_days"] != 30:
        raise ValueError("Unsupported pricing rounding or membership coverage.")
    rates = {
        name: Decimal(policy[name])
        for name in (
            "membership_fee",
            "classic_overage_per_minute",
            "casual_unlock",
            "casual_classic_per_minute",
            "member_ebike_per_minute",
            "casual_ebike_per_minute",
            "member_unlock",
        )
    }
    included = policy["classic_included_minutes"]
    accounts, weeks = defaultdict(_bucket), defaultdict(_bucket)
    total = _bucket()
    for row in dataset["rows"]:
        minutes = row["billable_minutes"]
        classic = row["rideable_type"] == "classic_bike"
        overage = max(minutes - included, 0) if classic else 0
        casual = (
            rates["casual_unlock"]
            + minutes * rates["casual_classic_per_minute" if classic else "casual_ebike_per_minute"]
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        residual = (
            rates["member_unlock"]
            + (
                overage * rates["classic_overage_per_minute"]
                if classic
                else minutes * rates["member_ebike_per_minute"]
            )
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        start = datetime.fromisoformat(row["started_at"])
        week_start = (start.date() - timedelta(days=start.weekday())).isoformat()
        duration_seconds = Decimal(str(row["duration_seconds"]))
        for bucket in (total, accounts[row["scenario_account_id"]], weeks[week_start]):
            bucket["ride_count"] += 1
            bucket["duration_seconds"] += duration_seconds
            bucket["billed_minutes"] += minutes
            bucket["classic_overage_minutes"] += overage
            bucket["classic_overage_ride_count"] += overage > 0
            bucket["classic_ride_count"] += classic
            bucket["ebike_ride_count"] += not classic
            bucket["pay_per_use"] += casual
            bucket["member_residual"] += residual
    account_count = len(accounts)
    fee_total = rates["membership_fee"] * account_count
    member_total = fee_total + total["member_residual"]
    savings = total["pay_per_use"] - member_total
    coverage_start = datetime.fromisoformat(dataset["coverage_start"])
    fee_week = (coverage_start.date() - timedelta(days=coverage_start.weekday())).isoformat()
    weeks[fee_week]
    weekly = []
    for week_start, bucket in sorted(weeks.items()):
        fee = fee_total if week_start == fee_week else Decimal(0)
        weekly.append(
            {
                "week_start": week_start,
                **_public_bucket(bucket),
                "allocated_membership_fee": _money(fee),
                "membership_total": _money(fee + bucket["member_residual"]),
            }
        )
    per_account = [
        {
            "account_id": account,
            **_public_bucket(bucket),
            "membership_fee": _money(rates["membership_fee"]),
            "membership_total": _money(rates["membership_fee"] + bucket["member_residual"]),
        }
        for account, bucket in sorted(accounts.items())
    ]
    average_saving = (total["pay_per_use"] - total["member_residual"]) / total["ride_count"]
    threshold = (rates["membership_fee"] / average_saving) if average_saving > 0 else None
    weak_rides = (
        int(threshold.to_integral_value(rounding=ROUND_CEILING)) if threshold is not None else None
    )
    strict_rides = int(threshold) + 1 if threshold is not None else None
    average_minutes = Decimal(total["billed_minutes"]) / total["ride_count"]
    rides_per_account = [value["ride_count"] for value in accounts.values()]
    return {
        "row_count": total["ride_count"],
        "account_count": account_count,
        "coverage_start": dataset["coverage_start"],
        "coverage_end": dataset["coverage_end"],
        "summary": {
            key: total[key]
            for key in (
                "billed_minutes",
                "classic_overage_minutes",
                "classic_overage_ride_count",
                "classic_ride_count",
                "ebike_ride_count",
            )
        }
        | {
            "duration_seconds": float(total["duration_seconds"]),
            "average_duration_minutes": _money(
                total["duration_seconds"] / (60 * total["ride_count"])
            ),
        },
        "pay_per_use_total": _money(total["pay_per_use"]),
        "membership_fee_total": _money(fee_total),
        "membership_residual_total": _money(total["member_residual"]),
        "membership_total": _money(member_total),
        "savings": _money(savings),
        "decision": "Buy Monthly Membership" if savings > 0 else "Pay Per Ride/Minute",
        "weekly": weekly,
        "per_account": per_account,
        "break_even": {
            "rides_at_sample_mix": weak_rides,
            "strictly_cheaper_rides_at_sample_mix": strict_rides,
            "minutes_at_sample_mix": _money(weak_rides * average_minutes)
            if weak_rides is not None
            else None,
            "actual_rides_per_account": {
                "min": min(rides_per_account),
                "max": max(rides_per_account),
            },
            "average_saving_per_ride": format(average_saving, ".6f"),
            "method": "Per account: membership fee / sample-average (casual ride cost minus member residual). Ceiling gives weak break-even; ties recommend Pay Per Ride/Minute. The strict threshold is floor + 1. Minutes use sample-average billed minutes. This repeated sample-mix approximation is not a guarantee for every ordering of heterogeneous rides.",
        },
        "assumptions": dataset["assumptions"]
        + policy["assumptions"]
        + [
            "The entire membership fee is allocated to the calendar week containing coverage_start; later weeks include only residual charges.",
            "Original member_casual describes the public source trip and is not a scenario identity or the product selected for this counterfactual comparison.",
            "A tie recommends Pay Per Ride/Minute; comparison savings are pay-per-use minus membership total.",
        ],
    }


def _bucket():
    return {
        "ride_count": 0,
        "duration_seconds": Decimal(0),
        "billed_minutes": 0,
        "classic_overage_minutes": 0,
        "classic_overage_ride_count": 0,
        "classic_ride_count": 0,
        "ebike_ride_count": 0,
        "pay_per_use": Decimal(0),
        "member_residual": Decimal(0),
    }


def _public_bucket(bucket):
    count = bucket["ride_count"]
    return {
        "ride_count": count,
        "average_duration_minutes": _money(bucket["duration_seconds"] / (60 * count))
        if count
        else "0.00",
        "billed_minutes": bucket["billed_minutes"],
        "classic_overage_minutes": bucket["classic_overage_minutes"],
        "pay_per_use": _money(bucket["pay_per_use"]),
        "member_residual": _money(bucket["member_residual"]),
    }
