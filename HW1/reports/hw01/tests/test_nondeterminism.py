import copy
import importlib.util
import json
import math
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "run_nondeterminism.py"
RAW_RESULTS_PATH = Path(__file__).parents[1] / "raw" / "nondeterminism_runs.json"
SPEC = importlib.util.spec_from_file_location("run_nondeterminism", MODULE_PATH)
run_nondeterminism = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(run_nondeterminism)


CASE = {
    "title": "Modern apartment near light rail",
    "content": "Modern apartment with covered parking and light rail access.",
    "email": "student@example.com",
}
BASE_URL = "http://localhost:11434"
TIMEOUT = 10.0


def successful_result():
    return {
        "finalized": {
            "data": {
                "tags": ["modern apartment", "covered parking", "light rail"],
                "summary": "Modern apartment offers covered parking and light rail access.",
                "issues": [],
            }
        },
        "reviewer_changed": False,
        "latency_ms": {"planner": 10, "reviewer": 20},
    }


def successful_record(attempt=1, run=1):
    return {
        "attempt": attempt,
        "run": run,
        "status": "ok",
        "started_at": "2026-08-31T00:00:00Z",
        "tags": ["modern apartment", "covered parking", "light rail"],
        "summary": "Modern apartment offers covered parking and light rail access.",
        "reviewer_changed": False,
        "latency_ms": {"planner": 10, "reviewer": 20, "total": 30},
    }


def independent_percentile(values, percent):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 2)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)


def independently_summarize(records, requested):
    successful = [record for record in records if record["status"] == "ok"]
    tag_sets = {tuple(sorted(record["tags"])) for record in successful}
    tag_counts = Counter(tag for record in successful for tag in set(record["tags"]))
    totals = [record["latency_ms"]["total"] for record in successful]
    success_count = len(successful)
    return {
        "runs_requested": requested,
        "attempts": len(records),
        "successful_runs": success_count,
        "failed_attempts": len(records) - success_count,
        "distinct_tag_sets": len(tag_sets),
        "tags_in_all_successful_runs": sorted(
            tag for tag, occurrences in tag_counts.items() if occurrences == success_count
        )
        if success_count
        else [],
        "tags_in_exactly_one_run": sorted(
            tag for tag, occurrences in tag_counts.items() if occurrences == 1
        ),
        "latency_ms": {
            "p50": independent_percentile(totals, 50),
            "p95": independent_percentile(totals, 95),
            "p99": independent_percentile(totals, 99),
        },
    }


class NondeterminismTests(unittest.TestCase):
    def write_case(self, root):
        case_path = root / "case.json"
        case_path.write_text(json.dumps(CASE))
        return case_path

    def initial_payload(self, temperatures=(0.7,), count=1):
        return run_nondeterminism.initial_payload(
            CASE,
            "fake",
            BASE_URL,
            temperatures,
            count,
            TIMEOUT,
        )

    def complete_payload(self):
        payload = self.initial_payload()
        payload["status"] = "complete"
        payload["completed_at"] = "2026-08-31T00:01:00Z"
        payload["runs"]["0.7"] = [successful_record()]
        payload["metrics"]["0.7"] = run_nondeterminism.summarize_runs(
            payload["runs"]["0.7"],
            1,
        )
        return payload

    def run_once(self, case_path, output_path, **overrides):
        arguments = {
            "case_path": case_path,
            "output_path": output_path,
            "model_name": "fake",
            "base_url": BASE_URL,
            "temperatures": [0.7],
            "count": 1,
            "timeout": TIMEOUT,
            "max_errors": 2,
            "resume": False,
        }
        arguments.update(overrides)
        return run_nondeterminism.run_experiment(**arguments)

    def test_percentile_uses_linear_interpolation(self):
        self.assertEqual(run_nondeterminism.percentile([10, 20, 30, 40], 50), 25.0)
        self.assertEqual(run_nondeterminism.percentile([], 95), None)

    def test_summarize_runs_reports_tag_frequency_and_latency(self):
        runs = [
            {
                "status": "ok",
                "tags": ["alpha beta", "shared", "first"],
                "latency_ms": {"total": 100},
            },
            {
                "status": "ok",
                "tags": ["alpha beta", "shared", "second"],
                "latency_ms": {"total": 200},
            },
            {"status": "error", "error": "model unavailable"},
        ]

        result = run_nondeterminism.summarize_runs(runs, requested=2)

        self.assertEqual(result["successful_runs"], 2)
        self.assertEqual(result["failed_attempts"], 1)
        self.assertEqual(result["distinct_tag_sets"], 2)
        self.assertEqual(result["tags_in_all_successful_runs"], ["alpha beta", "shared"])
        self.assertEqual(result["tags_in_exactly_one_run"], ["first", "second"])
        self.assertEqual(result["latency_ms"]["p50"], 150.0)

    def test_non_resume_refuses_overwrite_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"
            original = b"existing checkpoint bytes\n"
            output_path.write_bytes(original)

            with self.assertRaisesRegex(FileExistsError, "--overwrite"):
                self.run_once(case_path, output_path)

            self.assertEqual(output_path.read_bytes(), original)

    def test_explicit_overwrite_replaces_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"
            output_path.write_bytes(b"old output\n")

            with (
                mock.patch.object(run_nondeterminism.agents_demo, "create_model"),
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "run_pipeline",
                    return_value=successful_result(),
                ),
            ):
                result = self.run_once(case_path, output_path, overwrite=True)

            self.assertEqual(result["status"], "complete")
            self.assertEqual(json.loads(output_path.read_text())["status"], "complete")

    def test_one_run_checkpoints_running_state_then_completes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"
            observed = []

            def inspect_checkpoint(**_kwargs):
                observed.append(json.loads(output_path.read_text()))
                return successful_result()

            with (
                mock.patch.object(run_nondeterminism.agents_demo, "create_model"),
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "run_pipeline",
                    side_effect=inspect_checkpoint,
                ),
            ):
                result = self.run_once(case_path, output_path)

            self.assertEqual(observed[0]["status"], "running")
            self.assertEqual(observed[0]["runs"]["0.7"][0]["status"], "running")
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["metrics"]["0.7"]["successful_runs"], 1)

    def test_completed_checkpoint_is_validated_before_resume_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"
            payload = self.complete_payload()
            output_path.write_text(json.dumps(payload))

            with mock.patch.object(
                run_nondeterminism.agents_demo,
                "create_model",
            ) as create_model:
                result = self.run_once(case_path, output_path, resume=True)

            create_model.assert_not_called()
            self.assertEqual(result, payload)

    def test_completed_checkpoint_rejects_malformed_records_and_stale_metrics(self):
        invalid_payloads = {}

        too_many = self.complete_payload()
        too_many["runs"]["0.7"].append(successful_record(attempt=2, run=2))
        too_many["metrics"]["0.7"] = run_nondeterminism.summarize_runs(
            too_many["runs"]["0.7"], 1
        )
        invalid_payloads["too many successful runs"] = too_many

        non_contiguous = self.complete_payload()
        non_contiguous["runs"]["0.7"][0]["run"] = 2
        invalid_payloads["non-contiguous run number"] = non_contiguous

        bad_tags = self.complete_payload()
        bad_tags["runs"]["0.7"][0]["tags"] = ["one", "two"]
        invalid_payloads["not exactly three tags"] = bad_tags

        long_summary = self.complete_payload()
        long_summary["runs"]["0.7"][0]["summary"] = " ".join(["word"] * 26)
        invalid_payloads["summary over 25 words"] = long_summary

        stale_metrics = self.complete_payload()
        stale_metrics["metrics"]["0.7"]["successful_runs"] = 99
        invalid_payloads["stale metrics"] = stale_metrics

        for name, payload in invalid_payloads.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    run_nondeterminism.validate_completed_checkpoint(payload, [0.7], 1)

    def test_resume_rejects_stale_completed_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"
            payload = self.complete_payload()
            payload["metrics"]["0.7"]["successful_runs"] = 99
            output_path.write_text(json.dumps(payload))

            with (
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "create_model",
                ) as create_model,
                self.assertRaisesRegex(ValueError, "metrics do not match"),
            ):
                self.run_once(case_path, output_path, resume=True)

            create_model.assert_not_called()

    def test_checkpoint_identity_includes_schema_base_url_and_timeout(self):
        for field, replacement in (
            ("schema_version", 999),
            ("base_url", "http://different:11434"),
            ("timeout", 99.0),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                case_path = self.write_case(root)
                output_path = root / "runs.json"
                payload = self.complete_payload()
                payload[field] = replacement
                original = json.dumps(payload).encode()
                output_path.write_bytes(original)

                with self.assertRaisesRegex(ValueError, "configuration does not match"):
                    self.run_once(case_path, output_path, resume=True)

                self.assertEqual(output_path.read_bytes(), original)

    def test_partial_resume_preserves_success_and_error_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"
            payload = self.initial_payload(count=2)
            existing = [
                successful_record(),
                {
                    "attempt": 2,
                    "status": "error",
                    "started_at": "2026-08-31T00:00:30Z",
                    "elapsed_ms": 8,
                    "error": "RuntimeError: temporary failure",
                },
            ]
            payload["runs"]["0.7"] = copy.deepcopy(existing)
            payload["metrics"]["0.7"] = run_nondeterminism.summarize_runs(existing, 2)
            output_path.write_text(json.dumps(payload))

            with (
                mock.patch.object(run_nondeterminism.agents_demo, "create_model"),
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "run_pipeline",
                    return_value=successful_result(),
                ),
            ):
                result = self.run_once(
                    case_path,
                    output_path,
                    count=2,
                    resume=True,
                )

            self.assertEqual(result["runs"]["0.7"][:2], existing)
            self.assertEqual(result["runs"]["0.7"][2]["attempt"], 3)
            self.assertEqual(result["runs"]["0.7"][2]["run"], 2)
            self.assertEqual(result["metrics"]["0.7"]["failed_attempts"], 1)

    def test_error_then_success_has_correct_attempt_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"

            with (
                mock.patch.object(run_nondeterminism.agents_demo, "create_model"),
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "run_pipeline",
                    side_effect=[RuntimeError("temporary"), successful_result()],
                ),
            ):
                result = self.run_once(case_path, output_path)

            records = result["runs"]["0.7"]
            self.assertEqual([record["attempt"] for record in records], [1, 2])
            self.assertEqual([record["status"] for record in records], ["error", "ok"])
            self.assertEqual(records[1]["run"], 1)
            self.assertEqual(result["metrics"]["0.7"]["attempts"], 2)
            self.assertEqual(result["metrics"]["0.7"]["failed_attempts"], 1)

    def test_max_errors_writes_a_terminal_failed_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"

            with (
                mock.patch.object(run_nondeterminism.agents_demo, "create_model"),
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "run_pipeline",
                    side_effect=[RuntimeError("first"), RuntimeError("second")],
                ),
                self.assertRaisesRegex(RuntimeError, "reached 2 failed attempts"),
            ):
                self.run_once(case_path, output_path, max_errors=2)

            checkpoint = json.loads(output_path.read_text())
            self.assertEqual(checkpoint["status"], "failed")
            self.assertIsNotNone(checkpoint["completed_at"])
            self.assertEqual(checkpoint["metrics"]["0.7"]["failed_attempts"], 2)

    def test_keyboard_interrupt_is_checkpointed_and_reraised(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"

            with (
                mock.patch.object(run_nondeterminism.agents_demo, "create_model"),
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "run_pipeline",
                    side_effect=KeyboardInterrupt,
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                self.run_once(case_path, output_path)

            checkpoint = json.loads(output_path.read_text())
            record = checkpoint["runs"]["0.7"][0]
            self.assertEqual(checkpoint["status"], "interrupted")
            self.assertEqual(record["attempt"], 1)
            self.assertEqual(record["status"], "interrupted")
            self.assertEqual(checkpoint["metrics"]["0.7"]["failed_attempts"], 1)

    def test_resume_converts_stale_running_record_without_reusing_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"
            payload = self.initial_payload()
            payload["runs"]["0.7"] = [
                {
                    "attempt": 1,
                    "status": "running",
                    "started_at": "2026-08-31T00:00:00Z",
                }
            ]
            payload["metrics"]["0.7"] = run_nondeterminism.summarize_runs(
                payload["runs"]["0.7"], 1
            )
            output_path.write_text(json.dumps(payload))

            with (
                mock.patch.object(run_nondeterminism.agents_demo, "create_model"),
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "run_pipeline",
                    return_value=successful_result(),
                ),
            ):
                result = self.run_once(case_path, output_path, resume=True)

            records = result["runs"]["0.7"]
            self.assertEqual([record["attempt"] for record in records], [1, 2])
            self.assertEqual([record["status"] for record in records], ["interrupted", "ok"])
            self.assertEqual(result["metrics"]["0.7"]["failed_attempts"], 1)

    def test_models_are_created_in_temperature_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_path = self.write_case(root)
            output_path = root / "runs.json"

            with (
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "create_model",
                    side_effect=lambda _model, _url, temperature, _timeout: temperature,
                ) as create_model,
                mock.patch.object(
                    run_nondeterminism.agents_demo,
                    "run_pipeline",
                    return_value=successful_result(),
                ),
            ):
                self.run_once(
                    case_path,
                    output_path,
                    temperatures=[0.7, 0.0],
                )

            self.assertEqual([call.args[2] for call in create_model.call_args_list], [0.7, 0.0])

    def test_checked_in_raw_experiment_integrity(self):
        original_bytes = RAW_RESULTS_PATH.read_bytes()
        payload = json.loads(original_bytes)

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["model"], "qwen3:1.7b")
        self.assertEqual(payload["base_url"], "http://localhost:11434")
        self.assertEqual(payload["timeout"], 120.0)
        self.assertEqual(payload["temperature_order"], [0.7, 0.0])
        self.assertEqual(payload["runs_per_temperature"], 20)
        self.assertEqual(set(payload["runs"]), {"0.7", "0.0"})
        self.assertEqual(
            payload["input"],
            {
                "title": "Modern Two-Bedroom Apartment Near Downtown San Jose",
                "content": (
                    "Bright two-bedroom apartment with in-unit laundry, covered parking, "
                    "pet-friendly policies, and convenient light rail access near downtown "
                    "San Jose."
                ),
                "email": "student@example.com",
            },
        )

        expected_errors = {"0.7": 2, "0.0": 0}
        for temperature in payload["temperature_order"]:
            key = str(temperature)
            records = payload["runs"][key]
            successful = [record for record in records if record["status"] == "ok"]
            errors = [record for record in records if record["status"] == "error"]
            self.assertEqual(
                [record["attempt"] for record in records],
                list(range(1, len(records) + 1)),
            )
            self.assertEqual([record["run"] for record in successful], list(range(1, 21)))
            self.assertEqual(len(successful), 20)
            self.assertEqual(len(errors), expected_errors[key])
            for record in successful:
                self.assertEqual(len(record["tags"]), 3)
                self.assertLessEqual(len(record["summary"].split()), 25)
            self.assertEqual(payload["metrics"][key], independently_summarize(records, 20))

        self.assertEqual(
            [
                record["attempt"]
                for record in payload["runs"]["0.7"]
                if record["status"] == "error"
            ],
            [2, 17],
        )
        self.assertEqual(RAW_RESULTS_PATH.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
