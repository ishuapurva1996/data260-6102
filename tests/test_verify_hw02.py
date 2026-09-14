"""Provenance and failure semantics of the whole-assignment verifier."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_hw02", ROOT / "scripts/verify_hw02.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class ProvenanceTests(unittest.TestCase):
    def test_changed_added_deleted_source_fail_but_generated_report_is_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "code").mkdir()
            source = root / "code/app.py"
            source.write_text("print('original')\n")
            for args in (["init", "-q"], ["add", "code"],
                         ["-c", "user.name=Verifier test", "-c", "user.email=test@example.com",
                          "commit", "-qm", "fixture"]):
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
            original = verify.source_snapshot(root, "HEAD")
            self.assertTrue(original["passed"])
            (root / "reports/hw02").mkdir(parents=True)
            (root / "reports/hw02/verification.json").write_text('{"passed":false}')
            self.assertEqual(verify.source_snapshot(root, "HEAD"), original)
            source.write_text("print('changed')\n")
            self.assertFalse(verify.source_snapshot(root, "HEAD")["passed"])
            source.unlink()
            self.assertFalse(verify.source_snapshot(root, "HEAD")["passed"])
            source.write_text("print('original')\n")
            (root / "code/untracked.py").write_text("pass\n")
            self.assertIn("code/untracked.py", verify.source_snapshot(root, "HEAD")["mismatches"])

    def test_output_cannot_replace_source_or_saved_evidence(self):
        for name in ("scripts/verify_hw02.py", "code/app.py", "reports/hw01/verification.json",
                     "reports/hw02/raw/check.json", "reports/hw02/deployment_choice.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify.validate_output(ROOT / name, ROOT)
        verify.validate_output(ROOT / "reports/hw02/verification.json", ROOT)

    def test_failed_command_and_missing_executable_do_not_pass(self):
        import sys
        failed = verify.command([sys.executable, "-c", "raise SystemExit(7)"], ROOT)
        self.assertEqual(failed["exit_code"], 7)
        self.assertFalse(failed["passed"])
        absent = verify.command(["/no/such/hw02-python"], ROOT)
        self.assertFalse(absent["passed"])

    def test_not_run_live_checks_cannot_claim_submission_ready(self):
        checks = {"offline": {"passed": True}, "live": {"passed": None, "status": "not_run"}}
        self.assertEqual(verify.outcome(checks, live=False, submission=False), (True, False))
        self.assertEqual(verify.outcome(checks, live=True, submission=True), (False, False))


if __name__ == "__main__":
    unittest.main()
