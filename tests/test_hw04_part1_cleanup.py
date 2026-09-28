"""Check the browser runner's cleanup guards without a live service or MySQL."""
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser_hw04_part1_runtime as runtime


@pytest.fixture
def engine():
    database = create_engine("sqlite:///:memory:")
    with database.begin() as connection:
        connection.execute(text("CREATE TABLE rentals (id INTEGER PRIMARY KEY, description TEXT, submitter_email TEXT)"))
    yield database
    database.dispose()


@pytest.fixture
def journal(tmp_path):
    run_id = str(uuid4())
    path = tmp_path / "rental.json"
    payload = {"schema_version": 1, "run_id": run_id, "record_id": 17, "phase": "created"}
    path.write_text(json.dumps(payload))
    path.chmod(0o600)
    return path, payload


def write_journal(journal, **changes):
    path, payload = journal
    payload.update(changes)
    path.write_text(json.dumps(payload))
    return path


def insert_row(engine, record_id, run_id=None, **overrides):
    values = {
        "id": record_id,
        "description": f"HW4 Part 1 browser cleanup run {run_id}" if run_id else "An unrelated rental that must remain intact.",
        "email": f"{run_id}@example.com" if run_id else "unrelated@example.invalid",
    }
    values.update(overrides)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO rentals (id, description, submitter_email) VALUES (:id, :description, :email)"), values)


def rows(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT id, description, submitter_email FROM rentals ORDER BY id")).all()


def assert_recovery(result, path):
    assert path.exists(), "An unresolved cleanup must retain its recovery journal"
    assert Path(result["recovery_journal"]) == path


def test_deletes_only_the_exact_owned_row(engine, journal):
    path, payload = journal
    insert_row(engine, 17, payload["run_id"])
    insert_row(engine, 18)
    unrelated = rows(engine)[1]

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "deleted"
    assert result["record_id"] == 17
    assert rows(engine) == [unrelated]
    assert not path.exists()


def test_already_deleted_row_is_safe(engine, journal):
    path, _ = journal
    insert_row(engine, 18)
    before = rows(engine)

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "already_absent"
    assert result["record_id"] == 17
    assert rows(engine) == before
    assert not path.exists()


@pytest.mark.parametrize("mismatch", ["description", "email"])
def test_refuses_same_id_when_either_ownership_field_differs(engine, journal, mismatch):
    path, payload = journal
    override = {mismatch: "Somebody else's rental" if mismatch == "description" else "somebody@example.invalid"}
    insert_row(engine, 17, payload["run_id"], **override)
    before = rows(engine)

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "ownership_mismatch"
    assert rows(engine) == before
    assert_recovery(result, path)


def test_pending_create_recovers_one_exact_marker_match(engine, journal):
    path, payload = journal
    write_journal(journal, record_id=None, phase="create_pending")
    insert_row(engine, 29, payload["run_id"])
    # The same description without this run's exact email does not confer ownership.
    insert_row(engine, 30, payload["run_id"], email="unrelated@example.invalid")
    unrelated = rows(engine)[1]

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "deleted"
    assert result["record_id"] == 29
    assert rows(engine) == [unrelated]
    assert not path.exists()


def test_pending_create_without_match_is_safe(engine, journal):
    path = write_journal(journal, record_id=None, phase="create_pending")
    insert_row(engine, 18)
    before = rows(engine)

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "not_created"
    assert rows(engine) == before
    assert not path.exists()


def test_ambiguous_marker_never_deletes_multiple_rows(engine, journal):
    path, payload = journal
    write_journal(journal, record_id=None, phase="create_pending")
    insert_row(engine, 17, payload["run_id"])
    insert_row(engine, 18, payload["run_id"])
    before = rows(engine)

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "ambiguous"
    assert rows(engine) == before
    assert_recovery(result, path)


class FailingEngine:
    def __init__(self):
        self.connection_attempts = 0

    def begin(self):
        self.connection_attempts += 1
        raise RuntimeError("private-connection-password-must-not-leak")


def test_connection_failure_retains_recovery_without_error_secrets(journal):
    path, _ = journal
    engine = FailingEngine()

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "failed"
    assert engine.connection_attempts == 1
    assert "private-connection-password-must-not-leak" not in json.dumps(result)
    assert_recovery(result, path)


@pytest.mark.parametrize("invalid_id", [0, -1, True, "17", 17.5])
def test_malformed_id_is_rejected_before_database_access(journal, invalid_id):
    path = write_journal(journal, record_id=invalid_id)
    engine = FailingEngine()

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "failed"
    assert engine.connection_attempts == 0
    assert "private-connection-password-must-not-leak" not in json.dumps(result)
    assert_recovery(result, path)


@pytest.mark.parametrize("invalid_run_id", [None, "not-a-uuid", "../../other-run"])
def test_malformed_run_id_is_rejected_before_database_access(journal, invalid_run_id):
    path = write_journal(journal, run_id=invalid_run_id)
    engine = FailingEngine()

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "failed"
    assert engine.connection_attempts == 0
    assert "private-connection-password-must-not-leak" not in json.dumps(result)
    assert_recovery(result, path)


def test_not_started_does_not_connect_or_leave_recovery(journal):
    path = write_journal(journal, record_id=None, phase="not_started")
    engine = FailingEngine()

    result = runtime.cleanup_rental(path, engine)

    assert result["status"] == "not_created"
    assert engine.connection_attempts == 0
    assert not path.exists()
