"""Offline contract proofs for the native-call rental agent; no live model."""

import io
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.model_client import CompletionResult, TokenUsage
from src.tool_agent import AgentLogError, AgentResult, run_agent
from src.tool_agent import loop
from src.rental_tools.executor import execute_tool, SAFETY_BLOCK_ERROR
from src.rental_tools.registry import TOOL_REGISTRY
from src.rental_tools.service import RentalService
from scripts.hw05.part4.fixture import FixtureReader, PRIVATE_SENTINEL


def response(content="", calls=None, invalid=None):
    raw = SimpleNamespace(content=content, tool_calls=calls or [], invalid_tool_calls=invalid or [])
    return CompletionResult(content, TokenUsage(1, 1, 2), raw)


def call(name="count_rentals", args=None, id="call-1"):
    return {"name": name, "args": {"manager_id": 1} if args is None else args, "id": id, "type": "tool_call"}


class MockModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, messages, tools=None):
        self.requests.append((list(messages), tools))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def run(model, **kwargs):
    stream = io.StringIO()
    result = run_agent("Count rentals for manager 1.", model=model, log_stream=stream,
                       code_revision="offline-test", **kwargs)
    return result, [json.loads(line) for line in stream.getvalue().splitlines()]


def test_explicit_normal_completion_matches_terminal_log():
    result, events = run(MockModel([response("There are two rentals.")]))
    assert (result.answer, result.steps, result.tool_calls, result.stop_reason) == (
        "There are two rentals.", 1, 0, "completed")
    terminals = [e for e in events if e["event"] == "terminal"]
    assert len(terminals) == 1
    assert {key: terminals[0][key] for key in ("run_id", "answer", "steps", "tool_calls", "stop_reason")} == vars(result)


def test_budget_stops_before_extra_request_and_never_answers_with_tool_result():
    model = MockModel([response(calls=[call(id=f"call-{n}")]) for n in range(3)])
    invoked = []
    def executor(name, inputs):
        invoked.append((name, inputs))
        return '{"ok":true,"data":{"count":2},"error":null}'
    result, events = run(model, executor=executor, max_steps=3)
    assert (result.answer, result.steps, result.tool_calls, result.stop_reason) == (None, 3, 3, "max_steps")
    assert len(model.requests) == len(invoked) == 3
    assert len([e for e in events if e["event"] == "terminal"]) == 1


def test_native_assistant_object_and_call_id_are_preserved():
    first = response(calls=[call(id="actual-id")])
    model = MockModel([first, response("Two rentals.")])
    result, _ = run(model, executor=lambda *args: '{"ok":true,"data":{"count":2},"error":null}')
    history = model.requests[1][0]
    assert history[2] is first.raw_response
    assert history[3]["role"] == "tool"
    assert history[3]["tool_call_id"] == "actual-id"
    assert result.stop_reason == "completed"


@pytest.mark.parametrize("max_steps", [True, False, 0, -1, 1.0, "3", None, float("inf")])
def test_step_budget_is_strict_positive_integer(max_steps):
    with pytest.raises(ValueError, match="max_steps"):
        run(MockModel([]), max_steps=max_steps)


def test_advertised_tools_match_shared_registry_and_strict_flag():
    model = MockModel([response("Done.")])
    run(model)
    definitions = model.requests[0][1]
    assert [item["function"]["name"] for item in definitions] == list(TOOL_REGISTRY)
    for item in definitions:
        actual = item["function"]
        definition = TOOL_REGISTRY[actual["name"]]
        assert actual["parameters"] == definition.input_model.model_json_schema()
        assert actual["description"] == definition.description
    flag = definitions[1]["function"]["parameters"]["properties"]["include_contact"]
    assert flag["type"] == "boolean" and flag["default"] is False


@pytest.mark.parametrize("flag", ["true", 1, None, 0, "false"])
def test_invalid_contact_flags_are_executor_errors_and_not_safety_blocks(flag):
    reader = FixtureReader()
    model = MockModel([response(calls=[call("get_rental", {"rental_id": 1, "include_contact": flag})]),
                       response("The request had invalid arguments.")])
    result, events = run(model, executor=lambda name, args: execute_tool(name, args, service=RentalService(reader)))
    assert result.stop_reason == "completed" and result.steps == 2 and result.tool_calls == 1
    assert reader.calls == []
    failure = next(e["result"] for e in events if e["event"] == "tool_result")
    assert failure["ok"] is False and failure["error"].startswith("Invalid input:")


def test_safety_short_circuit_preserves_order_and_stops_later_calls():
    reader = FixtureReader()
    closes = []
    reader.close = lambda: closes.append(True)
    service = RentalService(reader)
    requested = [call("count_rentals", {"manager_id": 1}, "first"),
                 call("get_rental", {"rental_id": 1, "include_contact": True}, "private"),
                 call("search_rentals", {"query": "garden"}, "never")]
    model = MockModel([response(calls=requested)])
    invoked = []
    def executor(name, args):
        invoked.append(name)
        return execute_tool(name, args, service=service)
    result, events = run(model, executor=executor)
    assert vars(result) == {"run_id": result.run_id, "answer": None, "steps": 1,
                            "tool_calls": 2, "stop_reason": "safety_block"}
    assert invoked == ["count_rentals", "get_rental"]
    assert reader.calls == [("count", 1)] and closes == []
    results = [e for e in events if e["event"] == "tool_result"]
    assert results[-1]["result"] == {"ok": False, "data": None, "error": SAFETY_BLOCK_ERROR}
    assert PRIVATE_SENTINEL not in json.dumps(events)


def test_unknown_name_flows_through_default_production_executor(monkeypatch):
    invoked = []
    def recording(name, inputs):
        invoked.append(name)
        return execute_tool(name, inputs)
    monkeypatch.setattr(loop, "execute_tool", recording)
    result, events = run(MockModel([response(calls=[call("not_a_tool", {})]),
                                    response("That tool is unavailable.")]))
    assert invoked == ["not_a_tool"]
    assert result.tool_calls == 1 and result.steps == 2 and result.stop_reason == "completed"
    assert next(e["result"]["error"] for e in events if e["event"] == "tool_result") == "Unknown rental tool."


def test_tool_domain_error_is_available_to_next_model_turn():
    reader = FixtureReader()
    model = MockModel([response(calls=[call("get_rental", {"rental_id": 8})]), response("Rental 8 was not found.")])
    result, _ = run(model, executor=lambda name, args: execute_tool(name, args, service=RentalService(reader)))
    assert result.stop_reason == "completed" and result.steps == 2
    assert json.loads(model.requests[1][0][-1]["content"])["error"] == "Rental 8 was not found."


def test_multiple_calls_count_each_executor_invocation_in_order():
    requests = [call(id="one"), call(id="two"), call(id="three")]
    model = MockModel([response(calls=requests), response("Finished all three lookups.")])
    invoked = []
    def executor(name, args):
        invoked.append((name, args))
        return '{"ok":true,"data":{"count":2},"error":null}'
    result, events = run(model, executor=executor)
    assert result.steps == 2 and result.tool_calls == 3 and len(invoked) == 3
    assert [e["call_id"] for e in events if e["event"] == "tool_result"] == ["one", "two", "three"]
    assert [message["tool_call_id"] for message in model.requests[1][0][-3:]] == ["one", "two", "three"]


@pytest.mark.parametrize("bad_response,category", [
    (response(), "empty_response"),
    (response(content=[]), "invalid_content"),
    (response(calls=[{"name": "get_rental", "args": {}, "id": None}]), "invalid_native_calls"),
    (response(calls=[{"name": "get_rental", "args": "{}", "id": "a"}]), "invalid_native_calls"),
    (response(calls=[{**call(), "unexpected": True}]), "invalid_native_calls"),
    (response(calls=[call(), call()]), "duplicate_call_id"),
    (response(calls=[call(id=str(n)) for n in range(4)]), "batch_limit"),
    (response(invalid=[{"name": "get_rental", "args": "{", "id": "broken", "error": "dependency-secret"}]), "invalid_native_calls"),
])
def test_malformed_batch_consumes_one_step_and_executes_nothing(bad_response, category):
    model = MockModel([bad_response] * 5)
    result, events = run(model, executor=lambda *args: pytest.fail("Rejected batch must not execute"))
    assert (result.answer, result.steps, result.tool_calls, result.stop_reason) == (None, 1, 0, "malformed_response")
    assert len(model.requests) == 1
    assert next(e["error"] for e in events if e["event"] == "response_error") == category
    assert "dependency-secret" not in json.dumps(events)


def test_plain_text_is_never_guessed_to_be_a_tool_request():
    text = '{"name":"get_rental","args":{"rental_id":1}}'
    result, _ = run(MockModel([response(text)]), executor=lambda *args: pytest.fail("No native call"))
    assert result.answer == text and result.tool_calls == 0


@pytest.mark.parametrize("returned_first", [False, True])
def test_failed_model_attempt_does_not_count_as_returned_response(returned_first):
    responses = ([response(calls=[call()])] if returned_first else []) + [RuntimeError("dependency-secret")]
    result, events = run(MockModel(responses), executor=lambda *args: '{"ok":true,"data":{},"error":null}')
    assert result.stop_reason == "model_error" and result.answer is None
    assert result.steps == result.tool_calls == int(returned_first)
    failed = next(e for e in events if e["event"] == "model_error")
    assert failed["attempt"] == 1 + int(returned_first) and failed["steps"] == int(returned_first)
    assert "dependency-secret" not in json.dumps(events)


@pytest.mark.parametrize("output", [None, "not-json", '{"ok":true,"data":[],"error":null}',
                                    '{"ok":true,"data":{"x":NaN},"error":null}',
                                    '{"ok":true,"data":{"x":1e400},"error":null}'])
def test_invalid_executor_output_stops_safely(output):
    result, events = run(MockModel([response(calls=[call()])]), executor=lambda *args: output)
    assert result.stop_reason == "tool_error" and result.answer is None
    assert result.steps == result.tool_calls == 1
    assert next(e["result"]["error"] for e in events if e["event"] == "tool_result") == "Rental executor failed."


def test_executor_exception_is_sanitized():
    def broken(*args):
        raise RuntimeError("mysql://secret-user:password@host SELECT private")
    result, events = run(MockModel([response(calls=[call()])]), executor=broken)
    assert result.stop_reason == "tool_error"
    assert "password" not in json.dumps(events) and "secret-user" not in json.dumps(events)


@pytest.mark.parametrize("timeout", [True, False, 0, -1, float("nan"), float("inf"), "10", None, 10 ** 400])
def test_request_timeout_requires_positive_finite_number(timeout):
    with pytest.raises(ValueError, match="timeout"):
        run(MockModel([]), timeout=timeout)


@pytest.mark.parametrize("temperature", [True, -1, float("nan"), float("inf"), "0", 10 ** 400])
def test_temperature_requires_nonnegative_finite_number(temperature):
    with pytest.raises(ValueError, match="temperature"):
        run(MockModel([]), temperature=temperature)


@pytest.mark.parametrize("base_url", ["https://example.com", "http://10.0.0.1:11434",
    "http://127.0.0.1.example.com", "http://user:password@localhost:11434", "http://localhost:11434?key=secret"])
def test_only_loopback_ollama_endpoints_are_allowed(base_url):
    with pytest.raises(ValueError, match="loopback"):
        run(MockModel([]), base_url=base_url)


def test_live_factory_receives_finite_timeout_and_explicit_tag(monkeypatch):
    received = []
    def factory(*args, **kwargs):
        received.append((args, kwargs))
        return MockModel([response("Complete.")])
    monkeypatch.setattr(loop, "build_ollama_client", factory)
    monkeypatch.setattr(loop, "current_revision", lambda: "a" * 40)
    stream = io.StringIO()
    result = run_agent("Count.", model_name="installed:test", log_stream=stream, timeout=17)
    assert received == [(("installed:test", "http://127.0.0.1:11434", 0.0, 17), {"reasoning": False})]
    assert result.stop_reason == "completed"
    start = json.loads(stream.getvalue().splitlines()[0])
    assert start["code_revision"] == "a" * 40 and start["configuration"]["timeout_seconds"] == 17


def test_live_initialization_failure_is_logged_without_raw_exception(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("raw dependency-secret")
    monkeypatch.setattr(loop, "build_ollama_client", broken)
    result, events = run(None, model_name="installed:test")
    assert result.stop_reason == "model_error" and result.steps == result.tool_calls == 0
    assert "dependency-secret" not in json.dumps(events)


def test_jsonl_is_append_only_sequenced_utc_and_caller_stream_stays_open(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_text('{"prior":"preserved"}\n')
    first = run_agent("One.", model=MockModel([response("One.")]), log_path=path, code_revision="test")
    second = run_agent("Two.", model=MockModel([response("Two.")]), log_path=path, code_revision="test")
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert events[0] == {"prior": "preserved"} and first.run_id != second.run_id
    for run_id in [first.run_id, second.run_id]:
        rows = [e for e in events[1:] if e["run_id"] == run_id]
        assert [e["sequence"] for e in rows] == list(range(1, len(rows) + 1))
        assert all(e["timestamp_utc"].endswith("+00:00") for e in rows)
        assert len([e for e in rows if e["event"] == "terminal"]) == 1
    stream = io.StringIO()
    run_agent("Hello.", model=MockModel([response("Hello.")]), log_stream=stream, code_revision="test")
    assert not stream.closed


@pytest.mark.parametrize("failure_at", [1, 2, 4])
def test_required_logging_failure_never_returns_success(failure_at):
    class BrokenLog(io.StringIO):
        writes = 0
        def write(self, line):
            self.writes += 1
            if self.writes == failure_at:
                raise OSError("dependency-secret")
            return super().write(line)
    stream = BrokenLog()
    model = MockModel([response("Answer.")])
    with pytest.raises(AgentLogError, match="could not be written") as caught:
        run_agent("Hello.", model=model, log_stream=stream, code_revision="test")
    assert "dependency-secret" not in str(caught.value)
    assert len(model.requests) == (0 if failure_at <= 2 else 1)


def test_log_open_failure_is_clean_and_precedes_model_request(tmp_path):
    model = MockModel([])
    with pytest.raises(AgentLogError, match="could not be opened"):
        run_agent("Hello.", model=model, log_path=tmp_path, code_revision="test")
    assert model.requests == []


def test_import_and_mock_run_need_no_live_packages_network_or_configuration():
    code = '''
import builtins, io, socket, sys
from types import SimpleNamespace
original_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(("langchain", "ollama", "pymysql", "src.rental_tools.runtime")):
        raise AssertionError("live import")
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded
def no_network(*args, **kwargs):
    raise AssertionError("network")
class GuardedSocket(socket.socket):
    connect = no_network
    connect_ex = no_network
socket.socket = GuardedSocket
socket.create_connection = no_network
from src.tool_agent import run_agent
class MockModel:
    def complete(self, messages, tools=None):
        return SimpleNamespace(content="Offline.", raw_response=SimpleNamespace(tool_calls=[], invalid_tool_calls=[]))
result = run_agent("Hello.", model=MockModel(), log_stream=io.StringIO(), code_revision="offline")
assert result.answer == "Offline."
print("offline lazy import passed")
'''
    environment = {key: value for key, value in os.environ.items()
                   if not any(part in key for part in ("DATABASE", "OLLAMA", "API_KEY", "HW5_"))}
    completed = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=environment,
                               capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "offline lazy import passed"


def cli_module():
    spec = importlib.util.spec_from_file_location("hw05_agent_cli", ROOT / "scripts/hw05/run_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("reason", ["max_steps", "safety_block", "model_error", "malformed_response", "tool_error"])
def test_cli_nonanswer_stop_displays_counters_and_explanation(monkeypatch, capsys, reason):
    cli = cli_module()
    monkeypatch.setattr(cli, "run_agent", lambda *args, **kwargs: AgentResult("run-test", None, 2, 1, reason))
    assert cli.main(["Count.", "--model", "installed:test"]) == 1
    output = capsys.readouterr().out
    assert f"stop_reason={reason} steps=2 tool_calls=1" in output
    assert cli.EXPLANATIONS[reason] in output and '"ok"' not in output and "None" not in output


def test_cli_normal_completion_prints_model_answer(monkeypatch, capsys):
    cli = cli_module()
    monkeypatch.setattr(cli, "run_agent", lambda *args, **kwargs: AgentResult("run-test", "Two rentals.", 2, 1, "completed"))
    assert cli.main(["Count.", "--model", "installed:test"]) == 0
    assert capsys.readouterr().out.endswith("Two rentals.\n")


def test_cli_bad_configuration_has_clean_nonzero_result(capsys):
    cli = cli_module()
    assert cli.main(["Count.", "--model", "installed:test", "--max-steps", "0"]) == 2
    captured = capsys.readouterr()
    assert "max_steps" in captured.err and "Traceback" not in captured.err and not captured.out
