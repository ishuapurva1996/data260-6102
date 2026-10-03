"""Prove a real PyMySQL socket read timeout using an owned stalled greeting.

This probes the reader's configured read_timeout, not a query deadline, TCP
connect timeout, write timeout, pool exhaustion, or a running MySQL database.
No SQL reaches the owned socket because the server never sends its greeting.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from sqlalchemy.exc import DBAPIError

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.rental_tools.reader import MySQLRentalReader


def _type_name(error: BaseException | None) -> str | None:
    return None if error is None else f"{type(error).__module__}.{type(error).__name__}"


def run_probe(*, read_timeout_s: float = 0.2) -> dict:
    """Return safe evidence; always close both sockets and stop the server thread."""
    if (isinstance(read_timeout_s, bool) or not isinstance(read_timeout_s, (int, float))
            or not 0 < read_timeout_s <= 1):
        raise ValueError("read_timeout_s must be a finite number greater than 0 and at most 1.")

    started_utc = datetime.now(timezone.utc).isoformat()
    # Broad tolerance for scheduling/engine setup; the server stays open longer
    # so server shutdown cannot impersonate a timely driver read timeout.
    lower_s = read_timeout_s * 0.75
    upper_s = read_timeout_s + 1.5
    hold_s = upper_s + 1
    stop = threading.Event()
    accepted = threading.Event()
    socket_closed = threading.Event()
    server_expired = threading.Event()
    server_errors: list[str] = []
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    reader = None
    server = None
    error = None
    elapsed_s = 0.0

    def stalled_greeting():
        try:
            while not stop.is_set():
                try:
                    connection, _ = listener.accept()
                    break
                except TimeoutError:
                    continue
            else:
                return
            try:
                with connection:
                    accepted.set()
                    if not stop.wait(hold_s):
                        server_expired.set()
            finally:
                socket_closed.set()
        except OSError as server_error:
            if not stop.is_set():
                server_errors.append(_type_name(server_error))

    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.1)
        port = listener.getsockname()[1]
        server = threading.Thread(target=stalled_greeting, name="hw05-part3-timeout-probe")
        server.start()
        reader = MySQLRentalReader(
            f"mysql+pymysql://timeout_probe@127.0.0.1:{port}/s6102_rel",
            connect_timeout_s=1, read_timeout_s=read_timeout_s,
            write_timeout_s=1, pool_timeout_s=1,
        )
        started = time.perf_counter()
        try:
            reader.get_rental(1)
        except Exception as read_error:
            error = read_error
        finally:
            elapsed_s = time.perf_counter() - started
    finally:
        stop.set()
        listener.close()
        if server is not None:
            server.join(timeout=2)
        if reader is not None:
            reader.close()

    driver_error = error.orig if isinstance(error, DBAPIError) else None
    args = driver_error.args if driver_error is not None else ()
    code = args[0] if args and type(args[0]) is int else None
    elapsed_within_bounds = lower_s <= elapsed_s <= upper_s
    server_stopped = server is not None and not server.is_alive()
    passed = (
        _type_name(error) == "sqlalchemy.exc.OperationalError"
        and _type_name(driver_error) == "pymysql.err.OperationalError"
        and code == 2013 and accepted.is_set() and elapsed_within_bounds
        and server_stopped and socket_closed.is_set()
        and not server_expired.is_set() and not server_errors
    )
    return {
        "student": "Pragya Apurva",
        "passed": passed,
        "control_proved": "PyMySQL read_timeout during stalled server greeting",
        "read_timeout_s": read_timeout_s,
        "connect_timeout_s": 1,
        "write_timeout_s": 1,
        "pool_timeout_s": 1,
        "elapsed_ms": elapsed_s * 1000,
        "elapsed_bounds_ms": [lower_s * 1000, upper_s * 1000],
        "elapsed_within_bounds": elapsed_within_bounds,
        "exception_type": _type_name(error),
        "driver_exception_type": _type_name(driver_error),
        "driver_error_code": code,
        "connection_accepted": accepted.is_set(),
        "server_hold_expired": server_expired.is_set(),
        "server_error_types": server_errors,
        "server_thread_stopped": server_stopped,
        "listener_closed": listener.fileno() == -1,
        "accepted_socket_closed": socket_closed.is_set(),
        "started_utc": started_utc,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "versions": {"PyMySQL": version("PyMySQL"), "SQLAlchemy": version("SQLAlchemy")},
        "limitations": "Stalled greeting only; not live MySQL, other timeout controls, or a whole-call deadline.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-timeout-s", type=float, default=0.2)
    args = parser.parse_args()
    receipt = run_probe(read_timeout_s=args.read_timeout_s)
    receipt["command"] = [sys.executable, *sys.argv]
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
