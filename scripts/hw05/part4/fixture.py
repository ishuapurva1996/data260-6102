"""Finite offline rows for Part 4; this is not a MySQL collation emulator."""

from typing import Any


PRIVATE_SENTINEL = "PART4_PRIVATE_SENTINEL"


class FixtureReader:
    """Implement the production reader interface without configuration or I/O."""

    def __init__(self):
        self.calls: list[tuple[Any, ...]] = []
        # Deliberately out of order so search assertions check stable ID order.
        self.rows = [
            {
                "id": 7, "listing_title": "Downtown Condo",
                "property_address": "707 Market Street", "property_type": "condo",
                "description": "A condo near the downtown library.", "manager_id": 2,
                "submitter_email": PRIVATE_SENTINEL, "password_hash": PRIVATE_SENTINEL,
            },
            {
                "id": 2, "listing_title": "Garden House",
                "property_address": "202 Pine Street", "property_type": "house",
                "description": "A house with a fenced garden.", "manager_id": 1,
                "submitter_email": PRIVATE_SENTINEL, "password_hash": PRIVATE_SENTINEL,
            },
            {
                "id": 1, "listing_title": "Garden Apartment",
                "property_address": "101 Oak Avenue", "property_type": "apartment",
                "description": "A bright apartment beside the community garden.", "manager_id": 1,
                "submitter_email": PRIVATE_SENTINEL, "password_hash": PRIVATE_SENTINEL,
            },
        ]
        self.managers = {1: "Alex Morgan", 2: "Taylor Reed", 3: "Empty Manager"}

    def search_rentals(self, query: str, limit: int) -> list[dict[str, Any]]:
        self.calls.append(("search", query, limit))
        return [
            dict(row) for row in sorted(self.rows, key=lambda row: row["id"])
            if query.lower() in row["listing_title"].lower()
            or query.lower() in row["property_address"].lower()
        ][:limit]

    def get_rental(self, rental_id: int) -> dict[str, Any] | None:
        self.calls.append(("get", rental_id))
        return next((dict(row) for row in self.rows if row["id"] == rental_id), None)

    def count_rentals(self, manager_id: int) -> dict[str, Any] | None:
        self.calls.append(("count", manager_id))
        if manager_id not in self.managers:
            return None
        return {
            "manager_id": manager_id, "manager_name": self.managers[manager_id],
            "count": sum(row["manager_id"] == manager_id for row in self.rows),
            "manager_email": PRIVATE_SENTINEL,
        }
