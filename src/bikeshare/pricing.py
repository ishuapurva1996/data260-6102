import hashlib
import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit

_MONEY = r"(\d+(?:\.\d+)?)"


def _unique(values, field):
    found = set(values)
    if len(found) != 1:
        raise ValueError(f"Missing or contradictory official pricing fact: {field}.")
    return next(iter(found))


def _amounts(pattern, text):
    return [format(Decimal(value), ".2f") for value in re.findall(pattern, text, re.I)]


def parse_policy(snapshots):
    """Fail closed when current product-specific evidence is absent or disagrees."""
    facts = {
        name: []
        for name in (
            "membership_fee",
            "classic_included_minutes",
            "classic_overage_per_minute",
            "casual_unlock",
            "casual_classic_per_minute",
            "member_ebike_per_minute",
            "casual_ebike_per_minute",
            "member_unlock",
            "rounding",
        )
    }
    citations, product_paths = [], set()
    member_source_seen = False
    for snapshot in snapshots:
        try:
            url, text = snapshot["url"], snapshot["text"]
            captured_at, digest = snapshot["captured_at"], snapshot["sha256"]
            parsed = urlsplit(url)
            timestamp = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(
                "Every policy snapshot needs URL, text, capture time, and text SHA-256."
            ) from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"capitalbikeshare.com", "help.capitalbikeshare.com"}
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or timestamp.tzinfo is None
        ):
            raise ValueError(
                "Policy sources must be official HTTPS pages with an offset-aware capture time."
            )
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
            raise ValueError("Pricing snapshot SHA-256 does not match its exact UTF-8 text bytes.")
        normalized = re.sub(r"\s+", " ", text)
        path = parsed.path.rstrip("/")
        member = path == "/pricing/30-day" or (
            parsed.hostname == "help.capitalbikeshare.com" and path.endswith("-30-Day-Membership")
        )
        casual = path == "/pricing/single-trip"
        rounding = parsed.hostname == "help.capitalbikeshare.com" and (
            member or path.endswith("-How-long-can-I-keep-a-bike-out")
        )
        if not (member or casual or rounding):
            continue
        product_paths.add(path)
        if member:
            member_source_seen = True
            facts["membership_fee"] += _amounts(r"\$" + _MONEY + r"\s*/\s*30[- ]Days?", normalized)
            included = re.findall(
                r"(?:Unlimited |as many )(\d+)-minute (?:rides|trips) on classic bikes|First (\d+) minutes included",
                normalized,
                re.I,
            )
            facts["classic_included_minutes"] += [int(a or b) for a, b in included]
            facts["classic_included_minutes"] += [
                int(value)
                for value in re.findall(r"Ride longer than (\d+) minutes and pay", normalized, re.I)
            ]
            facts["classic_overage_per_minute"] += _amounts(
                r"(?:Ride longer than \d+ minutes and |If you need more time than what.s covered, )pay \$"
                + _MONEY
                + r"\s*(?:/minute|per minute)",
                normalized,
            )
            facts["member_ebike_per_minute"] += _amounts(
                r"(?:discounted rate of |Members pay )\$"
                + _MONEY
                + r"\s*(?:/min|per minute) (?:on |for )ebikes",
                normalized,
            )
            if re.search(r"don.t pay to unlock bikes|avoid unlock fees", normalized, re.I):
                facts["member_unlock"].append("0.00")
        if casual:
            match = re.search(
                r"The Single Trip costs \$"
                + _MONEY
                + r" to unlock and \$"
                + _MONEY
                + r"/min on a classic bike or \$"
                + _MONEY
                + r"/min on an ebike",
                normalized,
                re.I,
            )
            if match:
                for name, value in zip(
                    ("casual_unlock", "casual_classic_per_minute", "casual_ebike_per_minute"),
                    match.groups(),
                ):
                    facts[name].append(format(Decimal(value), ".2f"))
        if rounding and re.search(
            r"All per minute ride prices are rounded up to the nearest minute", normalized, re.I
        ):
            facts["rounding"].append("ceil_per_ride")
        citations.append(
            {
                "url": url,
                "captured_at": captured_at,
                "sha256": digest,
                "excerpt": normalized,
            }
        )
    if not member_source_seen or "/pricing/single-trip" not in product_paths:
        raise ValueError(
            "Capture an official product-specific 30-day membership page and the single-trip page before calculating."
        )
    policy = {name: _unique(values, name) for name, values in facts.items()}
    if not 0 < policy["classic_included_minutes"] <= 1440:
        raise ValueError("Invalid included-minute policy.")
    if any(
        Decimal(policy[name]) < 0
        for name in facts
        if name not in {"rounding", "classic_included_minutes"}
    ):
        raise ValueError("Negative prices are unsupported.")
    return {
        **policy,
        "currency": "USD",
        "membership_days": 30,
        "citations": citations,
        "pricing_basis": "Captured current Capital Bikeshare 30-day membership and single-trip base transportation rates; not historical actual charges.",
        "assumptions": [
            "Pre-tax base transportation comparison: location-dependent sales taxes are excluded.",
            "Parking, damages, lost-bike and other penalties are excluded because the trip CSV does not observe them; ebike totals include transportation only.",
            "Current captured prices are applied counterfactually to the uploaded trip durations.",
        ],
    }
