"""Campaign lifecycle tests. Scripted graph results are NEVER measured evidence."""
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from code import agents_experiments as batch
from code.agents_graph import _write_evidence, parse_args, run_graph
from src.model_client import OllamaModelClient

DRAFT = {"tags":["rental","parking","transit"],"summary":"Rental near transit with parking."}
CASE = {"title":"Rental", "content":"Rental near transit with parking."}


class Transport:
    def __init__(self, responses):
        self.responses = iter(responses)

    def invoke(self, messages):
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(content=json.dumps(value), usage_metadata={}, response_metadata={})


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="part4 tests with spaces ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.campaign = self.root/"campaign with spaces"
        self.case = self.root/"input with spaces.json"
        self.case.write_text(json.dumps(CASE))
        self.adversarial = self.root/"adversarial.json"
        self.adversarial.write_text(json.dumps({**CASE,"content":"Conflicting parking notices."}))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(batch, "SOURCE_PATHS", ["src/model_client.py"]))
        self.stack.enter_context(patch.object(batch, "environment", return_value={"python":"test", "packages":{}}))
        self.model = self.stack.enter_context(patch.object(batch, "model_identity", return_value={"name":"qwen3:1.7b","digest":"test-only"}))
        self.manifest = batch.prepare_campaign(self.campaign,self.case,self.adversarial)
        self.calls = 0

    def launch(self, responses):
        def fake(args, **kwargs):
            self.calls += 1
            parsed = parse_args(args[2:])
            lines = []
            result = run_graph(parsed, llm=OllamaModelClient(Transport(responses)), emit=lambda s: lines.append(s+"\n"))
            _write_evidence(result, parsed.evidence_dir, "".join(lines))
            kwargs["stdout"].write(batch.json_bytes(result))
            kwargs["stderr"].write("".join(lines).encode())
            return SimpleNamespace(returncode={"accepted":0,"turn_limit":1,"error":2}[result["status"]])
        # Git calls are metadata reads and remain real, even while graph launch is stubbed.
        original = subprocess.run
        return patch.object(batch.subprocess, "run", side_effect=lambda args,**kw: original(args,**kw) if args[0]=="git" else fake(args,**kw))

    def test_accepted_ceiling_error_exit_codes_and_raw_capture(self):
        for index, responses, status, code in (
            (0,[DRAFT,{"issues":[]}],"accepted",0),
            (1,[{}]*10,"turn_limit",1),
            (2,[ConnectionError("offline test")],"error",2),
        ):
            slot = self.manifest["schedule"][index]
            with self.launch(responses):
                row = batch.execute_trial(self.campaign,self.manifest,slot)
            self.assertEqual((row["status"],row["returncode"]),(status,code))
            self.assertEqual(batch.read_trial(self.campaign,self.manifest,slot),row)
        self.assertEqual(self.calls,3)

    def test_resume_only_pending_slots_and_excludes_warmups(self):
        with self.launch([DRAFT,{"issues":[]}]):
            batch.run_campaign(self.campaign,limit=1)
            first = (self.campaign/"trials/schema-01/result.json").read_bytes()
            batch.run_campaign(self.campaign,limit=1)
        self.assertEqual(self.calls,4)  # two excluded warm-ups, two measured slots
        self.assertEqual((self.campaign/"trials/schema-01/result.json").read_bytes(),first)
        _, rows, summary = batch.load_campaign(self.campaign)
        self.assertEqual(len(rows),2)
        self.assertEqual(summary["pending"],73)
        self.assertFalse(summary["complete"])
        self.assertEqual(len(list((self.campaign/"warmups").iterdir())),2)

    def test_unknown_start_is_preserved_and_resume_refuses(self):
        slot = self.manifest["schedule"][0]
        batch.write_new(self.campaign/"trials/schema-01/started.json",batch.trial_base(self.manifest,slot))
        _, rows, summary = batch.load_campaign(self.campaign)
        self.assertEqual(rows[0]["status"],"unknown")
        self.assertEqual(summary["unknown"],1)
        with self.assertRaises(batch.IntegrityError), self.launch([DRAFT,{"issues":[]}]):
            batch.run_campaign(self.campaign)
        self.assertEqual(self.calls,0)

    def assert_warmup_resume_refused(self):
        before = {p.relative_to(self.campaign): p.read_bytes()
                  for p in self.campaign.rglob("*") if p.is_file()}
        calls = self.calls
        with self.assertRaisesRegex(batch.IntegrityError, "preserve.*new campaign"), self.launch([DRAFT,{"issues":[]}]):
            batch.run_campaign(self.campaign,limit=1)
        after = {p.relative_to(self.campaign): p.read_bytes()
                 for p in self.campaign.rglob("*") if p.is_file()}
        self.assertEqual(after,before)
        self.assertEqual(self.calls,calls)
        self.assertFalse((self.campaign/"runner.lock").exists())
        self.assertEqual(batch.load_campaign(self.campaign)[2]["pending"],75)

    def test_failed_warmup_is_preserved_and_resume_refuses(self):
        with self.assertRaisesRegex(batch.IntegrityError, "Excluded warm-up failed"), self.launch([ConnectionError("offline test")]):
            batch.run_campaign(self.campaign,limit=1)
        self.assertEqual(self.calls,1)
        self.assert_warmup_resume_refused()

    def test_unknown_warmup_is_preserved_and_resume_refuses(self):
        slot = dict(trial_id="warmup-interrupted",cohort="warmup",order=0,
                    max_turns=10,input_key="schema",pair=None)
        batch.write_new(self.campaign/"warmups"/slot["trial_id"]/"started.json",
                        batch.trial_base(self.manifest,slot))
        self.assertEqual(batch.read_trial(self.campaign,self.manifest,slot,folder="warmups")["status"],"unknown")
        self.assert_warmup_resume_refused()

    def test_partial_warmup_is_preserved_and_resume_refuses(self):
        directory = self.campaign/"warmups/warmup-partial"
        directory.mkdir(parents=True)
        (directory/"interrupted.txt").write_text("preserved partial evidence")
        self.assert_warmup_resume_refused()

    def test_git_timeout_starts_nothing_and_releases_campaign_lock(self):
        def stalled(args,**kwargs):
            self.assertEqual(args[0],"git", "Metadata failure must not launch a model process")
            self.assertEqual(kwargs["timeout"],5)
            raise subprocess.TimeoutExpired(args,kwargs["timeout"])
        with patch.object(batch.subprocess,"run",side_effect=stalled) as launch:
            with self.assertRaisesRegex(batch.IntegrityError,"Git metadata unavailable: TimeoutExpired"):
                batch.run_campaign(self.campaign,limit=1)
        self.assertEqual(launch.call_count,1)
        self.assertFalse((self.campaign/"warmups").exists())
        self.assertFalse((self.campaign/"trials").exists())
        self.assertFalse((self.campaign/"runner.lock").exists())
        self.assertEqual(batch.load_campaign(self.campaign)[2]["pending"],75)

    def test_git_metadata_errors_leave_measured_slot_pending(self):
        slot = self.manifest["schedule"][0]
        for failure in (OSError("Git unavailable"),subprocess.CalledProcessError(1,["git","status"])):
            with self.subTest(failure=type(failure).__name__), patch.object(batch.subprocess,"run",side_effect=failure) as launch:
                with self.assertRaisesRegex(batch.IntegrityError,"Git metadata unavailable"):
                    batch.execute_trial(self.campaign,self.manifest,slot)
                self.assertEqual(launch.call_count,1)
                self.assertEqual(launch.call_args.args[0][0],"git")
                self.assertEqual(launch.call_args.kwargs["timeout"],5)
                self.assertIsNone(batch.read_trial(self.campaign,self.manifest,slot))
                self.assertFalse((self.campaign/"trials").exists())

    def test_offline_copy_report_never_queries_model(self):
        with self.launch([DRAFT,{"issues":[]}]):
            batch.execute_trial(self.campaign,self.manifest,self.manifest["schedule"][0])
        copied = self.root/"copied campaign"
        shutil.copytree(self.campaign,copied)
        with patch.object(batch,"model_identity",side_effect=AssertionError("offline called model")), patch(
            "src.model_client.build_ollama_client",side_effect=AssertionError("offline built adapter")
        ):
            summary = batch.write_report(copied)
        self.assertEqual(summary["started"],1)
        self.assertEqual(self.calls,1)

    def test_duplicate_runner_and_existing_campaign_refused(self):
        with batch.campaign_lock(self.campaign):
            with self.assertRaises(batch.IntegrityError):
                with batch.campaign_lock(self.campaign):
                    pass
        with self.assertRaises(FileExistsError):
            batch.prepare_campaign(self.campaign,self.case,self.adversarial)

    def test_identical_adversarial_input_is_rejected(self):
        with self.assertRaises(batch.IntegrityError):
            batch.prepare_campaign(self.root/"invalid-campaign",self.case,self.case)

    def test_modified_input_source_model_and_config_rejected(self):
        input_path = self.campaign/self.manifest["inputs"]["schema"]["path"]
        original = input_path.read_bytes()
        input_path.write_text("{}")
        with self.assertRaises(batch.IntegrityError):
            batch.load_manifest(self.campaign)
        input_path.write_bytes(original)
        with patch.object(batch,"model_identity",return_value={"digest":"changed"}):
            with self.assertRaises(batch.IntegrityError):
                batch.load_manifest(self.campaign,execution=True)
        source = self.campaign/"sources/src/model_client.py"
        source.write_text("altered")
        with self.assertRaises(batch.IntegrityError):
            batch.load_manifest(self.campaign)

    def test_partial_directory_and_malformed_terminal_fail(self):
        directory = self.campaign/"trials/schema-01"
        directory.mkdir(parents=True)
        with self.assertRaises(batch.IntegrityError):
            batch.load_campaign(self.campaign)
        batch.write_new(directory/"started.json",batch.trial_base(self.manifest,self.manifest["schedule"][0]))
        (directory/"result.json").write_text("{broken")
        with self.assertRaises(batch.IntegrityError):
            batch.load_campaign(self.campaign)

    def test_outer_deadline_preserves_interruption_and_never_calls_it_ceiling(self):
        original = subprocess.run
        def failed(args,**kwargs):
            if args[0]=="git":
                return original(args,**kwargs)
            self.assertGreaterEqual(kwargs["timeout"],10*120+90)
            raise subprocess.TimeoutExpired(args,kwargs["timeout"])
        with patch.object(batch.subprocess,"run",side_effect=failed):
            row = batch.execute_trial(self.campaign,self.manifest,self.manifest["schedule"][0])
        self.assertEqual(row["status"],"error")
        self.assertIsNone(row["returncode"])
        self.assertIn("TimeoutExpired",row["operational_error"])
        self.assertTrue((self.campaign/"trials/schema-01/stderr.txt").exists())

    def test_tampered_stdout_fails_hash_check(self):
        with self.launch([DRAFT,{"issues":[]}]):
            batch.execute_trial(self.campaign,self.manifest,self.manifest["schedule"][0])
        (self.campaign/"trials/schema-01/stdout.json").write_text("{}")
        with self.assertRaises(batch.IntegrityError):
            batch.load_campaign(self.campaign)


if __name__ == "__main__":
    unittest.main()
