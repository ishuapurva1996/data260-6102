"""Run the six canonical Part 4 assertions using production tools and finite rows.

Run from the repository with ``python scripts/hw05/run_offline_tests.py``.
No database, network, model server, or Part 3 runtime is needed.
"""

from collections.abc import Callable, Sequence
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.hw05.part4.fixture import FixtureReader, PRIVATE_SENTINEL
from src.rental_tools.executor import execute_tool
from src.rental_tools.service import RentalService


def checked_result(name: str, inputs: dict[str, Any], reader: FixtureReader) -> dict[str, Any]:
    """Every assertion case checks the string, envelope, and public projection."""
    raw = execute_tool(name, inputs, service=RentalService(reader))
    assert isinstance(raw, str)
    result = json.loads(raw)
    assert isinstance(result, dict)
    assert set(result) == {"ok", "data", "error"}
    assert type(result["ok"]) is bool
    if result["ok"]:
        assert isinstance(result["data"], dict)
        assert result["error"] is None
    else:
        assert result["data"] is None
        assert isinstance(result["error"], str) and result["error"].strip()
    assert PRIVATE_SENTINEL not in raw
    return result


def valid_search() -> None:
    reader = FixtureReader()
    result = checked_result("search_rentals", {"query": "garden", "limit": 5}, reader)
    assert result == {"ok": True, "error": None, "data": {
        "items": [
            {"id": 1, "listingTitle": "Garden Apartment", "propertyAddress": "101 Oak Avenue",
             "propertyType": "apartment", "managerId": 1},
            {"id": 2, "listingTitle": "Garden House", "propertyAddress": "202 Pine Street",
             "propertyType": "house", "managerId": 1},
        ],
        "returnedCount": 2, "limit": 5,
    }}
    assert reader.calls == [("search", "garden", 5)]


def whitespace_search_rejected() -> None:
    reader = FixtureReader()
    result = checked_result("search_rentals", {"query": "   ", "limit": 5}, reader)
    assert result == {
        "ok": False, "data": None,
        "error": "Invalid input: query: Value error, query must contain non-whitespace characters",
    }
    assert reader.calls == []


def valid_rental_detail() -> None:
    reader = FixtureReader()
    result = checked_result("get_rental", {"rental_id": 1}, reader)
    assert result == {"ok": True, "error": None, "data": {
        "id": 1, "listingTitle": "Garden Apartment", "propertyAddress": "101 Oak Avenue",
        "propertyType": "apartment", "managerId": 1,
        "description": "A bright apartment beside the community garden.",
    }}
    assert reader.calls == [("get", 1)]


def missing_rental_8_rejected() -> None:
    reader = FixtureReader()
    result = checked_result("get_rental", {"rental_id": 8}, reader)
    assert result == {"ok": False, "data": None, "error": "Rental 8 was not found."}
    assert reader.calls == [("get", 8)]


def valid_manager_count() -> None:
    reader = FixtureReader()
    result = checked_result("count_rentals", {"manager_id": 1}, reader)
    assert result == {
        "ok": True, "data": {"managerId": 1, "managerName": "Alex Morgan", "count": 2},
        "error": None,
    }
    assert reader.calls == [("count", 1)]


def missing_manager_4_rejected() -> None:
    reader = FixtureReader()
    result = checked_result("count_rentals", {"manager_id": 4}, reader)
    assert result == {"ok": False, "data": None, "error": "Property manager 4 was not found."}
    assert reader.calls == [("count", 4)]


CASES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("valid_search", valid_search),
    ("whitespace_search_rejected", whitespace_search_rejected),
    ("valid_rental_detail", valid_rental_detail),
    ("missing_rental_8_rejected", missing_rental_8_rejected),
    ("valid_manager_count", valid_manager_count),
    ("missing_manager_4_rejected", missing_manager_4_rejected),
)


def main(*, cases: Sequence[tuple[str, Callable[[], None]]] | None = None) -> int:
    if not __debug__:
        print("ERROR: Python optimization disables assertions; run without -O.", file=sys.stderr)
        return 2
    selected = CASES if cases is None else cases
    print("Pragya Apurva - HW5 Part 4 offline assertions")
    passed = 0
    for name, case in selected:
        try:
            case()
        except Exception as exc:
            # Exception details might contain dependency or private fixture data.
            print(f"FAIL {name} ({type(exc).__name__})")
        else:
            passed += 1
            print(f"PASS {name}")
    print(f"{passed}/{len(selected)} passed")
    return 0 if passed == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
