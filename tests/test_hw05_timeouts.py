"""Finite driver/pool controls and a real loopback PyMySQL timeout."""

import json
import math
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event

from src.rental_tools.reader import MySQLRentalReader, RentalReaderConfigurationError


@pytest.mark.parametrize("method,args", [
    ("search_rentals", ("Maple", 5)),
    ("get_rental", (1,)),
    ("count_rentals", (1,)),
])
@pytest.mark.parametrize("overrides,expected", [
    ({}, (5, 10, 10, 5)),
    ({"connect_timeout_s": 2, "read_timeout_s": 0.2,
      "write_timeout_s": 0.3, "pool_timeout_s": 0.4}, (2, 0.2, 0.3, 0.4)),
])
def test_effective_driver_options_are_finite_and_reads_stay_lazy(monkeypatch, method, args, overrides, expected):
    import src.rental_tools.reader as adapter

    observed = []
    engines = []

    class BeforeNetwork(Exception):
        pass

    def capture_engine(*engine_args, **kwargs):
        engine = create_engine(*engine_args, **kwargs)
        engines.append(engine)

        def before_network(dialect, connection_record, positional, options):
            observed.append(options)
            raise BeforeNetwork

        event.listen(engine, "do_connect", before_network)
        return engine

    class ForbiddenEnvironment:
        def get(self, *args, **kwargs):
            raise AssertionError("Explicit reader construction must not inspect environment")

    monkeypatch.setattr(adapter, "create_engine", capture_engine)
    monkeypatch.setattr(adapter, "os", SimpleNamespace(environ=ForbiddenEnvironment()))
    reader = MySQLRentalReader(
        "mysql+pymysql://probe:unused@127.0.0.1/s6102_rel?read_timeout=999",
        **overrides,
    )
    assert not engines
    try:
        with pytest.raises(BeforeNetwork):
            getattr(reader, method)(*args)
        assert len(engines) == len(observed) == 1
        connect, read, write, pool = expected
        assert observed[0]["connect_timeout"] == connect
        assert observed[0]["read_timeout"] == read
        assert observed[0]["write_timeout"] == write
        assert observed[0]["charset"] == "utf8mb4"
        assert engines[0].pool.timeout() == pool
        assert engines[0].hide_parameters is True
    finally:
        reader.close()


@pytest.mark.parametrize("field", [
    "connect_timeout_s", "read_timeout_s", "write_timeout_s", "pool_timeout_s",
])
@pytest.mark.parametrize("invalid", [0, -1, math.inf, -math.inf, math.nan, True, False, None, "5"])
def test_timeout_values_reject_nonfinite_nonpositive_and_nonnumeric_inputs(field, invalid):
    with pytest.raises(RentalReaderConfigurationError, match=field):
        MySQLRentalReader(**{field: invalid})


def test_connect_timeout_respects_driver_maximum():
    with pytest.raises(RentalReaderConfigurationError, match="connect_timeout_s"):
        MySQLRentalReader(connect_timeout_s=31536001)


def test_actual_pymysql_read_timeout_and_owned_socket_cleanup():
    from scripts.hw05.part3.probe_driver_timeout import run_probe

    receipt = run_probe(read_timeout_s=0.1)
    assert receipt["passed"] is True
    assert receipt["control_proved"] == "PyMySQL read_timeout during stalled server greeting"
    assert receipt["exception_type"] == "sqlalchemy.exc.OperationalError"
    assert receipt["driver_exception_type"] == "pymysql.err.OperationalError"
    assert receipt["driver_error_code"] == 2013
    assert receipt["connection_accepted"] is True
    assert receipt["elapsed_within_bounds"] is True
    assert receipt["server_thread_stopped"] is True
    assert receipt["listener_closed"] is True
    assert receipt["accepted_socket_closed"] is True
    assert "probe:unused" not in json.dumps(receipt)
    assert "SELECT" not in json.dumps(receipt)


@pytest.mark.parametrize("invalid", [0, -1, math.inf, math.nan, True, "0.1", 2])
def test_probe_requires_a_short_finite_timeout(invalid):
    from scripts.hw05.part3.probe_driver_timeout import run_probe

    with pytest.raises(ValueError, match="read_timeout_s"):
        run_probe(read_timeout_s=invalid)
