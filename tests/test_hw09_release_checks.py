"""Regression checks for the HW9 setup and release evidence boundaries."""

import argparse
import json
import shutil

import pytest

from scripts import verify_hw09 as verifier


def test_development_inputs_cannot_be_rebound_after_freeze(tmp_path, monkeypatch):
    shutil.copytree(verifier.EVIDENCE / "raw/part4", tmp_path / "raw/part4")
    monkeypatch.setattr(verifier, "EVIDENCE", tmp_path)
    base = tmp_path / "raw/part4"
    training = base / "data/training_data.json"
    cases = json.loads(training.read_text())
    cases[0]["question"] += " Changed after freeze."
    training.write_text(json.dumps(cases))
    held_path = base / "held_out_results.json"
    held = json.loads(held_path.read_text())
    held["dataset_sha256"][training.name] = verifier.digest(training)
    held_path.write_text(json.dumps(held))
    with pytest.raises(AssertionError):
        verifier.verify_part4()


def test_live_check_rejects_a_server_from_another_revision(tmp_path):
    log = tmp_path / "api.log"
    log.write_text(
        json.dumps(
            {
                "event": "semantic_cache_ready",
                "threshold": 0.85,
                "allow_stale": False,
                "source_commit": "wrong-source",
            }
        )
        + "\n"
    )
    args = argparse.Namespace(api_log=log)
    with pytest.raises(AssertionError):
        verifier.verify_live(args, tmp_path)


def test_setup_validation_error_does_not_echo_private_input(tmp_path, monkeypatch, capsys):
    from scripts.hw04 import db_setup as hw4
    from scripts.hw05.part1 import db_setup as hw5
    from scripts.hw07 import db_setup as hw7
    from scripts.hw09 import setup

    env = tmp_path / "private.env"
    env.write_text("")
    monkeypatch.setattr("sys.argv", ["setup.py", "--env-file", str(env), "--seed-accounts"])
    monkeypatch.setenv("HW4_DATABASE_URL", "mysql+pymysql://test@127.0.0.1:1/s6102_rel")
    sentinel = "PRIVATE_SETUP_SENTINEL" * 60
    monkeypatch.setenv("HW7_READER_USERNAME", "test_reader")
    monkeypatch.setenv("HW7_READER_PASSWORD", sentinel)
    monkeypatch.setattr(hw4, "create_database", lambda: None)
    monkeypatch.setattr(hw4, "migrate", lambda *a, **kw: [])
    monkeypatch.setattr(hw5, "migrate", lambda *a, **kw: [])
    monkeypatch.setattr(hw7, "migrate", lambda *a, **kw: False)
    assert setup.main() == 1
    captured = capsys.readouterr()
    assert "PRIVATE_SETUP_SENTINEL" not in captured.out + captured.err
    assert "Setup failed (ValidationError)" in captured.err
