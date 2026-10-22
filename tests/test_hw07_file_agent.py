"""Controlled responses establish discovery ordering; excluded from real-model evidence."""

import json

import pytest
from langchain_core.messages import AIMessage

from src.course_files.agent import run_file_agent
from src.course_files.sandbox import FileTools
from src.model_client import CompletionResult, TokenUsage


class Replies:
    def __init__(self, replies):
        self.replies = iter(replies)

    def complete(self, messages, tools=None):
        raw = next(self.replies)
        return CompletionResult(raw.content, TokenUsage(10, 10, 20), raw)


def call(name, arguments, identifier):
    return AIMessage(content="", tool_calls=[{"name": name, "args": arguments, "id": identifier}])


def test_discovered_path_and_contents_are_required_in_final(tmp_path):
    root = tmp_path / "course"
    root.mkdir()
    with FileTools(root) as tools:
        tools.write_file("a.py", "quiet\n")
        tools.write_file("unexpected.py", "DEBUG = True\n")
        model = Replies(
            [
                call("glob_files", {"pattern": "*.py"}, "glob-1"),
                call("search_in_files", {"query": "DEBUG", "file_pattern": "*.py"}, "search-2"),
                call("read_file", {"path": "unexpected.py"}, "read-3"),
                AIMessage(
                    content=json.dumps({"path": "unexpected.py", "content": "DEBUG = True\n"})
                ),
            ]
        )
        result = run_file_agent("Find DEBUG using discovery.", tools, model=model)
    assert result["verification"]["passed"] and result["stop_reason"] == "success"
    assert [e["name"] for e in result["trace"] if e["event"] == "tool_result"] == [
        "glob_files",
        "search_in_files",
        "read_file",
    ]
    last_request = [e for e in result["trace"] if e["event"] == "model_request"][-1]
    assert [m["tool_call_id"] for m in last_request["messages"] if m["type"] == "tool"] == [
        "glob-1",
        "search-2",
        "read-3",
    ]


def test_guessed_read_is_rejected_before_execution(tmp_path):
    root = tmp_path / "course"
    root.mkdir()
    with FileTools(root) as tools:
        result = run_file_agent(
            "Find DEBUG.", tools, model=Replies([call("read_file", {"path": "guess.py"}, "guess")])
        )
    assert result["stop_reason"] == "human_review"
    assert not result["verification"]["passed"]
    assert not any(e["event"] == "tool_result" for e in result["trace"])


def test_search_must_use_requested_debug_literal_and_python_filter(tmp_path):
    from src.course_files.agent import verify

    root = tmp_path / "course"
    root.mkdir()
    with FileTools(root) as tools:
        tools.write_file("a.py", "DEBUG = True\n")
        observations = [
            {
                "name": "glob_files",
                "inputs": {"pattern": "*.py"},
                "result": tools.glob_files("*.py"),
            },
            {
                "name": "search_in_files",
                "inputs": {"query": "True", "file_pattern": "*.py"},
                "result": tools.search_in_files("True", "*.py"),
            },
            {"name": "read_file", "inputs": {"path": "a.py"}, "result": tools.read_file("a.py")},
        ]
        answer = json.dumps({"path": "a.py", "content": "DEBUG = True\n"})
        assert not verify(answer, observations)["passed"]
        observations[1]["inputs"] = {"query": "DEBUG", "file_pattern": "*"}
        assert not verify(answer, observations)["passed"]


@pytest.mark.parametrize(
    "arguments",
    [{"query": "True", "file_pattern": "*.py"}, {"query": "DEBUG", "file_pattern": "*"}],
)
def test_wrong_search_is_rejected_before_execution(tmp_path, arguments):
    root = tmp_path / "course"
    root.mkdir()
    with FileTools(root) as tools:
        tools.write_file("a.py", "DEBUG = True\n")
        result = run_file_agent(
            "Find DEBUG.",
            tools,
            model=Replies(
                [
                    call("glob_files", {"pattern": "*.py"}, "glob"),
                    call("search_in_files", arguments, "wrong-search"),
                ]
            ),
        )
    assert result["stop_reason"] == "human_review"
    assert result["tool_calls"] == 1
    assert not result["verification"]["passed"]


def test_guessed_glob_cannot_bypass_discovery(tmp_path):
    root = tmp_path / "course"
    root.mkdir()
    with FileTools(root) as tools:
        tools.write_file("sample_b.py", "DEBUG = True\n")
        result = run_file_agent(
            "Discover Python files.",
            tools,
            model=Replies(
                [
                    call("glob_files", {"pattern": "sample_b.py"}, "guess"),
                ]
            ),
        )
    assert result["tool_calls"] == 0
    assert result["stop_reason"] == "human_review"


def test_verifier_rejects_a_guessed_glob_even_with_correct_contents(tmp_path):
    from src.course_files.agent import verify

    root = tmp_path / "course"
    root.mkdir()
    with FileTools(root) as tools:
        tools.write_file("sample_b.py", "DEBUG = True\n")
        observations = [
            {
                "name": "glob_files",
                "inputs": {"pattern": "sample_b.py"},
                "result": tools.glob_files("sample_b.py"),
            },
            {
                "name": "search_in_files",
                "inputs": {"query": "DEBUG", "file_pattern": "*.py"},
                "result": tools.search_in_files("DEBUG", "*.py"),
            },
            {
                "name": "read_file",
                "inputs": {"path": "sample_b.py"},
                "result": tools.read_file("sample_b.py"),
            },
        ]
    assert not verify(
        json.dumps({"path": "sample_b.py", "content": "DEBUG = True\n"}), observations
    )["passed"]
