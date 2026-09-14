"""Artifact refresh must retain the provenance of the original live checks."""

from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "refresh_hw02_artifacts", ROOT / "scripts/refresh_hw02_artifacts.py")
refresh_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh_module)


def prior_verification():
    commit = "a" * 40
    hashes = {"code/app.py": "b" * 64}
    source = {"passed": True, "commit": commit, "ref": "hw2-code",
              "ref_sha256": hashes, "checkout_sha256": dict(hashes), "mismatches": {}}
    config = {"base_url": "http://localhost:11434", "temperature": 0.0,
              "timeout": 120.0, "max_turns": 10, "response_format": "json",
              "reasoning": False, "num_ctx": 4096}
    outcomes = []
    for name, code, status, turns in (("normal_reviewer", 0, "accepted", 2),
                                     ("controlled_always_issue", 1, "turn_limit", 10)):
        outcomes.append({"name": name, "passed": True, "exit_code": code,
                         "validation": {"passed": True, "status": status, "turn_count": turns},
                         "run": {"status": status, "turn_count": turns, "max_turns": 10,
                                 "adapter_response_count": turns,
                                 "config": {**config, "model": "qwen3:1.7b",
                                            "controlled_reviewer": bool(code)}}})
    after = deepcopy(source)
    after["ref"] = commit
    return {
        "assignment": "HW2", "HW": 2, "SID4": "6102", "DOMAIN_ID": 6,
        "PORT_BASE": 8702, "SEED": 6102, "VERIFY_SEED": 266102,
        "passed": True, "submission_ready": True, "live_requested": True,
        "submission_artifacts_required": True, "ref": "hw2-code", "commit_hash": commit,
        "generated_at": "2026-09-14T08:09:16.462074+00:00", "model": "qwen3:1.7b",
        "config": config, "command": ["python", "scripts/verify_hw02.py", "--live"],
        "checks": {
            "source_ref_matches_checkout": source,
            "isolated_web_crud": {"passed": True},
            "deterministic_graph_smoke": {"passed": True},
            "saved_part4_evidence": {"passed": True},
            "live_web_8702": {"passed": True, "live_server_mutations": 0},
            "live_graph_termination": {"passed": True, "exit_code": 0,
                                       "details": {"passed": True, "real_model": True,
                                                   "model_calls": 12, "outcomes": outcomes}},
            "submission_artifacts": {"passed": True, "files": {
                "report.pdf": {"bytes": 8, "sha256": "c" * 64}}},
            "source_unchanged_during_checks": after,
        },
    }


class ArtifactRefreshTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.prior_path = Path(temporary.name).resolve() / "verification.json"
        self.prior = prior_verification()
        self.current_source = deepcopy(self.prior["checks"]["source_ref_matches_checkout"])
        self.command = ["python", "scripts/refresh_hw02_artifacts.py", "--prior", str(self.prior_path)]

    def refresh(self, prior=None):
        self.prior_path.write_text(json.dumps(self.prior if prior is None else prior))
        original_bytes = self.prior_path.read_bytes()
        result = refresh_module.refresh(self.prior_path, self.command)
        self.assertEqual(self.prior_path.read_bytes(), original_bytes)
        return result

    def assert_blocked(self, result, artifacts):
        self.assertIs(result["passed"], False)
        self.assertIs(result["submission_ready"], False)
        self.assertIs(result["checks"]["submission_artifacts"]["passed"], False)
        self.assertEqual(result["checks"]["submission_artifacts"]["status"], "not_run")
        artifacts.assert_not_called()

    def test_refresh_preserves_live_evidence_and_records_artifact_update(self):
        updated = {"passed": True, "files": {"report.pdf": {"bytes": 16, "sha256": "d" * 64}}}
        with patch.object(refresh_module.verifier, "source_snapshot", return_value=self.current_source), \
                patch.object(refresh_module.verifier, "submission_artifacts", return_value=updated):
            result = self.refresh()
        self.assertIs(result["passed"], True)
        self.assertIs(result["submission_ready"], True)
        metadata = result["artifact_refresh"]
        self.assertIs(metadata["passed"], True)
        self.assertIs(metadata["live_checks_rerun"], False)
        self.assertEqual(metadata["model_calls"], 0)
        self.assertEqual(metadata["command"], self.command)
        self.assertEqual(metadata["prior_verification"], {
            "path": str(self.prior_path),
            "sha256": hashlib.sha256(self.prior_path.read_bytes()).hexdigest()})
        self.assertEqual(metadata["helper_source_sha256"],
                         hashlib.sha256(Path(refresh_module.__file__).read_bytes()).hexdigest())
        self.assertTrue(datetime.fromisoformat(metadata["checked_at"]).tzinfo)
        self.assertTrue(metadata["scope"])
        self.assertTrue(metadata["checks"])
        artifacts = result["checks"]["submission_artifacts"]
        self.assertEqual(artifacts["files"], updated["files"])
        self.assertGreaterEqual(artifacts["checked_at"], metadata["checked_at"])
        self.assertLessEqual(artifacts["checked_at"], metadata["finished_at"])
        expected = deepcopy(self.prior)
        expected["checks"]["submission_artifacts"] = artifacts
        expected["artifact_refresh"] = metadata
        self.assertEqual(result, expected)

    def test_changed_current_source_blocks_artifact_refresh(self):
        self.current_source.update(passed=False, mismatches={"code/app.py": {"changed": True}})
        with patch.object(refresh_module.verifier, "source_snapshot", return_value=self.current_source) as snapshot, \
                patch.object(refresh_module.verifier, "submission_artifacts") as artifacts:
            self.assert_blocked(self.refresh(), artifacts)
            snapshot.assert_called()

    def test_tampered_prior_hashes_fail_even_when_checkout_matches_tag(self):
        tampered = deepcopy(self.prior)
        for name in ("source_ref_matches_checkout", "source_unchanged_during_checks"):
            for key in ("ref_sha256", "checkout_sha256"):
                tampered["checks"][name][key]["code/app.py"] = "e" * 64
        with patch.object(refresh_module.verifier, "source_snapshot", return_value=self.current_source) as snapshot, \
                patch.object(refresh_module.verifier, "submission_artifacts") as artifacts:
            self.assert_blocked(self.refresh(tampered), artifacts)
            snapshot.assert_called()


if __name__ == "__main__":
    unittest.main()
