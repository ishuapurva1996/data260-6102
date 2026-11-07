"""The integrated verifier must reject altered held-out evidence."""

import json
import shutil

import pytest

from scripts import verify_hw09 as verifier


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    shutil.copytree(verifier.EVIDENCE / "raw/part4", tmp_path / "raw/part4")
    monkeypatch.setattr(verifier, "EVIDENCE", tmp_path)
    return tmp_path / "raw/part4"


def test_original_held_out_evidence_regrades(evidence):
    assert verifier.verify_part4()["independently_regraded"] == 40


@pytest.mark.parametrize("change", ["third_attempt", "wrong_claim", "different_input"])
def test_modified_held_out_evidence_is_rejected(evidence, change):
    path = evidence / "held_out_results.json"
    result = json.loads(path.read_text())
    case = result["variants"][1]["cases"][0]
    if change == "third_attempt":
        case["attempts"] = [case["attempts"][0]] * 3
    elif change == "wrong_claim":
        case["attempts"][-1]["answer"]["claims"] = {"available_units": 999}
    else:
        case["question"]["question"] = "Changed after the freeze"
    path.write_text(json.dumps(result))
    with pytest.raises(AssertionError):
        verifier.verify_part4()
