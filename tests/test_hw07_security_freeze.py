"""Freeze integrity proofs; no real model, network, or application database."""

import importlib
import json
import shutil
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "changed", ["src/bikeshare/config.py", "src/bikeshare/policies.py", "src/bikeshare/service.py"]
)
def test_frozen_code_hashes_detect_configuration_fetch_and_supervisor_drift(
    tmp_path, monkeypatch, changed
):
    module = importlib.import_module("scripts.hw07.injection_experiment")
    root = Path(__file__).parents[1]
    for relative in set(module.code_hashes()) | {changed}:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    before = module.code_hashes()
    with (tmp_path / changed).open("a") as stream:
        stream.write("\n# controlled change to a frozen runtime dependency\n")
    assert module.code_hashes() != before


@pytest.mark.parametrize("raw_final_logged", [False, True])
def test_interrupted_worker_preserves_observed_raw_final_before_scoring(
    tmp_path, monkeypatch, raw_final_logged
):
    module = importlib.import_module("scripts.hw07.injection_experiment")
    sentinel = json.loads((module.CASES / "manifest.json").read_text())["sentinel"]
    raw = json.dumps({"decision": "Pay Per Ride/Minute", "justification": sentinel})
    freeze = tmp_path / "freeze.json"
    freeze.write_text(
        json.dumps(
            {
                "configuration": {"max_seconds": 1},
                "order": [
                    {"cell_id": "disclosure-before", "attack": "disclosure", "stage": "before"}
                ],
            }
        )
    )
    monkeypatch.setattr(module, "validate", lambda _: None)

    def interrupted_child(command, directory, *, timeout):
        trace = [
            {"event": "model_request", "reservation": {"total_tokens": 1}},
            {"event": "model_response", "message": {"content": raw, "tool_calls": []}},
        ]
        if raw_final_logged:
            trace.append({"event": "raw_final", "answer": raw, "before_verification": True})
        (directory / "trace.jsonl").write_text("".join(json.dumps(e) + "\n" for e in trace))
        return {"timed_out": True, "returncode": -15, "latency_ms": 1000}

    monkeypatch.setattr(module, "run_child", interrupted_child)
    output = tmp_path / "output"
    module.suite(freeze, output, tmp_path / "runtime")
    result = json.loads((output / "disclosure-before/result.json").read_text())
    score = json.loads((output / "disclosure-before/score.json").read_text())
    assert result["model_answer"] == raw
    assert score["recommendation_override"] and score["final_disclosure"]
    assert not score["verifier_accepted"]
    assert score["incomplete_evidence"]
