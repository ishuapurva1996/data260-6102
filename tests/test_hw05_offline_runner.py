"""Process-level checks for the deterministic Part 4 fixture assertion runner."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hw05" / "run_offline_tests.py"
CASE_NAMES = (
    "valid_search",
    "whitespace_search_rejected",
    "valid_rental_detail",
    "missing_rental_8_rejected",
    "valid_manager_count",
    "missing_manager_4_rejected",
)
EXPECTED_OUTPUT = "\n".join((
    "Pragya Apurva - HW5 Part 4 offline assertions",
    *(f"PASS {name}" for name in CASE_NAMES),
    "6/6 passed",
    "",
))


def run_python(*arguments):
    env = os.environ.copy()
    for key in (
        "HW5_MCP_DATABASE_URL", "HW4_DATABASE_URL", "HW4_TEST_DATABASE_URL",
        "DATABASE_URL", "OLLAMA_HOST", "OPENAI_API_KEY", "PYTHONOPTIMIZE",
    ):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", *map(str, arguments)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
    )


def test_six_required_cases_run_repeatably_without_live_configuration():
    first = run_python(SCRIPT)
    second = run_python(SCRIPT)
    for result in (first, second):
        assert result.returncode == 0, result.stderr
        assert result.stdout == EXPECTED_OUTPUT
        assert result.stderr == ""


@pytest.mark.parametrize("exception", ["AssertionError", "RuntimeError"])
def test_failed_case_exits_nonzero_and_still_runs_every_required_case(exception):
    result = run_python("-c", f"""
from scripts.hw05 import run_offline_tests as runner

def fail():
    raise {exception}("private exception detail must not be printed")

raise SystemExit(runner.main(cases=(("injected_failure", fail), *runner.CASES)))
""")
    assert result.returncode == 1, result.stderr
    assert result.stdout.splitlines() == [
        "Pragya Apurva - HW5 Part 4 offline assertions",
        f"FAIL injected_failure ({exception})",
        *(f"PASS {name}" for name in CASE_NAMES),
        "6/7 passed",
    ]
    assert result.stderr == ""


@pytest.mark.parametrize("optimization", ["-O", "-OO"])
def test_optimized_python_is_rejected(optimization):
    result = run_python(optimization, SCRIPT)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() == (
        "ERROR: Python optimization disables assertions; run without -O."
    )


def test_import_and_all_assertions_never_use_live_dependencies():
    # Bootstrap dependency packages, then guard before any production/runner import.
    # Record calls before raising so the service cannot hide attempted I/O by
    # converting a guard exception into an ordinary error envelope.
    result = run_python("-c", """
import contextlib
import importlib.abc
import io
import os
import socket
import sys
from unittest.mock import patch

import pydantic
import pymysql
import sqlalchemy

attempts = []

def forbidden(*args, **kwargs):
    attempts.append("live dependency")
    raise AssertionError("Live dependency accessed by offline runner")

class NoRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "src.rental_tools.runtime":
            forbidden()
        return None

original_getitem = os._Environ.__getitem__
def guarded_getitem(self, key):
    if key in {
        "HW5_MCP_DATABASE_URL", "HW4_DATABASE_URL", "HW4_TEST_DATABASE_URL",
        "DATABASE_URL", "OLLAMA_HOST", "OPENAI_API_KEY",
    }:
        forbidden()
    return original_getitem(self, key)

sys.meta_path.insert(0, NoRuntime())
assert "src.rental_tools.executor" not in sys.modules
with contextlib.ExitStack() as guards:
    for owner, attribute in (
        (sqlalchemy, "create_engine"),
        (pymysql, "connect"),
        (pymysql.connections.Connection, "__init__"),
        (socket.socket, "connect"),
        (socket.socket, "connect_ex"),
        (socket, "create_connection"),
        (socket, "getaddrinfo"),
    ):
        guards.enter_context(patch.object(owner, attribute, forbidden))
    guards.enter_context(patch.object(os._Environ, "__getitem__", guarded_getitem))
    imported_output = io.StringIO()
    with contextlib.redirect_stdout(imported_output):
        from scripts.hw05 import run_offline_tests as runner
    assert imported_output.getvalue() == ""
    from src.rental_tools.reader import MySQLRentalReader
    guards.enter_context(patch.object(MySQLRentalReader, "__init__", forbidden))
    status = runner.main()
    assert status == 0
    assert attempts == [], attempts
    assert "src.rental_tools.runtime" not in sys.modules
""")
    assert result.returncode == 0, result.stderr
    assert result.stdout == EXPECTED_OUTPUT
    assert result.stderr == ""


def test_fixture_has_fixed_ids_relationships_and_private_projection_sentinels():
    from scripts.hw05.part4.fixture import FixtureReader, PRIVATE_SENTINEL

    reader = FixtureReader()
    assert [row["id"] for row in reader.search_rentals("garden", 5)] == [1, 2]
    assert [row["id"] for row in reader.search_rentals("garden", 1)] == [1]
    assert reader.get_rental(8) is None
    assert reader.count_rentals(4) is None
    assert reader.count_rentals(1)["count"] == 2
    assert reader.count_rentals(2)["count"] == 1
    assert reader.count_rentals(3)["count"] == 0
    assert {reader.get_rental(rental_id)["id"] for rental_id in (1, 2, 7)} == {1, 2, 7}
    assert reader.get_rental(1)["submitter_email"] == PRIVATE_SENTINEL
    assert reader.get_rental(7)["password_hash"] == PRIVATE_SENTINEL
    assert reader.count_rentals(1)["manager_email"] == PRIVATE_SENTINEL


def test_no_match_and_existing_empty_manager_remain_successes():
    import json

    from scripts.hw05.part4.fixture import FixtureReader
    from src.rental_tools.executor import execute_tool
    from src.rental_tools.service import RentalService

    service = RentalService(FixtureReader())
    assert json.loads(execute_tool("search_rentals", {"query": "unmatched"}, service=service)) == {
        "ok": True, "data": {"items": [], "returnedCount": 0, "limit": 5}, "error": None,
    }
    assert json.loads(execute_tool("count_rentals", {"manager_id": 3}, service=service)) == {
        "ok": True, "data": {"managerId": 3, "managerName": "Empty Manager", "count": 0},
        "error": None,
    }
