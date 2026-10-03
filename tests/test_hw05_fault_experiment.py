"""Controlled fixture checks; these tests do not claim MySQL timing evidence."""
import json
import math
import random
from collections import Counter

import pytest

from scripts.hw05.part3.fixture import FIXTURE, FixtureReader, fixture_sha256
from scripts.hw05.part3.run_fault_experiment import (
    RATES, compare_replay, derive_metrics, deterministic_projection,
    main, read_rows, run_experiment, run_rate,
)
from scripts.hw05.part3.run_retry_demos import run_demos
from src.rental_tools.reliability import RetryPolicy


def no_sleep(_delay):
    pass


@pytest.mark.parametrize("tamper", [None, "metrics", "rng"])
def test_independent_audit_recomputes_and_detects_altered_evidence(tmp_path, monkeypatch, tamper):
    import hashlib
    import scripts.hw05.part3.run_fault_experiment as runner
    from scripts.hw05.part3.recompute_metrics import audit

    original = runner.run_experiment
    monkeypatch.setattr(runner, "run_experiment", lambda **kwargs: original(**kwargs, _sleep=no_sleep))
    output = tmp_path / "unit-test-only"
    assert runner.main(["--output-dir", str(output), "--label", "diagnostic"]) == 0
    if tamper == "metrics":
        metrics = json.loads((output / "metrics.json").read_text())
        metrics[1]["mean_latency_ms"] += 100
        (output / "metrics.json").write_text(json.dumps(metrics))
    elif tamper == "rng":
        path = output / "rows.jsonl"
        rows = read_rows(path)
        rows[0]["trace"][0]["draw"] = 0.99
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        manifest = json.loads((output / "manifest.json").read_text())
        manifest["artifacts_sha256"]["rows.jsonl"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (output / "manifest.json").write_text(json.dumps(manifest))
    if tamper:
        with pytest.raises(AssertionError):
            audit(output)
    else:
        result = audit(output)
        assert result["passed"] and result["rows_checked"] == 150
        assert [row["successes"] for row in result["metrics"]] == [50, 50, 46]


def test_fixture_is_immutable_public_and_detached():
    reader = FixtureReader()
    with pytest.raises(TypeError):
        FIXTURE["rental"]["id"] = 2
    row = reader.get_rental(1)
    assert row["listing_title"] == "Campus apartment"
    row["id"] = 99
    assert reader.get_rental(1)["id"] == 1
    assert len(fixture_sha256()) == 64
    assert set(reader.get_rental(1)) == {
        "id", "listing_title", "property_address", "property_type", "manager_id", "description",
    }
    assert reader.search_rentals("campus", 5)[0]["id"] == 1
    assert reader.count_rentals(1) == {"manager_id": 1, "manager_name": "Campus Homes", "count": 1}


@pytest.mark.parametrize("rate", [-0.01, 1.01, math.nan, math.inf, True, "0.2", None])
def test_invalid_rate_rejected(rate):
    with pytest.raises((TypeError, ValueError)):
        run_rate(rate, _sleep=no_sleep)


def test_invalid_policy_rejected_before_running():
    with pytest.raises(TypeError):
        run_experiment(policy={"max_attempts": 3}, _sleep=no_sleep)
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=True)


@pytest.mark.parametrize("seed", [True, -1, 266102.0, "266102"])
def test_invalid_seed_rejected(seed):
    with pytest.raises(ValueError):
        run_experiment(seed=seed, _sleep=no_sleep)


def test_seeded_runs_replay_without_touching_global_rng():
    state = random.getstate()
    first = run_experiment(run_id="first", _sleep=no_sleep)
    second = run_experiment(run_id="second", _sleep=no_sleep)
    assert random.getstate() == state
    assert deterministic_projection(first) == deterministic_projection(second)
    assert compare_replay(first, second)["matched"] is True
    second[50]["trace"][0]["draw"] = 0.99
    assert compare_replay(first, second)["matched"] is False


def test_exact_call_mix_and_one_rng_draw_per_attempt_including_zero_rate():
    rows = run_experiment(_sleep=no_sleep)
    assert len(rows) == 150
    for rate in RATES:
        group = [row for row in rows if row["rate"] == rate]
        assert [row["logical_index"] for row in group] == list(range(1, 51))
        assert Counter(row["tool"] for row in group) == {
            "search_rentals": 17, "get_rental": 17, "count_rentals": 16,
        }
        expected_rng = random.Random(266102)
        for row in group:
            assert row["attempt_count"] == len(row["trace"])
            for number, attempt in enumerate(row["trace"], 1):
                assert attempt["attempt"] == number
                assert attempt["draw"] == expected_rng.random()
                assert attempt["injected"] == (attempt["draw"] < rate)
                assert attempt["operation"] == row["tool"]
                assert attempt["outcome"] == ("transient_error" if attempt["injected"] else "success")
                expected_sleep = (0.1 * 2 ** (number - 1)
                                  if attempt["injected"] and number < 3 else 0)
                assert attempt["sleep_s"] == expected_sleep
        if rate == 0:
            assert all(row["envelope"]["ok"] and row["attempt_count"] == 1 for row in group)


def test_every_method_can_exhaust_and_measures_failure_duration():
    ticks = iter(value for _ in range(50) for value in (10.0, 10.35))
    sleeps = []
    rows = run_rate(1.0, _sleep=sleeps.append, _clock=lambda: next(ticks))
    assert len(rows) == 50
    assert sleeps == [0.1, 0.2] * 50
    assert {row["tool"] for row in rows} == {"search_rentals", "get_rental", "count_rentals"}
    for row in rows:
        assert row["elapsed_ms"] == pytest.approx(350)
        assert row["envelope"] == {
            "ok": False, "data": None, "error": "Rental data is temporarily unavailable.",
        }
        assert row["attempt_count"] == 3


def test_metrics_use_all_fifty_durations_and_nearest_rank_p99():
    rows = run_experiment(_sleep=no_sleep)
    for row in rows:
        row["elapsed_ms"] = float(row["logical_index"])
    # The last 50%-rate observation is intentionally a longer failed call.
    rows[-1]["elapsed_ms"] = 350.0
    rows[-1]["envelope"] = {
        "ok": False, "data": None, "error": "Rental data is temporarily unavailable.",
    }
    metrics = derive_metrics(rows)
    assert len(metrics) == 3
    assert metrics[0]["mean_latency_ms"] == 25.5
    assert metrics[0]["p99_latency_ms"] == 50
    assert metrics[2]["mean_latency_ms"] == 31.5
    assert metrics[2]["p99_latency_ms"] == metrics[2]["maximum_latency_ms"] == 350
    assert metrics[2]["successes"] == sum(row["envelope"]["ok"] for row in rows[100:])


@pytest.mark.parametrize("change", ["missing", "duplicate", "nan", "negative", "wrong_tool", "wrong_input"])
def test_metrics_reject_invalid_selected_records(change):
    rows = run_experiment(_sleep=no_sleep)
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows[-1]["logical_index"] = 49
    elif change == "nan":
        rows[0]["elapsed_ms"] = math.nan
    elif change == "negative":
        rows[0]["elapsed_ms"] = -1
    elif change == "wrong_tool":
        rows[0]["tool"] = "get_rental"
    else:
        rows[0]["inputs"]["query"] = "different"
    with pytest.raises(ValueError):
        derive_metrics(rows)


def test_scripted_demonstrations_are_separate_and_sanitized():
    sleeps = []
    demos = run_demos(_sleep=sleeps.append)
    assert [demo["attempt_count"] for demo in demos] == [1, 2, 3]
    assert [demo["envelope"]["ok"] for demo in demos] == [True, True, False]
    assert sleeps == [0.1, 0.1, 0.2]
    assert [item["injected"] for item in demos[-1]["trace"]] == [True, True, True]
    assert demos[-1]["envelope"]["error"] == "Rental data is temporarily unavailable."


def test_cli_writes_raw_before_metrics_and_refuses_overwrite(tmp_path, monkeypatch):
    import scripts.hw05.part3.run_fault_experiment as runner

    original = runner.run_experiment
    monkeypatch.setattr(runner, "run_experiment", lambda **kw: original(**kw, _sleep=no_sleep))
    original_metrics = runner.derive_metrics
    output = tmp_path / "selected"

    def checked_metrics(rows):
        assert len(read_rows(output / "rows.jsonl")) == 150
        return original_metrics(rows)

    monkeypatch.setattr(runner, "derive_metrics", checked_metrics)
    assert main(["--output-dir", str(output), "--label", "selected"]) == 0
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["label"] == "selected"
    assert manifest["seed"] == 266102
    assert manifest["fixture_sha256"] == fixture_sha256()
    assert manifest["policy"]["max_attempts"] == 3
    assert manifest["source"]["git_revision"]
    assert isinstance(manifest["source"]["dirty"], bool)
    assert manifest["source"]["sha256"]
    assert manifest["versions"]["python"]
    assert manifest["started_at_utc"].endswith("+00:00")
    assert manifest["completed_at_utc"].endswith("+00:00")
    assert "--label selected" in manifest["command"]
    assert main(["--output-dir", str(output), "--label", "selected"]) != 0


def test_replay_cli_retains_separate_output_and_mismatch_receipt(tmp_path, monkeypatch):
    import scripts.hw05.part3.run_fault_experiment as runner

    original = runner.run_experiment
    monkeypatch.setattr(runner, "run_experiment", lambda **kw: original(**kw, _sleep=no_sleep))
    selected = tmp_path / "selected"
    replay = tmp_path / "replay"
    assert main(["--output-dir", str(selected), "--label", "selected"]) == 0
    raw_path = selected / "rows.jsonl"
    original_bytes = raw_path.read_bytes()
    assert main(["--output-dir", str(replay), "--label", "replay", "--compare-to", str(raw_path)]) == 0
    assert raw_path.read_bytes() == original_bytes
    receipt = json.loads((replay / "replay-comparison.json").read_text())
    assert receipt["matched"] is True
    assert receipt["logical_calls_compared"] == 150
    assert receipt["selected_rows_sha256"]
    altered = read_rows(raw_path)
    altered[0]["trace"][0]["draw"] = 0.99
    altered_path = tmp_path / "altered.jsonl"
    altered_path.write_text("\n".join(json.dumps(row) for row in altered) + "\n")
    mismatch = tmp_path / "mismatch"
    assert main(["--output-dir", str(mismatch), "--label", "replay", "--compare-to", str(altered_path)]) == 1
    receipt = json.loads((mismatch / "replay-comparison.json").read_text())
    assert receipt["matched"] is False
    assert receipt["mismatched_row_numbers"] == [1]


def test_demos_cli_has_name_safe_envelope_and_trace(tmp_path, monkeypatch, capsys):
    import scripts.hw05.part3.run_retry_demos as runner

    original = runner.run_demos
    monkeypatch.setattr(runner, "run_demos", lambda: original(_sleep=no_sleep))
    output = tmp_path / "demos"
    assert runner.main(["--output-dir", str(output)]) == 0
    transcript = capsys.readouterr().out
    assert "Pragya Apurva" in transcript
    assert "retry_exhaustion: ok=False attempts=3 sleeps=[0.1, 0.2]" in transcript
    assert '"error": "Rental data is temporarily unavailable."' in transcript
    assert "trace=" in transcript
    assert len(json.loads((output / "demonstrations.json").read_text())) == 3
    assert runner.main(["--output-dir", str(output)]) != 0
