"""Immutable public fixture for controlled Part 3 measurements, never MySQL proof."""
import hashlib
import json
from types import MappingProxyType


FIXTURE = MappingProxyType({
    "rental": MappingProxyType({
        "id": 1,
        "listing_title": "Campus apartment",
        "property_address": "100 Campus Way, San Jose",
        "property_type": "apartment",
        "manager_id": 1,
        "description": "A one-bedroom apartment near campus.",
    }),
    "manager": MappingProxyType({"manager_id": 1, "manager_name": "Campus Homes"}),
})


def fixture_payload():
    """Return detached JSON-compatible data, without making the fixture mutable."""
    return {name: dict(row) for name, row in FIXTURE.items()}


def fixture_sha256():
    encoded = json.dumps(fixture_payload(), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class FixtureReader:
    """One rental and manager; Python casefold is only a fixture approximation."""

    def search_rentals(self, query: str, limit: int):
        row = FIXTURE["rental"]
        term = query.casefold()
        matched = any(term in row[key].casefold() for key in ("listing_title", "property_address"))
        return [dict(row)][:limit] if matched else []

    def get_rental(self, rental_id: int):
        return dict(FIXTURE["rental"]) if rental_id == FIXTURE["rental"]["id"] else None

    def count_rentals(self, manager_id: int):
        if manager_id != FIXTURE["manager"]["manager_id"]:
            return None
        return {**FIXTURE["manager"], "count": int(FIXTURE["rental"]["manager_id"] == manager_id)}
