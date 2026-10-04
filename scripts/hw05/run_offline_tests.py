"""Run the six Part 4 assertions plus two Part 5 offline safety/agent assertions.

Run from the repository with ``python scripts/hw05/run_offline_tests.py``.
No database, network, model server, or Part 3 runtime is needed.
"""

from collections.abc import Callable, Sequence
import json
import io
from pathlib import Path
import sys
from typing import Any
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


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


def private_contact_blocked() -> None:
    # A default-call trap proves the block precedes factory construction.
    from src.rental_tools.executor import SAFETY_BLOCK_ERROR

    factory_calls = []
    runtime = ModuleType("src.rental_tools.runtime")

    def forbidden_factory():
        factory_calls.append("constructed")
        raise AssertionError("Blocked requests must not construct a runtime")

    runtime.build_service = forbidden_factory
    reader = FixtureReader()
    inputs = {"rental_id": 1, "include_contact": True}
    expected = {"ok": False, "data": None, "error": SAFETY_BLOCK_ERROR}
    with patch.dict(sys.modules, {"src.rental_tools.runtime": runtime}):
        assert checked_result("get_rental", inputs, reader) == expected
        raw = execute_tool("get_rental", inputs)
        assert json.loads(raw) == expected
    assert reader.calls == []
    assert factory_calls == []
    for private_field in ("submitter_email", "manager_email", "password_hash", PRIVATE_SENTINEL):
        assert private_field not in raw


def mock_model_max_steps() -> None:
    from src.model_client import CompletionResult, TokenUsage
    from src.tool_agent import run_agent

    class MockModel:
        def __init__(self):
            self.requests = 0

        def complete(self, messages, tools=None):
            self.requests += 1
            raw = SimpleNamespace(
                content="", invalid_tool_calls=[],
                tool_calls=[{"name": "count_rentals", "args": {"manager_id": 1},
                             "id": f"offline-{self.requests}", "type": "tool_call"}],
            )
            return CompletionResult("", TokenUsage(0, 0, 0), raw)

    model, reader, log = MockModel(), FixtureReader(), io.StringIO()
    service = RentalService(reader)
    calls = []

    def executor(name, inputs):
        calls.append((name, inputs))
        return execute_tool(name, inputs, service=service)

    result = run_agent(
        "Offline mock: keep counting manager 1", model=model, executor=executor,
        log_stream=log, max_steps=3, code_revision="offline-mock",
    )
    assert model.requests == result.steps == 3
    assert result.tool_calls == len(calls) == len(reader.calls) == 3
    assert all(call == ("count", 1) for call in reader.calls)
    assert result.stop_reason == "max_steps"
    assert result.answer is None
    events = [json.loads(line) for line in log.getvalue().splitlines()]
    terminal = [event for event in events if event["event"] == "terminal"]
    assert len(terminal) == 1
    assert terminal[0]["run_id"] == result.run_id
    assert terminal[0]["steps"] == result.steps
    assert terminal[0]["tool_calls"] == result.tool_calls
    assert terminal[0]["stop_reason"] == result.stop_reason
    assert terminal[0]["answer"] is None


CASES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("valid_search", valid_search),
    ("whitespace_search_rejected", whitespace_search_rejected),
    ("valid_rental_detail", valid_rental_detail),
    ("missing_rental_8_rejected", missing_rental_8_rejected),
    ("valid_manager_count", valid_manager_count),
    ("missing_manager_4_rejected", missing_manager_4_rejected),
    ("private_contact_blocked", private_contact_blocked),
    ("mock_model_max_steps", mock_model_max_steps),
)


def main(*, cases: Sequence[tuple[str, Callable[[], None]]] | None = None) -> int:
    if not __debug__:
        print("ERROR: Python optimization disables assertions; run without -O.", file=sys.stderr)
        return 2
    selected = CASES if cases is None else cases
    print("Pragya Apurva - HW5 Parts 4/5 offline assertions")
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
