"""Merged executor/factory/retry contracts with controlled storage boundaries.

These tests retain the real default factory, reader construction and cleanup,
retry implementation, registry, and service. Read outcomes and engine disposal
are controlled probes; driver exceptions here are not live MySQL outage proof.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pymysql.err
import pytest
from sqlalchemy import exc as sa_exc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.rental_tools import executor, runtime
from src.rental_tools.contracts import failure, success
from src.rental_tools.reader import MySQLRentalReader
from src.rental_tools.reliability import RetryingRentalReader


ROW = {
    "id": 41,
    "listing_title": "Integration Garden Home",
    "property_address": "41 Garden Lane",
    "property_type": "house",
    "manager_id": 21,
    "description": "Near the park.",
    "submitter_email": "PRIVATE_SENTINEL",
}
LISTING = {
    "id": 41,
    "listingTitle": "Integration Garden Home",
    "propertyAddress": "41 Garden Lane",
    "propertyType": "house",
    "managerId": 21,
}
COUNT_ROW = {"manager_id": 21, "manager_name": "Garden Manager", "count": 1}
OPERATIONS = [
    ("search_rentals", {"query": "Garden"}, ("Garden", 5), [ROW]),
    ("get_rental", {"rental_id": 41}, (41,), ROW),
    ("count_rentals", {"manager_id": 21}, (21,), COUNT_ROW),
]


def decoded(raw):
    def reject_constant(value):
        raise AssertionError(f"Non-JSON constant: {value}")

    assert isinstance(raw, str)
    result = json.loads(raw, parse_constant=reject_constant)
    assert set(result) == {"ok", "data", "error"}
    assert type(result["ok"]) is bool
    if result["ok"]:
        assert isinstance(result["data"], dict) and result["error"] is None
    else:
        assert result["data"] is None
        assert isinstance(result["error"], str) and result["error"].strip()
    assert "PRIVATE_SENTINEL" not in raw
    return result


@pytest.fixture
def storage_probe(monkeypatch):
    """Instrument actual classes; never replace runtime.build_service."""
    probe = SimpleNamespace(
        outcomes=[], calls=[], readers=[], wrappers=[], engines=[],
        events=[], sleeps=[], cleanup_error=False,
    )
    reader_init = MySQLRentalReader.__init__
    retry_init = RetryingRentalReader.__init__

    class DisposalProbe:
        def __init__(self):
            self.disposals = 0

        def dispose(self):
            self.disposals += 1
            if probe.cleanup_error:
                raise RuntimeError("PRIVATE_SENTINEL")

    def observe_reader(self, *args, **kwargs):
        reader_init(self, *args, **kwargs)
        probe.readers.append(self)
        engine = DisposalProbe()
        probe.engines.append(engine)
        self._engine = engine

    def observe_wrapper(self, *args, **kwargs):
        retry_init(self, *args, **kwargs)
        probe.wrappers.append(self)
        self._sleep = probe.sleeps.append
        self.attempt_observer = probe.events.append

    def controlled_read(operation):
        def read(self, *args):
            probe.calls.append((operation, args))
            assert probe.outcomes, "Unexpected storage read"
            value = probe.outcomes.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        return read

    def forbid_connection(self):
        pytest.fail("Controlled integration test must not access a database")

    monkeypatch.setattr(MySQLRentalReader, "__init__", observe_reader)
    monkeypatch.setattr(MySQLRentalReader, "_get_engine", forbid_connection)
    monkeypatch.setattr(RetryingRentalReader, "__init__", observe_wrapper)
    for operation, *_ in OPERATIONS:
        monkeypatch.setattr(MySQLRentalReader, operation, controlled_read(operation))
    return probe


def assert_owned_reader_closed_once(probe):
    assert len(probe.readers) == len(probe.wrappers) == len(probe.engines) == 1
    wrapper, reader = probe.wrappers[0], probe.readers[0]
    assert type(wrapper) is RetryingRentalReader
    assert type(reader) is MySQLRentalReader
    assert wrapper.reader is reader
    assert wrapper._closed
    assert probe.engines[0].disposals == 1
    wrapper.close()
    assert probe.engines[0].disposals == 1


@pytest.mark.parametrize("name,inputs,args,outcome,expected", [
    ("search_rentals", {"query": "  Garden  "}, ("Garden", 5), [ROW],
     success({"items": [LISTING], "returnedCount": 1, "limit": 5})),
    ("search_rentals", {"query": "missing"}, ("missing", 5), [],
     success({"items": [], "returnedCount": 0, "limit": 5})),
    ("get_rental", {"rental_id": 41}, (41,), ROW,
     success({**LISTING, "description": "Near the park."})),
    ("get_rental", {"rental_id": 99}, (99,), None,
     failure("Rental 99 was not found.")),
    ("count_rentals", {"manager_id": 21}, (21,), COUNT_ROW,
     success({"managerId": 21, "managerName": "Garden Manager", "count": 1})),
    ("count_rentals", {"manager_id": 22}, (22,),
     {"manager_id": 22, "manager_name": "Empty Manager", "count": 0},
     success({"managerId": 22, "managerName": "Empty Manager", "count": 0})),
    ("count_rentals", {"manager_id": 99}, (99,), None,
     failure("Property manager 99 was not found.")),
])
def test_default_executor_uses_real_factory_once_without_result_retries(
    storage_probe, name, inputs, args, outcome, expected,
):
    storage_probe.outcomes = [outcome]
    assert decoded(executor.execute_tool(name, inputs)) == expected
    assert storage_probe.calls == [(name, args)]
    assert storage_probe.sleeps == []
    assert [(event["attempt"], event["outcome"]) for event in storage_probe.events] == [(1, "success")]
    assert_owned_reader_closed_once(storage_probe)
    assert storage_probe.readers[0]._engine is None


@pytest.mark.parametrize("name,inputs", [
    ("unknown_tool", {}),
    ([], {}),
    ("get_rental", "{\"rental_id\": 41}"),
    ("get_rental", {41: 41}),
    ("get_rental", {"rental_id": "41"}),
    ("count_rentals", {"manager_id": True}),
    ("count_rentals", {"manager_id": 0}),
    ("search_rentals", {"query": "   "}),
    ("search_rentals", {"query": "Garden", "limit": 26}),
    ("get_rental", {"rental_id": 41, "PRIVATE_SENTINEL": True}),
])
def test_invalid_default_calls_construct_nothing_and_perform_no_read(storage_probe, name, inputs):
    assert decoded(executor.execute_tool(name, inputs))["ok"] is False
    assert storage_probe.readers == storage_probe.wrappers == storage_probe.engines == []
    assert storage_probe.calls == storage_probe.events == storage_probe.sleeps == []


@pytest.mark.parametrize("name,inputs,args,outcome", OPERATIONS)
@pytest.mark.parametrize("fault", [
    "transient_raw_recovery", "transient_wrapped_recovery", "transient_exhaustion",
    "permanent_raw", "permanent_wrapped",
])
def test_controlled_driver_faults_cross_real_default_retry_boundary(
    storage_probe, capsys, name, inputs, args, outcome, fault,
):
    """Controlled PyMySQL/SQLAlchemy faults exercise actual classification."""
    transient = fault.startswith("transient")
    error = pymysql.err.OperationalError(2013 if transient else 1045, "PRIVATE_SENTINEL")
    if "wrapped" in fault:
        error = sa_exc.OperationalError("PRIVATE_SENTINEL", {}, error)
    exhausted = fault == "transient_exhaustion"
    failures = 3 if exhausted else 2 if transient else 1
    storage_probe.outcomes = [error] * failures + ([] if exhausted or not transient else [outcome])

    result = decoded(executor.execute_tool(name, inputs))

    if transient and not exhausted:
        assert result["ok"] is True
    else:
        assert result == failure("Rental data is temporarily unavailable.")
    attempts = failures + int(transient and not exhausted)
    assert storage_probe.calls == [(name, args)] * attempts
    assert storage_probe.sleeps == ([0.1, 0.2] if transient else [])
    assert [event["attempt"] for event in storage_probe.events] == list(range(1, attempts + 1))
    expected_outcomes = ["transient_error" if transient else "permanent_error"] * failures
    if transient and not exhausted:
        expected_outcomes.append("success")
    assert [event["outcome"] for event in storage_probe.events] == expected_outcomes
    assert storage_probe.events[-1]["sleep_s"] == 0
    assert "PRIVATE_SENTINEL" not in repr(storage_probe.events)
    assert_owned_reader_closed_once(storage_probe)
    assert capsys.readouterr() == ("", "")


def test_real_default_reader_is_disposed_after_serialization_failure(storage_probe):
    storage_probe.outcomes = [{**ROW, "description": float("nan")}]
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 41})) == failure(
        "Rental tool returned an invalid result.")
    assert storage_probe.calls == [("get_rental", (41,))]
    assert storage_probe.sleeps == []
    assert_owned_reader_closed_once(storage_probe)


def test_controlled_disposal_failure_preserves_default_result(storage_probe, capsys):
    storage_probe.outcomes = [ROW]
    storage_probe.cleanup_error = True
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 41})) == success(
        {**LISTING, "description": "Near the park."})
    assert_owned_reader_closed_once(storage_probe)
    assert capsys.readouterr() == ("", "Rental tool cleanup failed.\n")


@pytest.mark.parametrize("outcome,expected", [
    (ROW, success({**LISTING, "description": "Near the park."})),
    (RuntimeError("PRIVATE_SENTINEL"), failure("Rental data is temporarily unavailable.")),
    ({**ROW, "description": float("nan")}, failure("Rental tool returned an invalid result.")),
])
def test_injected_real_runtime_service_keeps_existing_wrapper_caller_owned(storage_probe, outcome, expected):
    original = runtime.build_service()
    service = runtime.build_service(reader=original.reader)
    assert service.reader is original.reader
    storage_probe.outcomes = [outcome]
    assert decoded(executor.execute_tool("get_rental", {"rental_id": 41}, service=service)) == expected
    assert len(storage_probe.readers) == len(storage_probe.wrappers) == 1
    assert not service.reader._closed
    assert storage_probe.engines[0].disposals == 0
    service.reader.close()
    assert_owned_reader_closed_once(storage_probe)


def test_repeated_two_argument_calls_have_fresh_owned_readers(storage_probe):
    storage_probe.outcomes = [ROW, ROW]
    for _ in range(2):
        assert decoded(executor.execute_tool("get_rental", {"rental_id": 41}))["ok"]
    assert len(storage_probe.readers) == len(storage_probe.wrappers) == 2
    assert storage_probe.readers[0] is not storage_probe.readers[1]
    assert storage_probe.wrappers[0] is not storage_probe.wrappers[1]
    assert all(wrapper.reader is reader for wrapper, reader in zip(storage_probe.wrappers, storage_probe.readers))
    assert all(wrapper._closed for wrapper in storage_probe.wrappers)
    assert [engine.disposals for engine in storage_probe.engines] == [1, 1]
