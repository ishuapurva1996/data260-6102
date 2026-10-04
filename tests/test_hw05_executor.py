"""Executor boundaries; runtime module doubles prove glue, never live integration."""

import copy
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rental_tools import executor
from src.rental_tools.contracts import failure, success
from src.rental_tools.registry import TOOL_REGISTRY
from src.rental_tools.service import RentalService


class Reader:
    def __init__(self):
        self.calls = []
        self.closes = 0

    def get_rental(self, rental_id):
        self.calls.append(("get", rental_id))
        if rental_id == 8:
            return None
        return {"id": rental_id, "listing_title": "Garden Home",
                "property_address": "1 Garden Lane", "property_type": "house",
                "manager_id": 1, "description": "Near the park.",
                "submitter_email": "private@example.invalid", "password_hash": "secret"}

    def search_rentals(self, query, limit):
        self.calls.append(("search", query, limit))
        return []

    def count_rentals(self, manager_id):
        self.calls.append(("count", manager_id))
        if manager_id == 4:
            return None
        return {"manager_id": manager_id, "manager_name": "Empty Manager", "count": 0,
                "manager_email": "private@example.invalid"}

    def close(self):
        self.closes += 1


def decoded(raw):
    assert isinstance(raw, str)
    value = json.loads(raw)
    assert set(value) == {"ok", "data", "error"}
    assert type(value["ok"]) is bool
    if value["ok"]:
        assert isinstance(value["data"], dict) and value["error"] is None
    else:
        assert value["data"] is None
        assert isinstance(value["error"], str) and value["error"].strip()
    return value


@pytest.fixture
def service():
    return RentalService(Reader())


def runtime_double(monkeypatch, factory):
    """Explicit isolated module double; the real Part 3 factory is absent here."""
    module = ModuleType("src.rental_tools.runtime")
    module.build_service = factory
    monkeypatch.setitem(sys.modules, module.__name__, module)


@pytest.mark.parametrize("name", [None, 1, True, [], {}, "", "close", "__dict__", "get_rental;SELECT"])
def test_unknown_names_are_safe_without_factory(monkeypatch, name):
    runtime_double(monkeypatch, lambda: pytest.fail("factory must not run"))
    result = decoded(executor.execute_tool(name, {}))
    assert result == failure("Unknown rental tool.")


@pytest.mark.parametrize("inputs", [None, [], "{}", 5, {1: "secret"}, {None: 1}])
def test_inputs_require_dict_and_string_keys(monkeypatch, inputs):
    runtime_double(monkeypatch, lambda: pytest.fail("factory must not run"))
    assert decoded(executor.execute_tool("get_rental", inputs))["ok"] is False


@pytest.mark.parametrize("name,inputs", [
    ("search_rentals", {}), ("search_rentals", {"query": ""}),
    ("search_rentals", {"query": "x" * 256}), ("search_rentals", {"query": 1}),
    *[("search_rentals", {"query": "x", "limit": n}) for n in [True, "1", 1.0, 0, 26]],
    *[(tool, {field: n}) for tool, field in [("get_rental", "rental_id"),
                                             ("count_rentals", "manager_id")]
      for n in [False, "1", 1.0, 0, -1, None]],
    ("get_rental", {}), ("count_rentals", {}),
    *[("get_rental", {"rental_id": 1, "include_contact": value})
      for value in ["true", "false", 1, 0, 1.0, None, [], {}]],
    ("get_rental", {"rental_id": 0, "include_contact": True}),
    ("get_rental", {"rental_id": 1, "include_contact": True, "extra": "secret"}),
    ("get_rental", {"rental_id": 1, "extra": "secret"}),
    ("search_rentals", {"query": "x", "sql": "secret"}),
    ("count_rentals", {"manager_id": 1, "extra": "secret"}),
])
def test_shared_strict_validation_precedes_factory_and_read(monkeypatch, service, name, inputs):
    runtime_double(monkeypatch, lambda: pytest.fail("factory must not run"))
    assert decoded(executor.execute_tool(name, inputs))["error"].startswith("Invalid input:")
    assert decoded(executor.execute_tool(name, inputs, service=service))["ok"] is False
    assert service.reader.calls == []


def test_canonical_whitespace_error_is_exact(service):
    assert decoded(executor.execute_tool("search_rentals", {"query": "   ", "limit": 5}, service=service)) == failure(
        "Invalid input: query: Value error, query must contain non-whitespace characters")
    assert service.reader.calls == []


def test_validation_does_not_echo_secret_values_or_extra_keys(service, capsys):
    raw = executor.execute_tool("get_rental", {"rental_id": "private@example.invalid",
                                              "SELECT password FROM users": "secret"}, service=service)
    assert decoded(raw)["ok"] is False
    assert decoded(raw)["error"] == (
        "Invalid input: rental_id: Input should be a valid integer; "
        "unexpected_field: Extra inputs are not permitted"
    )
    assert "private@" not in raw and "SELECT" not in raw and "secret" not in raw
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("flag", [{}, {"include_contact": False}])
def test_valid_dispatch_and_projection_use_static_handler(service, monkeypatch, flag):
    monkeypatch.setattr(service, "get_rental", lambda **kw: pytest.fail("arbitrary instance dispatch"))
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 1, **flag}, service=service)) == success({
        "id": 1, "listingTitle": "Garden Home", "propertyAddress": "1 Garden Lane",
        "propertyType": "house", "managerId": 1, "description": "Near the park."})
    assert service.reader.calls == [("get", 1)]
    assert service.reader.closes == 0


def test_contact_policy_blocks_valid_request_before_factory_and_injected_read(monkeypatch, service):
    runtime_double(monkeypatch, lambda: pytest.fail("blocked requests must not construct a service"))
    inputs = {"rental_id": 1, "include_contact": True}
    before = copy.deepcopy(inputs)
    expected = failure("Safety block: rental submitter contact information is private.")
    for provided in [None, service]:
        raw = executor.execute_tool("get_rental", inputs, service=provided)
        assert decoded(raw) == expected
        assert "private@example.invalid" not in raw and "password_hash" not in raw
    assert inputs == before
    assert service.reader.calls == []
    assert service.reader.closes == 0


def test_defaults_trim_boundaries_and_no_mutation(service):
    inputs = {"query": "  Garden  "}
    before = copy.deepcopy(inputs)
    assert decoded(executor.execute_tool("search_rentals", inputs, service=service)) == success({
        "items": [], "returnedCount": 0, "limit": 5})
    assert inputs == before
    assert service.reader.calls == [("search", "Garden", 5)]
    assert decoded(executor.execute_tool("search_rentals", {"query": "x" * 255, "limit": 25}, service=service))["ok"]


def test_missing_no_match_and_zero_remain_domain_outcomes(service):
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 8}, service=service)) == failure("Rental 8 was not found.")
    assert decoded(executor.execute_tool("count_rentals", {"manager_id": 4}, service=service)) == failure("Property manager 4 was not found.")
    assert decoded(executor.execute_tool("count_rentals", {"manager_id": 3}, service=service)) == success({
        "managerId": 3, "managerName": "Empty Manager", "count": 0})


def test_reader_failure_is_sanitized(service, monkeypatch, capsys):
    def broken(_):
        raise RuntimeError("mysql+pymysql://user:password@host/s6102_rel SELECT private_email")
    monkeypatch.setattr(service.reader, "get_rental", broken)
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 1}, service=service)) == failure(
        "Rental data is temporarily unavailable.")
    assert service.reader.closes == 0
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("result", [None, [], {}, {"ok": True, "data": {}, "error": None, "extra": 1},
    {"ok": 1, "data": {}, "error": None}, success(None), success([]),
    {"ok": True, "data": {}, "error": "secret"}, failure(""), failure("   "), failure(3),
    {"ok": False, "data": {}, "error": "secret"}, success({"x": float("nan")}),
    success({"x": float("inf")}), success({"x": object()}), success({"x": {1, 2}}),
])
def test_malformed_and_unserializable_results_have_constant_fallback(monkeypatch, service, result):
    definition = replace(TOOL_REGISTRY["get_rental"], handler=lambda *a, **kw: result)
    monkeypatch.setattr(executor, "TOOL_REGISTRY", {"get_rental": definition})
    raw = executor.execute_tool("get_rental", {"rental_id": 1}, service=service)
    assert decoded(raw) == failure("Rental tool returned an invalid result.")
    assert service.reader.closes == 0


def test_circular_result_has_safe_fallback(monkeypatch, service):
    data = {}
    data["self"] = data
    definition = replace(TOOL_REGISTRY["get_rental"], handler=lambda *a, **kw: success(data))
    monkeypatch.setattr(executor, "TOOL_REGISTRY", {"get_rental": definition})
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 1}, service=service)) == failure(
        "Rental tool returned an invalid result.")


def test_default_factory_double_creates_fresh_owned_service_each_call(monkeypatch):
    readers = []
    def factory():
        reader = Reader()
        readers.append(reader)
        return RentalService(reader)
    runtime_double(monkeypatch, factory)
    for _ in range(2):
        assert decoded(executor.execute_tool("get_rental", {"rental_id": 1}))["ok"]
    assert len(readers) == 2 and all(r.closes == 1 for r in readers)


@pytest.mark.parametrize("mode", ["domain_error", "exception", "serialization", "cleanup"])
def test_default_double_always_closes_without_overwriting_result(monkeypatch, mode, capsys):
    reader = Reader()
    service = RentalService(reader)
    runtime_double(monkeypatch, lambda: service)
    if mode == "exception":
        def broken(*a, **kw):
            raise RuntimeError("private password SELECT")
        monkeypatch.setattr(executor, "TOOL_REGISTRY", {"get_rental": replace(TOOL_REGISTRY["get_rental"], handler=broken)})
    if mode == "serialization":
        monkeypatch.setattr(reader, "get_rental", lambda _: {**Reader().get_rental(1), "description": float("nan")})
    if mode == "cleanup":
        def bad_close():
            reader.closes += 1
            raise RuntimeError("private password SELECT")
        monkeypatch.setattr(reader, "close", bad_close)
    value = decoded(executor.execute_tool("get_rental", {"rental_id": 8 if mode == "domain_error" else 1}))
    assert value["ok"] is (mode == "cleanup")
    assert reader.closes == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ("Rental tool cleanup failed.\n" if mode == "cleanup" else "")


def test_factory_exception_is_safe(monkeypatch, capsys):
    def broken():
        raise RuntimeError("password SELECT")
    runtime_double(monkeypatch, broken)
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 1})) == failure("Rental data is temporarily unavailable.")
    assert capsys.readouterr() == ("", "")


def test_falsey_injected_service_is_used_and_never_closed(monkeypatch):
    class FalseyService(RentalService):
        def __bool__(self):
            return False
    service = FalseyService(Reader())
    runtime_double(monkeypatch, lambda: pytest.fail("injection must bypass factory"))
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 1}, service=service))["ok"]
    assert service.reader.closes == 0


def test_cleanup_and_diagnostic_write_failures_cannot_replace_success(monkeypatch, service):
    runtime_double(monkeypatch, lambda: service)
    def broken(*args, **kwargs):
        raise OSError("private failure")
    monkeypatch.setattr(service.reader, "close", broken)
    monkeypatch.setattr(sys.stderr, "write", broken)
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 1}))["ok"]


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_baseexceptions_propagate_and_owned_reader_closes(monkeypatch, service, exception):
    def interrupted(_):
        raise exception()
    monkeypatch.setattr(service.reader, "get_rental", interrupted)
    runtime_double(monkeypatch, lambda: service)
    with pytest.raises(exception):
        executor.execute_tool("get_rental", {"rental_id": 1})
    assert service.reader.closes == 1


def test_missing_runtime_dependency_is_honest_in_isolated_process():
    code = '''
import builtins, json
from src.rental_tools.executor import execute_tool
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "runtime" or name == "src.rental_tools.runtime":
        raise ModuleNotFoundError("secret dependency internals")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
print(execute_tool("get_rental", {"rental_id": 1}))
'''
    run = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert run.returncode == 0 and run.stderr == ""
    assert decoded(run.stdout.strip()) == failure("Rental tool runtime is unavailable.")
