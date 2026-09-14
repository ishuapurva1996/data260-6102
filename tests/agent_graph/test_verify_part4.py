"""Offline verifier integration fixtures are deterministic, never measured runs."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


verifier = module("part4_verifier_test", "scripts/verify_part4.py")
runner = verifier.experiments
cli = module("part4_verify_graph_test", "code/agents_graph.py")
from src.model_client import CompletionResult, TokenUsage


class Adapter:
    def __init__(self):
        self.responses = iter([
            {"tags": ["apartment", "transit", "parking"], "summary": "Apartment near transit with parking."},
            {"issues": []},
        ])

    def complete(self, messages):
        return CompletionResult(json.dumps(next(self.responses)), TokenUsage(7, 3, 10), None)


class VerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = tempfile.TemporaryDirectory()
        base = Path(cls.seed.name)
        case = base / "case.json"
        case.write_text(json.dumps({"title": "Apartment", "content": "Near transit with parking."}))
        adversarial = base / "adversarial.json"
        adversarial.write_text(json.dumps({"title": "Apartment", "content": "Near transit. Parking included; no parking provided."}))
        cls.campaign = base / "fixture-campaign"
        git = {"commit": "a" * 40, "branch": "fixture", "dirty": True, "status": "?? fixture"}
        with patch.object(runner, "model_identity", return_value={"name": "qwen3:1.7b", "digest": "b" * 64}), \
             patch.object(runner, "git_metadata", return_value=git):
            manifest = runner.prepare_campaign(cls.campaign, case, adversarial)
        args = cli.parse_args(["--input-json", str(case)])
        with patch.object(cli, "_git_metadata", return_value={"commit": git["commit"], "dirty": True}):
            template = cli.run_graph(args, llm=Adapter())
        warmup = dict(trial_id="warmup-fixture", cohort="warmup", order=0, max_turns=10, input_key="schema", pair=None)
        for slot in [warmup, *manifest["schedule"]]:
            folder = "warmups" if slot["cohort"] == "warmup" else "trials"
            directory = cls.campaign / folder / slot["trial_id"]
            directory.mkdir(parents=True)
            raw = deepcopy(template)
            raw.update(run_id="fixture-" + slot["trial_id"], max_turns=slot["max_turns"], elapsed_ms=100.125)
            raw["input"] = {**runner.read_json(adversarial if slot["input_key"] == "adversarial" else case), "email": None}
            raw["config"]["max_turns"] = slot["max_turns"]
            cli._write_evidence(raw, directory / "cli", "deterministic fixture, not measured\n")
            (directory / "stdout.json").write_bytes(runner.json_bytes(raw))
            (directory / "stderr.txt").write_text("deterministic fixture, not measured\n")
            base_row = runner.trial_base(manifest, slot)
            runner.write_new(directory / "started.json", {**base_row, "started_at": raw["started_at"],
                             "command": [sys.executable, "code/agents_graph.py"], "git": git})
            record = {**base_row, **runner.classify_result(raw), "returncode": 0,
                      "finished_at": raw["finished_at"], "subprocess_wall_ms": 110.0,
                      "operational_error": None, "cli_evidence": True,
                      "evidence": f"{folder}/{slot['trial_id']}/cli/{raw['run_id']}/result.json"}
            record["files_sha256"] = {p.relative_to(directory).as_posix(): runner.digest(p.read_bytes())
                                       for p in directory.rglob("*") if p.is_file()}
            runner.write_new(directory / "result.json", record)
        runner.write_report(cls.campaign)

    @classmethod
    def tearDownClass(cls):
        cls.seed.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "copied campaign with spaces"
        shutil.copytree(self.campaign, self.path)

    def test_complete_copied_fixture_passes_without_model_or_network(self):
        with patch("src.model_client.build_ollama_client", side_effect=AssertionError("model called")), \
             patch.object(runner, "model_identity", side_effect=AssertionError("model inspected")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network called")):
            result = verifier.verify_campaign(self.path)
        self.assertTrue(result["passed"], result["checks"])
        self.assertEqual(result["measured_counts"]["total"], 75)
        self.assertEqual(result["recomputed"]["deployment_max_turns"], 2)
        self.assertIn("not model RNG", result["seed_note"])

    def test_missing_terminal_fails_and_preserves_interrupted_trial(self):
        terminal = self.path / "trials/schema-01/result.json"
        terminal.unlink()
        result = verifier.verify_campaign(self.path)
        self.assertFalse(result["passed"])
        self.assertFalse(terminal.exists())
        self.assertTrue((terminal.parent / "started.json").exists())

    def test_missing_or_tampered_excluded_warmup_fails(self):
        shutil.rmtree(self.path / "warmups")
        result = verifier.verify_campaign(self.path)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["excluded_ordinary_warmups"]["passed"])

    def test_input_source_and_duplicate_directory_tampering_fail(self):
        for relative in ("inputs/schema_input.json", "sources/src/model_client.py"):
            with self.subTest(relative=relative):
                path = self.path / relative
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                self.assertFalse(verifier.verify_campaign(self.path)["passed"])
                path.write_bytes(original)
        shutil.copytree(self.path / "trials/schema-01", self.path / "trials/duplicate")
        self.assertFalse(verifier.verify_campaign(self.path)["passed"])

    def test_derived_json_csv_and_summary_tampering_fail(self):
        for name in ("results.jsonl", "results.csv", "summary.json"):
            with self.subTest(name=name):
                path = self.path / name
                original = path.read_bytes()
                path.write_text("{}\n")
                result = verifier.verify_campaign(self.path)
                self.assertFalse(result["passed"], name)
                path.write_bytes(original)

    def test_independent_trace_rejects_old_approval_unbounded_turns_and_false_schema(self):
        record = runner.read_json(self.path / "trials/schema-01/result.json")
        raw = runner.read_json(self.path / record["evidence"])
        for mutation in (lambda r: r.update(reviewed_revision=0),
                         lambda r: r.update(turn_count=11),
                         lambda r: r.update(elapsed_ms=0),
                         lambda r: r["trace"][0].update(parsed={"tags": ["x", "tag", "tag"], "summary": "Invalid"})):
            broken = deepcopy(raw)
            mutation(broken)
            with self.assertRaises(ValueError):
                verifier.inspect_trace(broken)

    def test_report_arithmetic_and_recommendation_are_checked(self):
        report = Path(self.temp.name) / "reports"
        report.mkdir()
        metrics = "\n".join([
            "| Outcome | Count | Mean latency (ms) |", "|---|---:|---:|",
            "| Valid first attempt | 30 | 100.12 |", "| Valid after 1 retry | 0 | N/A |",
            "| Valid after 2+ retries | 0 | N/A |", "| Hit turn ceiling | 0 | N/A |",
            "| Ceiling | n | Accepted | Ceiling exits | Completion % | Mean latency (ms) |",
            "|---:|---:|---:|---:|---:|---:|", "| 2 | 20 | 20 | 0 | 100.00 | 100.12 |",
            "| 10 | 20 | 20 | 0 | 100.00 | 100.12 |",
            "| Metric | Value |", "|---|---:|",
            *[f"| {key} | 0 |" for key in verifier.SUPPLEMENT_KEYS],
            "| first_schema_valid_attempt_1 | 30 |",
            "| Trial | Status | Turns | Planner attempts | Schema failures | Latency ms |", "|---|---|---:|---:|---:|---:|",
            *[f"| adversarial-{n:02} | accepted | 2 | 1 | 0 | 100.12 |" for n in range(1, 6)],
        ])
        (report / "METRICS.md").write_text(metrics)
        summary = runner.read_json(self.path / "summary.json")
        manifest = runner.read_json(self.path / "manifest.json")
        choice = {**summary["deployment_choice"], "campaign_id": manifest["campaign_id"],
                  "campaign_manifest_sha256": runner.digest((self.path / "manifest.json").read_bytes()),
                  "evidence": os.path.relpath(self.path / "summary.json", report),
                  "command": "python code/agents_graph.py --input-json reports/hw02/cases/schema_input.json --max-turns 2"}
        (report / "deployment_choice.json").write_text(json.dumps(choice))
        self.assertTrue(verifier.verify_campaign(self.path, report)["passed"])
        (report / "METRICS.md").write_text(metrics.replace("| 30 |", "| 29 |"))
        self.assertFalse(verifier.verify_campaign(self.path, report)["passed"])
        (report / "METRICS.md").write_text(metrics)
        (report / "deployment_choice.json").write_text('{"max_turns": 10}')
        self.assertFalse(verifier.verify_campaign(self.path, report)["passed"])
        (report / "deployment_choice.json").write_text(json.dumps(choice))
        for corrupt in (metrics.replace("schema_failure_count | 0", "schema_failure_count | 1"),
                        metrics.replace("adversarial-01 | accepted", "adversarial-01 | turn_limit")):
            (report / "METRICS.md").write_text(corrupt)
            self.assertFalse(verifier.verify_campaign(self.path, report)["passed"])
        (report / "METRICS.md").write_text(metrics)
        missing_reason = {key: value for key, value in choice.items() if key != "reason"}
        for corrupt in (
            missing_reason, {"max_turns": 2}, {**choice, "campaign_id": "wrong-campaign"},
            {**choice, "campaign_manifest_sha256": "0" * 64},
            {**choice, "evidence": "nonexistent/summary.json"},
            {**choice, "command": "python code/agents_graph.py --max-turns 999"},
            {**choice, "command": "python code/agents_graph.py --max-turns 2 --controlled-reviewer"},
        ):
            with self.subTest(corrupt_choice=corrupt):
                (report / "deployment_choice.json").write_text(json.dumps(corrupt))
                self.assertFalse(verifier.verify_campaign(self.path, report)["passed"])
        (report / "deployment_choice.json").write_text(json.dumps(choice))
        self.assertTrue(verifier.verify_campaign(self.path, report)["passed"])

    def test_cli_failure_returns_nonzero_and_writes_scoped_output(self):
        (self.path / "results.csv").unlink()
        output = Path(self.temp.name) / "verification.json"
        with patch("builtins.print"):
            status = verifier.main(["--campaign", str(self.path), "--output", str(output)])
        self.assertEqual(status, 1)
        result = runner.read_json(output)
        self.assertFalse(result["passed"])
        self.assertEqual(result["part"], 4)
        self.assertIn("not final", result["scope"])


if __name__ == "__main__":
    unittest.main()
