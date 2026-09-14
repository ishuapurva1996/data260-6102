"""Exercise the real compiled graph behind the CLI with a scripted adapter."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPO_ROOT / "code" / "agents_graph.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
spec = importlib.util.spec_from_file_location("part3_cli_under_test", CLI_PATH)
cli = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cli)
verifier_spec = importlib.util.spec_from_file_location(
    "part3_verifier_under_test", REPO_ROOT / "scripts" / "verify_part3.py"
)
verifier = importlib.util.module_from_spec(verifier_spec)
assert verifier_spec.loader is not None
verifier_spec.loader.exec_module(verifier)

from src.model_client import CompletionResult, TokenUsage


PROPOSAL = {"tags": ["apartment", "parking", "transit"], "summary": "A bright apartment with covered parking near light rail."}
DIRECT = ["--title", "Sunny apartment", "--content", "Bright apartment with covered parking near light rail."]


class ScriptedAdapter:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("Unexpected extra model call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        raw = response if isinstance(response, str) else json.dumps(response)
        return CompletionResult(raw, TokenUsage(11, 7, 18), None)


class CLITests(unittest.TestCase):
    def invoke(self, adapter, extra=(), argv=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli, "build_ollama_client", return_value=adapter) as factory:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = cli.main(list(argv) if argv is not None else DIRECT + list(extra))
        return exit_code, json.loads(stdout.getvalue()), stdout.getvalue(), stderr.getvalue(), factory

    def test_one_actual_stream_and_machine_readable_output(self):
        adapter = ScriptedAdapter(PROPOSAL, {"issues": []})
        graph = cli.build_graph()
        observed_graph = Mock()
        observed_graph.stream.side_effect = graph.stream
        observed_graph.invoke.side_effect = AssertionError("Do not rerun after streaming")
        with patch.object(cli, "build_graph", return_value=observed_graph):
            code, result, stdout, stderr, factory = self.invoke(adapter)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["final_output"], PROPOSAL)
        self.assertEqual(result["turn_count"], 2)
        self.assertEqual(result["worker_attempts"], 2)
        self.assertEqual(result["adapter_response_count"], 2)
        self.assertEqual(result["input_tokens"], 22)
        self.assertEqual(result["output_tokens"], 14)
        self.assertEqual(result["total_tokens"], 36)
        self.assertEqual(len(adapter.calls), 2)
        observed_graph.stream.assert_called_once()
        observed_graph.invoke.assert_not_called()
        self.assertEqual(observed_graph.stream.call_args.kwargs["stream_mode"], ["updates", "values"])
        self.assertIn("supervisor", stderr)
        self.assertIn("planner attempt=1", stderr)
        self.assertIn("reviewer attempt=2", stderr)
        self.assertNotIn("ScriptedAdapter", stdout)
        self.assertNotIn('"llm"', stdout)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.kwargs, {"response_format": "json", "reasoning": False})
        self.assertEqual(result["proposal_revision"], result["reviewed_revision"])
        self.assertIn("started_at", result)
        self.assertIn("finished_at", result)
        self.assertGreaterEqual(result["elapsed_ms"], 0)
        self.assertIn("commit", result["git"])
        self.assertIn("dirty", result["git"])

    def test_ceiling_has_no_publishable_output(self):
        adapter = ScriptedAdapter(PROPOSAL)
        code, result, *_ = self.invoke(adapter, ["--max-turns", "1"])
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "turn_limit")
        self.assertIsNone(result["final_output"])
        self.assertEqual(result["proposal"], PROPOSAL)
        self.assertEqual(result["turn_count"], 1)

    def test_controlled_run_is_labeled_and_ends_unsuccessfully(self):
        adapter = ScriptedAdapter(PROPOSAL, {"issues": []}, PROPOSAL, {"issues": []})
        code, result, *_ = self.invoke(adapter, ["--max-turns", "4", "--controlled-reviewer"])
        self.assertEqual(code, 1)
        self.assertEqual(result["turn_count"], 4)
        self.assertTrue(result["config"]["controlled_reviewer"])
        self.assertTrue(result["controlled_reviewer"])
        self.assertIsNone(result["final_output"])
        self.assertTrue(result["review"]["issues"])
        self.assertEqual([entry["worker"] for entry in result["trace"]], ["planner", "reviewer", "planner", "reviewer"])

    def test_service_failure_is_error_not_ceiling(self):
        code, result, *_ = self.invoke(ScriptedAdapter(ConnectionError("Ollama offline")))
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["turn_count"], 1)
        self.assertEqual(result["worker_attempts"], 1)
        self.assertEqual(result["adapter_response_count"], 0)
        self.assertEqual(result["total_tokens"], 0)
        self.assertIn("Ollama offline", result["error"]["message"])

    def test_unexpected_stream_error_returns_terminal_error_without_rerun(self):
        broken = Mock()
        broken.stream.side_effect = RuntimeError("Unexpected graph failure")
        with patch.object(cli, "build_graph", return_value=broken):
            code, result, *_ = self.invoke(ScriptedAdapter())
        self.assertEqual(code, 2)
        self.assertEqual(result["error"]["kind"], "internal_error")
        self.assertIn("Unexpected graph failure", result["error"]["message"])
        broken.invoke.assert_not_called()

    def test_invalid_inputs_never_construct_model(self):
        invalid = [
            ["--title", " ", "--content", "content"],
            ["--title", "title"],
            DIRECT + ["--max-turns", "0"],
            DIRECT + ["--max-turns", "2.5"],
            DIRECT + ["--max-turns", "-1"],
            DIRECT + ["--temperature", "nan"],
            DIRECT + ["--temperature", "inf"],
            DIRECT + ["--temperature", "-1"],
            DIRECT + ["--timeout", "0"],
            DIRECT + ["--timeout", "nan"],
            DIRECT + ["--model", "  "],
            DIRECT + ["--base-url", "localhost:11434"],
            DIRECT + ["--base-url", "http://localhost:noport"],
            DIRECT + ["--input-json", "unused.json"],
        ]
        for argv in invalid:
            with self.subTest(argv=argv):
                code, result, _, stderr, factory = self.invoke(ScriptedAdapter(), argv=argv)
                self.assertEqual(code, 2)
                self.assertEqual(result["error"]["kind"], "configuration_error")
                self.assertEqual(result["turn_count"], 0)
                self.assertTrue(stderr)
                factory.assert_not_called()

    def test_json_input_and_direct_mode_preserve_same_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "listing.json"
            data = {"title": DIRECT[1], "content": DIRECT[3], "email": "student@example.com"}
            path.write_text(json.dumps(data), encoding="utf-8")
            _, direct_result, *_ = self.invoke(ScriptedAdapter(PROPOSAL, {"issues": []}), ["--email", data["email"]])
            code, file_result, *_ = self.invoke(ScriptedAdapter(PROPOSAL, {"issues": []}), argv=["--input-json", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(file_result["input"], direct_result["input"])
            self.assertEqual(file_result["final_output"], direct_result["final_output"])

    def test_bad_json_input_types_fail_before_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "listing.json"
            for data in ([], {"title": 3, "content": "hello"}, {"title": "ok", "content": "ok", "extra": 3}):
                with self.subTest(data=data):
                    path.write_text(json.dumps(data), encoding="utf-8")
                    code, _, _, _, factory = self.invoke(ScriptedAdapter(), argv=["--input-json", str(path)])
                    self.assertEqual(code, 2)
                    factory.assert_not_called()

    def test_evidence_matches_emitted_stream_and_retains_rejected_raw(self):
        rejected = '```json\n{"tags":["one","two","three"],"summary":"Text"}\n```'
        adapter = ScriptedAdapter(rejected, PROPOSAL, {"issues": []})
        with tempfile.TemporaryDirectory() as tmp:
            code, result, stdout, stderr, _ = self.invoke(adapter, ["--evidence-dir", tmp])
            self.assertEqual(code, 0)
            self.assertEqual(result["evidence"]["status"], "saved")
            self.assertTrue(result["evidence"]["captured"])
            directory = Path(result["evidence"]["directory"])
            self.assertEqual(directory.parent, Path(tmp).resolve())
            self.assertEqual((directory / "stdout.json").read_text(encoding="utf-8"), stdout)
            self.assertEqual((directory / "result.json").read_text(encoding="utf-8"), stdout)
            self.assertEqual((directory / "stderr.txt").read_text(encoding="utf-8"), stderr)
            events = json.loads((directory / "events.json").read_text(encoding="utf-8"))
            self.assertEqual(events["trace"][0]["raw"], rejected)
            self.assertEqual(events["trace"][0]["outcome"], "invalid")
            self.assertEqual(len(events["trace"]), 3)
            self.assertTrue(any(event["node"] == "supervisor" for event in events["events"]))

    def test_evidence_failure_is_explicit_and_has_failure_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "a_file"
            destination.write_text("cannot contain evidence", encoding="utf-8")
            code, result, _, stderr, _ = self.invoke(ScriptedAdapter(PROPOSAL, {"issues": []}), ["--evidence-dir", str(destination)])
            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["application_status"], "accepted")
            self.assertIsNone(result["final_output"])
            self.assertEqual(result["error"]["kind"], "evidence_error")
            self.assertFalse(result["evidence"]["captured"])
            self.assertEqual(result["evidence"]["status"], "error")
            self.assertIn("evidence capture failed", stderr)

    def test_partial_evidence_write_never_publishes_success_directory(self):
        original_write = Path.write_text

        def failing_write(path, *args, **kwargs):
            if path.name == "stdout.json":
                raise OSError("simulated full disk")
            return original_write(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Path, "write_text", failing_write):
                code, result, *_ = self.invoke(
                    ScriptedAdapter(PROPOSAL, {"issues": []}), ["--evidence-dir", tmp]
                )
            self.assertEqual(code, 2)
            self.assertEqual(result["error"]["kind"], "evidence_error")
            self.assertFalse(result["evidence"]["captured"])
            self.assertFalse(Path(result["evidence"]["directory"]).exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_verifier_accepts_real_captured_ordinary_and_controlled_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            for controlled in (False, True):
                with self.subTest(controlled=controlled):
                    responses = [PROPOSAL, {"issues": []}] * (5 if controlled else 1)
                    extra = ["--evidence-dir", tmp]
                    if controlled:
                        extra.append("--controlled-reviewer")
                    code, result, stdout, stderr, _ = self.invoke(ScriptedAdapter(*responses), extra)
                    checked = verifier.inspect_live_run(
                        {"exit_code": code, "stdout": stdout, "stderr": stderr},
                        controlled=controlled,
                    )
                    self.assertTrue(checked["passed"], checked)
                    self.assertEqual(code, 1 if controlled else 0)
                    self.assertEqual(checked["status"], "turn_limit" if controlled else "accepted")
                    self.assertEqual(checked["run_id"], result["run_id"])

    def test_verifier_rejects_malformed_acceptance_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, result, _, stderr, _ = self.invoke(
                ScriptedAdapter(PROPOSAL, {"issues": []}), ["--evidence-dir", tmp]
            )
            mutations = (
                {"review": None},
                {"review": {"issues": ["Still incorrect"]}},
                {"reviewed_revision": 0},
                {"final_output": {"tags": ["only one"], "summary": "Text"}},
                {"proposal": {"tags": ["one", "two", "three"], "summary": "Different draft"}},
            )
            for changed in mutations:
                with self.subTest(changed=changed):
                    output = json.dumps({**result, **changed})
                    checked = verifier.inspect_live_run(
                        {"exit_code": code, "stdout": output, "stderr": stderr}, controlled=False
                    )
                    self.assertFalse(checked["passed"], checked)
            malformed = verifier.inspect_live_run({"exit_code": 0, "stdout": "not JSON"}, controlled=False)
            self.assertFalse(malformed["passed"])

    def test_verifier_rejects_missing_or_tampered_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, result, stdout, stderr, _ = self.invoke(
                ScriptedAdapter(PROPOSAL, {"issues": []}), ["--evidence-dir", tmp]
            )
            run = {"exit_code": code, "stdout": stdout, "stderr": stderr}
            events_path = Path(result["evidence"]["directory"]) / "events.json"
            events = json.loads(events_path.read_text(encoding="utf-8"))
            events["trace"][1]["attempt"] = 3
            events_path.write_text(json.dumps(events), encoding="utf-8")
            self.assertFalse(verifier.inspect_live_run(run, controlled=False)["passed"])
            events_path.unlink()
            self.assertFalse(verifier.inspect_live_run(run, controlled=False)["passed"])

    def test_hw1_environment_overrides_are_resolved(self):
        with patch.dict(os.environ, {"SMOL_MODEL": "custom-model", "OLLAMA_URL": "http://localhost:22334"}):
            args = cli.parse_args(DIRECT)
        self.assertEqual(args.model, "custom-model")
        self.assertEqual(args.base_url, "http://localhost:22334")

    def test_entry_point_resolves_imports_from_another_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run([sys.executable, str(CLI_PATH), "--help"], cwd=tmp, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--controlled-reviewer", completed.stdout)
        self.assertIn("--max-turns", completed.stdout)


if __name__ == "__main__":
    unittest.main()
