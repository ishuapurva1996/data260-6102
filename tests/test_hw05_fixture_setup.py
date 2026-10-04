"""Inspect administrative connection settings without opening a database connection."""

import socket
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.hw05.part2 import setup_fixture


def test_fixture_driver_options_have_finite_timeouts_without_connecting(monkeypatch):
    class ConnectionIntercepted(Exception):
        pass

    effective_options = {}

    def capture_engine(*args, **kwargs):
        engine = create_engine(*args, **kwargs)

        @event.listens_for(engine, "do_connect")
        def inspect_connection(dialect, connection_record, connection_args, connection_options):
            # SQLAlchemy has merged URL and connect_args into the actual driver options.
            effective_options.update(connection_options)
            raise ConnectionIntercepted

        return engine

    def forbid_network(*args, **kwargs):
        pytest.fail("The fixture connection-settings test must remain offline.")

    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    monkeypatch.setattr(setup_fixture, "create_engine", capture_engine)
    monkeypatch.setenv("HW5_FIXTURE_ADMIN_URL", "mysql+pymysql://offline:unused@127.0.0.1:3308/s6102_rel")
    monkeypatch.setenv("HW5_FIXTURE_READER_PASSWORD", "unused-offline-password")

    with pytest.raises(ConnectionIntercepted):
        setup_fixture.main()

    assert effective_options["host"] == "127.0.0.1"
    assert effective_options["port"] == 3308
    assert effective_options["database"] == "s6102_rel"
    assert effective_options["charset"] == "utf8mb4"
    assert effective_options["connect_timeout"] == 5
    assert effective_options["read_timeout"] == 10
    assert effective_options["write_timeout"] == 10
