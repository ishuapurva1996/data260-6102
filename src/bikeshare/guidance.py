"""Trusted phase hints use captured policy facts and actual SQL observations only."""

import re
from decimal import Decimal

from .policies import MEMBERSHIP_URL, SINGLE_TRIP_URL
from .pricing import parse_policy

RATIONALE = (
    "Pay per use costs ${pay_per_use_total} for {row_count} rides across {account_count} hypothetical accounts {single_source}. "
    "The membership alternative totals ${membership_total} including ride charges for {account_count} separate accounts {member_source}. "
    "Each account pays ${membership_fee} for a 30-day membership with {included_minutes} included classic minutes per ride and ${overage_rate} per extra minute {member_source}. "
    "Ride minutes are rounded up separately for every ride {member_source}. "
    "{decision} is the recommendation for this assumed 30-day cohort {single_source}{member_source}."
)


def rationale_template(urls):
    return RATIONALE.replace("{single_source}", f"[{urls.index(SINGLE_TRIP_URL) + 1}]").replace(
        "{member_source}", f"[{urls.index(MEMBERSHIP_URL) + 1}]"
    )


def expected_rationale(reference, policy, urls):
    return rationale_template(urls).format(
        **{
            key: reference[key]
            for key in (
                "pay_per_use_total",
                "membership_total",
                "row_count",
                "account_count",
                "decision",
            )
        },
        membership_fee=format(Decimal(policy["membership_fee"]), ".2f"),
        included_minutes=policy["classic_included_minutes"],
        overage_rate=format(Decimal(policy["classic_overage_per_minute"]), ".2f"),
    )


def normalize_rationale(value):
    value = re.sub(
        r"\$([0-9][0-9,]*(?:\.[0-9]+)?)",
        lambda m: "$" + format(Decimal(m[1].replace(",", "")).normalize(), "f"),
        value,
    )
    return re.sub(r"\]\s+\[", "][", " ".join(value.split()))


def next_action(observations, snapshots, urls):
    """Guide model choices without executing a tool or inserting a tool result."""
    good = [e for e in observations if e["result"].get("success")]
    observed = {e["inputs"].get("url") for e in good if e["name"] == "policy_retriever"}
    missing = [url for url in urls if url not in observed]
    if missing:
        return (
            'NEXT: retrieve these URLs with native policy_retriever calls, k=3, query "classic unlock per minute membership included overage rounded up": '
            + ", ".join(missing)
        )
    try:
        policy = parse_policy(list(snapshots.values()))
    except ValueError:
        return "Pricing facts remain incomplete. Retrieve complete classic and ebike fees, membership allowance, and rounding passages; never invent a price."
    fields = {
        "rides",
        "accounts",
        "classic_rides",
        "ebike_rides",
        "classic_minutes",
        "ebike_minutes",
        "classic_overage_minutes",
    }
    aggregate = None
    for event in good:
        if event["name"] == "csv_sql":
            rows = event["result"]["data"]["rows"]
            if (
                len(rows) == 1
                and fields <= set(rows[0])
                and all(type(rows[0][key]) is int and rows[0][key] >= 0 for key in fields)
            ):
                aggregate = rows[0]
    if aggregate is None:
        allowance = policy["classic_included_minutes"]
        sql = (
            "SELECT COUNT(*) AS rides, COUNT(DISTINCT scenario_account_id) AS accounts, "
            "SUM(CASE WHEN rideable_type='classic_bike' THEN 1 ELSE 0 END) AS classic_rides, "
            "SUM(CASE WHEN rideable_type='electric_bike' THEN 1 ELSE 0 END) AS ebike_rides, "
            "SUM(CASE WHEN rideable_type='classic_bike' THEN billable_minutes ELSE 0 END) AS classic_minutes, "
            "SUM(CASE WHEN rideable_type='electric_bike' THEN billable_minutes ELSE 0 END) AS ebike_minutes, "
            f"SUM(CASE WHEN rideable_type='classic_bike' THEN MAX(billable_minutes-{allowance},0) ELSE 0 END) AS classic_overage_minutes FROM trips"
        )
        return (
            "NEXT: call csv_sql with this valid aggregate using the observed allowance, then WAIT for its observation: "
            + sql
        )
    a = aggregate
    expressions = {
        "PAYG": f"{a['classic_rides']}*{policy['casual_unlock']}+{a['classic_minutes']}*{policy['casual_classic_per_minute']}+{a['ebike_rides']}*{policy['casual_unlock']}+{a['ebike_minutes']}*{policy['casual_ebike_per_minute']}",
        "MEMBER": f"{a['accounts']}*{policy['membership_fee']}+{a['classic_overage_minutes']}*{policy['classic_overage_per_minute']}+{a['ebike_minutes']}*{policy['member_ebike_per_minute']}",
    }
    totals = {}
    for event in good:
        if event["name"] != "calculator":
            continue
        expression = re.sub(r"\s+", "", event["inputs"]["expression"])
        for label, expected in expressions.items():
            if expression == expected:
                totals[label] = Decimal(str(event["result"]["data"]["value"])).quantize(
                    Decimal("0.01")
                )
    missing_calculations = [
        f"{label} {value}" for label, value in expressions.items() if label not in totals
    ]
    if missing_calculations:
        return (
            "NEXT: use calculator for these numeric expressions derived from the actual SQL observation and captured policy: "
            + "; ".join(missing_calculations)
            + ". Then WAIT for their observations. Do not substitute ride counts for minutes or share fees across accounts."
        )
    decision = (
        "Pay Per Ride/Minute" if totals["PAYG"] <= totals["MEMBER"] else "Buy Monthly Membership"
    )
    return (
        f"NEXT: the actual calculator observations give PAYG {totals['PAYG']} USD and MEMBER {totals['MEMBER']} USD. The cheaper alternative (ties pay per use) requires decision exactly {decision}. Choose from these total costs, not citywide ride count. Return ONLY the final four-key JSON using these observed totals. Fill this exact five-sentence justification with that same decision; add no other claims: "
        + rationale_template(urls)
    )
