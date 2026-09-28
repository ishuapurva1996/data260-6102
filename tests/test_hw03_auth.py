"""Historical HW3 evidence-verifier unit tests remain supported.

The active HW3 signed-cookie/Jinja/public-API tests were deliberately superseded
by test_hw04_auth.py and test_api.py. HW4 requires opaque MySQL-backed sessions,
JSON login by email, authenticated CRUD, and persistence across app instances;
asserting the former runtime behavior would enforce the wrong assignment.
Historical HW3 report evidence is unchanged.
"""
import importlib.util
import json
from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "code/web_application/main.py"


def load_verifier():
    verifier_path = APP_PATH.parents[2] / "scripts/verify_hw03_part1.py"
    spec = importlib.util.spec_from_file_location("part1_verifier", verifier_path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    return verifier


def test_verifier_does_not_trust_overall_browser_pass_with_failed_check(tmp_path):
    verifier = load_verifier()
    checks = verifier.evidence_checks(tmp_path, {
        "status": "pass", "checks": [{"name": "logout replay", "status": "fail"}],
    })
    assert next(c for c in checks if c["name"] == "browser_individual_checks_passed")["passed"] is False


def test_verifier_reports_missing_screenshot(tmp_path):
    verifier = load_verifier()
    checks = verifier.evidence_checks(tmp_path, {
        "status": "pass", "checks": [{"name": "desktop", "status": "pass"}],
        "screenshots": [{"file": "missing.png"}],
    })
    assert next(c for c in checks if c["name"] == "screenshot_exists:missing.png")["passed"] is False


def test_verifier_exits_nonzero_when_auth_tests_fail(monkeypatch, tmp_path):
    from types import SimpleNamespace
    verifier = load_verifier()
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    auth = tmp_path / "code/web_application/routers/auth.py"
    auth.parent.mkdir(parents=True)
    auth.write_text("# test fixture\n")
    monkeypatch.setattr(verifier.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=1, stdout="FAILED auth replay check", stderr=""))
    monkeypatch.setattr(verifier.subprocess, "check_output", lambda *a, **kw: "test-revision")
    output = tmp_path / "verification.json"
    assert verifier.main(["--output", str(output)]) == 1
    result = json.loads(output.read_text())
    assert result["status"] == "fail"
    assert next(c for c in result["checks"] if c["name"] == "pytest_exit_status")["passed"] is False
    assert next(c for c in result["checks"] if c["name"] == "browser_evidence_readable")["passed"] is False


def test_verifier_uses_actual_replay_evidence_not_display_label(tmp_path):
    verifier = load_verifier()
    details = {"fresh_browser_context": True, "copied_cookie_actually_sent": True,
               "dashboard_response": {"status": 303, "headers": [{"name": "location", "value": "/login"}]}}
    evidence = {"status": "pass", "checks": [
        {"name": name, "status": "pass", "details": details}
        for name in ["desktop copied cookie after logout", "mobile copied cookie after logout", "copied cookie after idle time"]
    ]}
    checks = verifier.evidence_checks(tmp_path, evidence)
    assert next(c for c in checks if c["name"] == "browser_covers_replay")["passed"] is True
    details["copied_cookie_actually_sent"] = False
    checks = verifier.evidence_checks(tmp_path, evidence)
    assert next(c for c in checks if c["name"] == "browser_covers_replay")["passed"] is False
