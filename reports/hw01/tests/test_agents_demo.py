import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).parents[3] / "code" / "agents_demo.py"
SPEC = importlib.util.spec_from_file_location("agents_demo", MODULE_PATH)
agents_demo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(agents_demo)


class FakeModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def complete(self, messages, tools=None):
        self.calls.append(messages)
        return SimpleNamespace(content=next(self.replies))


class AgentsDemoTests(unittest.TestCase):
    def setUp(self):
        self.title = "Sunny two-bedroom apartment near light rail"
        self.content = (
            "A bright two-bedroom apartment with covered parking, in-unit laundry, "
            "and convenient light rail access."
        )

    def test_extract_json_block_ignores_surrounding_text_and_fences(self):
        raw = 'Draft:\n```json\n{"message": "ready", "data": {"tags": []}}\n```\nDone.'
        parsed = json.loads(agents_demo.extract_json_block(raw))
        self.assertEqual(parsed["message"], "ready")

    def test_phrase_candidates_are_derived_from_input(self):
        candidates = agents_demo.phrase_candidates(self.title, self.content)
        source_words = set(agents_demo.tokens(f"{self.title} {self.content}"))

        self.assertGreaterEqual(len(candidates), 3)
        self.assertTrue(
            all(set(agents_demo.tokens(candidate)).issubset(source_words) for candidate in candidates)
        )

    def test_coerce_reply_enforces_exact_tags_and_summary_limit(self):
        raw = {
            "thought": "Check the requested structure.",
            "message": "Here is the proposed metadata.",
            "data": {
                "tags": ["two-bedroom apartment", "covered parking"],
                "summary": " ".join(["word"] * 40),
                "issues": "Summary was too long",
            },
        }

        result = agents_demo.coerce_reply(raw, self.title, self.content)

        self.assertEqual(len(result["data"]["tags"]), 3)
        self.assertEqual(len(set(result["data"]["tags"])), 3)
        self.assertGreaterEqual(
            sum(" " in tag for tag in result["data"]["tags"]),
            2,
        )
        self.assertLessEqual(len(result["data"]["summary"].split()), 25)
        self.assertTrue(result["data"]["summary"].endswith("."))
        self.assertEqual(result["data"]["issues"], ["Summary was too long"])

    def test_coerce_reply_keeps_only_first_sentence(self):
        raw = {
            "message": "Validated.",
            "data": {
                "tags": ["two-bedroom apartment", "covered parking", "light rail"],
                "summary": "The apartment is bright. It also has a secret second sentence!",
                "issues": [],
            },
        }

        result = agents_demo.coerce_reply(raw, self.title, self.content)

        self.assertEqual(result["data"]["summary"], "The apartment is bright.")

    def test_coerce_reply_rejects_partly_hallucinated_tag(self):
        raw = {
            "message": "Validated.",
            "data": {
                "tags": [
                    "two-bedroom apartment",
                    "covered parking rooftop-pool",
                    "light rail",
                ],
                "summary": "Bright apartment with parking and transit access.",
                "issues": [],
            },
        }

        result = agents_demo.coerce_reply(raw, self.title, self.content)

        self.assertNotIn("covered parking rooftop-pool", result["data"]["tags"])
        source = set(agents_demo.tokens(f"{self.title} {self.content}"))
        self.assertTrue(
            all(
                set(agents_demo.tokens(tag)).difference(agents_demo.STOP).issubset(source)
                for tag in result["data"]["tags"]
            )
        )

    def test_coerce_reply_replaces_an_unsupported_summary(self):
        raw = {
            "message": "Validated.",
            "data": {
                "tags": ["two-bedroom apartment", "covered parking", "light rail"],
                "summary": "Ocean views, rooftop pool, and private concierge service.",
                "issues": [],
            },
        }

        result = agents_demo.coerce_reply(raw, self.title, self.content)

        self.assertNotIn("rooftop pool", result["data"]["summary"].lower())
        self.assertIn("covered parking", result["data"]["summary"].lower())

    def test_coerce_reply_replaces_copied_schema_placeholder(self):
        raw = {
            "message": "non-empty status under 60 words",
            "data": {
                "tags": ["two-bedroom apartment", "covered parking", "light rail access"],
                "summary": "Bright apartment with parking and transit access.",
                "issues": [],
            },
        }

        result = agents_demo.coerce_reply(raw, self.title, self.content)

        self.assertEqual(
            result["message"],
            "Proposal reviewed; tags and summary are ready.",
        )

    def test_coerce_reply_discards_false_schema_issues(self):
        raw = {
            "message": "Validated.",
            "data": {
                "tags": ["two-bedroom apartment", "covered parking", "light rail access"],
                "summary": "Bright apartment with parking and transit access.",
                "issues": ["Summary exceeds 25 words", "Tags may overlap"],
            },
        }

        result = agents_demo.coerce_reply(raw, self.title, self.content)

        self.assertEqual(result["data"]["issues"], [])

    def test_pipeline_uses_two_model_calls_and_reviewer_can_change_output(self):
        planner = {
            "thought": "Identify the central amenities and location.",
            "message": "Planner proposal complete.",
            "data": {
                "tags": ["two-bedroom apartment", "covered parking", "in-unit laundry"],
                "summary": "Bright apartment with useful amenities and convenient transit access.",
                "issues": [],
            },
        }
        reviewer = {
            "thought": "Replace the less distinctive laundry tag with transit access.",
            "message": "Reviewer corrected one tag.",
            "data": {
                "tags": ["two-bedroom apartment", "covered parking", "light rail access"],
                "summary": "Bright two-bedroom apartment offers parking, laundry, and convenient light rail access.",
                "issues": [],
            },
        }
        model = FakeModel([json.dumps(planner), json.dumps(reviewer)])

        result = agents_demo.run_pipeline(
            model=model,
            title=self.title,
            content=self.content,
            email="student@example.com",
        )

        self.assertEqual(len(model.calls), 2)
        self.assertIn("in-unit laundry", model.calls[1][1][1])
        self.assertTrue(result["reviewer_changed"])
        self.assertEqual(
            result["finalized"]["data"]["tags"],
            ["two-bedroom apartment", "covered parking", "light rail access"],
        )
        self.assertEqual(len(result["package"]["agents"]["transcript"]), 2)
        self.assertEqual(result["package"]["agents"]["final"]["issues"], [])

    def test_reviewer_receives_raw_unrepaired_planner_response(self):
        long_summary = " ".join(f"word{index}" for index in range(30))
        planner = {
            "thought": "Draft the requested tags and summary.",
            "message": "Draft.",
            "data": {
                "tags": ["invented rooftop", "covered parking"],
                "summary": long_summary,
                "issues": [],
            },
        }
        reviewer = {
            "thought": "Correct the unsupported tag and long summary.",
            "message": "Corrected.",
            "data": {
                "tags": ["two-bedroom apartment", "covered parking", "light rail"],
                "summary": "Bright apartment with parking and transit access.",
                "issues": [],
            },
        }
        model = FakeModel([json.dumps(planner), json.dumps(reviewer)])

        agents_demo.run_pipeline(
            model=model,
            title=self.title,
            content=self.content,
            email="student@example.com",
        )

        reviewer_prompt = model.calls[1][1][1]
        self.assertIn("invented rooftop", reviewer_prompt)
        self.assertIn(long_summary, reviewer_prompt)

    def test_agent_rejects_non_json_or_wrong_typed_output(self):
        invalid_replies = [
            'Draft: {"thought":"x","message":"y","data":{}}',
            json.dumps(
                {
                    "thought": "x",
                    "message": "y",
                    "data": {"tags": "not a list", "summary": "z", "issues": []},
                }
            ),
        ]

        for reply in invalid_replies:
            with self.subTest(reply=reply):
                agent = agents_demo.SimpleAgent("Return JSON.", FakeModel([reply]))
                with self.assertRaisesRegex(ValueError, "Agent response"):
                    agent.respond([], "Review the input.", self.title, self.content)

    def test_finalize_refuses_unresolved_reviewer_issues(self):
        reviewer = {
            "data": {
                "tags": ["two-bedroom apartment", "covered parking", "light rail"],
                "summary": "Bright apartment with parking and transit access.",
                "issues": ["The summary may be unsupported."],
            }
        }

        with self.assertRaisesRegex(ValueError, "unresolved issues"):
            agents_demo.finalize_reply(reviewer, self.title, self.content)

    def test_pipeline_rejects_insufficient_topical_input_before_model_call(self):
        for title, content in (("", ""), ("the and", "in the of"), ("Apartment", "")):
            with self.subTest(title=title, content=content):
                model = FakeModel([])
                with self.assertRaisesRegex(ValueError, "exactly three"):
                    agents_demo.run_pipeline(
                        model=model,
                        title=title,
                        content=content,
                        email="student@example.com",
                    )
                self.assertEqual(model.calls, [])

    def test_create_model_passes_timeout_to_sync_and_async_clients(self):
        captured = {}
        fake_module = ModuleType("langchain_ollama")

        def fake_chat_ollama(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace()

        fake_module.ChatOllama = fake_chat_ollama
        with mock.patch.dict(sys.modules, {"langchain_ollama": fake_module}):
            model = agents_demo.create_model(
                "qwen3:1.7b", "http://localhost:11434", 0.0, 45.0
            )

        self.assertEqual(captured["sync_client_kwargs"], {"timeout": 45.0})
        self.assertEqual(captured["async_client_kwargs"], {"timeout": 45.0})
        self.assertTrue(hasattr(model, "complete"))

    def test_parser_timeout_defaults_to_120_and_must_be_positive(self):
        parser = agents_demo.build_parser()
        args = parser.parse_args(["--title", self.title, "--content", self.content])
        self.assertEqual(args.timeout, 120.0)

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    ["--title", self.title, "--content", self.content, "--timeout", "0"]
                )

    def test_missing_dependency_error_names_part2_requirements(self):
        with mock.patch.dict(sys.modules, {"langchain_ollama": None}):
            with self.assertRaisesRegex(RuntimeError, "requirements-part2.txt"):
                agents_demo.create_model(
                    "qwen3:1.7b",
                    "http://localhost:11434",
                    0.0,
                    120.0,
                )

    def test_main_returns_one_and_prints_setup_guidance_on_runtime_failure(self):
        stderr = io.StringIO()
        with mock.patch.object(
            agents_demo,
            "create_model",
            side_effect=RuntimeError("connection failed"),
        ):
            with contextlib.redirect_stderr(stderr):
                result = agents_demo.main(
                    ["--title", self.title, "--content", self.content, "--model", "qwen3:1.7b"]
                )

        self.assertEqual(result, 1)
        self.assertIn("Agent pipeline failed: connection failed", stderr.getvalue())
        self.assertIn("Confirm that Ollama is running", stderr.getvalue())

    def test_main_rejects_unsupported_python_before_model_creation(self):
        stderr = io.StringIO()
        with mock.patch.object(agents_demo.sys, "version_info", (3, 13, 0)):
            with mock.patch.object(agents_demo, "create_model") as create_model:
                with contextlib.redirect_stderr(stderr):
                    result = agents_demo.main(
                        ["--title", self.title, "--content", self.content]
                    )

        self.assertEqual(result, 2)
        create_model.assert_not_called()
        self.assertIn("requires Python 3.11 or 3.12", stderr.getvalue())

    def test_parse_failure_still_returns_valid_schema(self):
        result = agents_demo.parse_and_coerce(
            "I could not produce JSON, but the apartment has parking and light rail access.",
            self.title,
            self.content,
        )

        self.assertEqual(set(result), {"thought", "message", "data"})
        self.assertEqual(len(result["data"]["tags"]), 3)
        self.assertLessEqual(len(result["data"]["summary"].split()), 25)


if __name__ == "__main__":
    unittest.main()
