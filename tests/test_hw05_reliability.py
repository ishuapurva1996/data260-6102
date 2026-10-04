"""Retry behavior below the unchanged service's validation/error conversion."""
import sys
from pathlib import Path

import pytest
import pymysql.err
from sqlalchemy import exc as sa_exc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.rental_tools.reliability import InjectedTransientError, RetryPolicy, RetryingRentalReader, is_transient
from src.rental_tools.reader import RentalReaderConfigurationError
from src.rental_tools.service import RentalService


class ScriptedReader:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []
        self.closed = 0

    def _read(self, *args):
        self.calls.append(args)
        result = next(self.outcomes)
        if isinstance(result, BaseException):
            raise result
        return result

    search_rentals = _read
    get_rental = _read
    count_rentals = _read

    def close(self):
        self.closed += 1


@pytest.mark.parametrize("method,args,value", [
    ("search_rentals", ("campus", 5), []), ("get_rental", (1,), None),
    ("count_rentals", (1,), {"manager_id": 1, "manager_name": "Campus", "count": 0}),
])
@pytest.mark.parametrize("failures", [0, 1, 2, 3])
def test_each_operation_has_bounded_attempts(method, args, value, failures):
    inner = ScriptedReader([InjectedTransientError("PRIVATE") for _ in range(failures)] + [value])
    sleeps, events = [], []
    reader = RetryingRentalReader(inner, sleep=sleeps.append, attempt_observer=events.append)
    if failures == 3:
        with pytest.raises(InjectedTransientError):
            getattr(reader, method)(*args)
    else:
        assert getattr(reader, method)(*args) == value
    assert inner.calls == [args] * min(failures + 1, 3)
    assert sleeps == [0.1, 0.2][:min(failures, 2)]
    assert [event["attempt"] for event in events] == list(range(1, len(inner.calls) + 1))
    assert events[-1]["sleep_s"] == 0
    assert all(set(event) == {"operation", "attempt", "outcome", "elapsed_s", "sleep_s"} for event in events)
    assert "PRIVATE" not in repr(events)


@pytest.mark.parametrize("error", [
    ValueError("private"), TypeError("private"), KeyError("private"),
    RentalReaderConfigurationError("private"), pymysql.err.OperationalError(1045, "private"),
])
def test_permanent_error_once(error):
    inner, sleeps = ScriptedReader([error]), []
    service = RentalService(RetryingRentalReader(inner, sleep=sleeps.append))
    result = service.get_rental(rental_id=1)
    assert not result["ok"] and result["data"] is None
    assert "private" not in repr(result)
    assert len(inner.calls) == 1 and sleeps == []


@pytest.mark.parametrize("code", [1205, 1213, 2006, 2013, 3024])
def test_explicit_driver_codes_raw_and_wrapped(code):
    error = pymysql.err.OperationalError(code, "private")
    assert is_transient(error)
    assert is_transient(sa_exc.OperationalError("private SQL", {}, error))


@pytest.mark.parametrize("code", [1044, 1045, 1049, 1064, 1142, 1146, 2003, 9999])
def test_other_driver_errors_permanent(code):
    error = pymysql.err.OperationalError(code, "private")
    assert not is_transient(error)
    assert not is_transient(sa_exc.OperationalError("private SQL", {}, error))


@pytest.mark.parametrize("error", [TimeoutError(), ConnectionResetError(), ConnectionAbortedError(),
    BrokenPipeError(), sa_exc.TimeoutError(), InjectedTransientError()])
def test_explicit_io_conditions(error):
    assert is_transient(error)


def test_no_retry_validation_missing_empty_zero():
    inner = ScriptedReader([None, None, [], {"manager_id": 3, "manager_name": "Empty", "count": 0}])
    events = []
    service = RentalService(RetryingRentalReader(inner, attempt_observer=events.append))
    assert service.search_rentals(query="   ", limit=5)["error"] == (
        "Invalid input: query: Value error, query must contain non-whitespace characters")
    assert not inner.calls
    assert service.get_rental(rental_id=8)["error"] == "Rental 8 was not found."
    assert service.count_rentals(manager_id=4)["error"] == "Property manager 4 was not found."
    assert service.search_rentals(query="missing")["data"]["items"] == []
    assert service.count_rentals(manager_id=3)["data"]["count"] == 0
    assert len(inner.calls) == 4 and all(event["attempt"] == 1 for event in events)


def test_observer_failure_cannot_repeat_read_or_change_result():
    def observer(event):
        raise RuntimeError("private observer error")
    inner = ScriptedReader([InjectedTransientError(), None])
    sleeps = []
    reader = RetryingRentalReader(inner, attempt_observer=observer, sleep=sleeps.append)
    assert reader.get_rental(8) is None
    assert len(inner.calls) == 2 and sleeps == [0.1]


def test_close_once_even_when_underlying_close_raises():
    inner = ScriptedReader([])
    def fail_close():
        inner.closed += 1
        raise RuntimeError("private")
    inner.close = fail_close
    reader = RetryingRentalReader(inner)
    with pytest.raises(RuntimeError):
        reader.close()
    reader.close()
    assert inner.closed == 1


@pytest.mark.parametrize("values", [
    {"max_attempts": True}, {"max_attempts": 0}, {"max_attempts": 1.5}, {"max_attempts": 11},
    {"initial_backoff_s": -1}, {"initial_backoff_s": float("nan")},
    {"backoff_multiplier": float("inf")}, {"backoff_multiplier": 0.5},
    {"max_backoff_s": -1}, {"max_backoff_s": float("inf")}, {"initial_backoff_s": True},
    {"max_backoff_s": "1"}, {"initial_backoff_s": 1, "max_backoff_s": 0.2},
])
def test_invalid_policy(values):
    with pytest.raises((ValueError, TypeError)):
        RetryPolicy(**values)


def test_custom_policy_delay_is_capped_and_no_sleep_after_last():
    inner, sleeps = ScriptedReader([InjectedTransientError()] * 5), []
    reader = RetryingRentalReader(inner, RetryPolicy(5, 0.1, 3, 0.2), sleep=sleeps.append)
    with pytest.raises(InjectedTransientError):
        reader.get_rental(1)
    assert sleeps == [0.1, 0.2, 0.2, 0.2]


def test_base_exceptions_propagate_without_retry():
    reader = RetryingRentalReader(ScriptedReader([KeyboardInterrupt()]))
    with pytest.raises(KeyboardInterrupt):
        reader.get_rental(1)
