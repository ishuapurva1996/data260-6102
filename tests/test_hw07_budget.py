"""The task ledger gates model and tool work before either can be called."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from src.model_client import TokenUsage
from src.tool_agent.budget import Budget

MESSAGES = [{"role": "user", "content": "Find a rental in San Jose."}]
TOOLS = [{"type": "function", "function": {"name": "search", "parameters": {}}}]


def test_reservation_blocks_total_and_context_limits_before_a_model_call():
    probe = Budget(max_tokens=10_000, context_window=8_000, output_limit=128)
    before = probe.snapshot()
    reservation = probe.reserve(MESSAGES, TOOLS)
    assert reservation is not None
    assert probe.snapshot() == before
    assert reservation["output_tokens"] == 128
    assert reservation["total_tokens"] == reservation["input_tokens"] + 128
    json.dumps(reservation, allow_nan=False)

    sent = []
    for ledger in (
        Budget(max_tokens=reservation["total_tokens"] - 1, output_limit=128),
        Budget(context_window=reservation["total_tokens"] - 1, output_limit=128),
    ):
        allowed = ledger.reserve(MESSAGES, TOOLS)
        if allowed is not None:
            sent.append("model request")
        assert allowed is None
        assert ledger.charged_tokens == 0
    assert sent == []

    exact = Budget(
        max_tokens=reservation["total_tokens"],
        context_window=reservation["total_tokens"],
        output_limit=128,
    )
    assert exact.reserve(MESSAGES, TOOLS) is not None


def test_reservation_bounds_utf8_bytes_and_records_the_pinned_tokenizer():
    prompts = []

    def count(prompt):
        prompts.append(prompt)
        return 17

    ledger = Budget(token_counter=count)
    reservation = ledger.reserve([{"content": "🏠 café"}], TOOLS)
    assert reservation is not None
    assert reservation["token_counter_input_tokens"] == 17
    assert reservation["input_tokens"] >= len(prompts[0].encode("utf-8")) + 1024 + 64
    assert json.loads(prompts[0])["messages"][0]["content"] == "🏠 café"


def test_tokenizer_estimate_cannot_lower_the_conservative_allowance():
    ledger = Budget(token_counter=lambda _: 9_000)
    assert ledger.reserve(MESSAGES, TOOLS) is None


def test_reported_usage_charges_actual_counts_and_leaves_room_for_the_next_call():
    ledger = Budget()
    reservation = ledger.reserve(MESSAGES, TOOLS)
    assert ledger.account(TokenUsage(120, 24, 144), reservation)
    snapshot = ledger.snapshot()
    assert snapshot["charged_tokens"] == 144
    assert snapshot["reported_input_tokens"] == 120
    assert snapshot["reported_output_tokens"] == 24
    assert snapshot["total_tokens"] == 144
    assert snapshot["unknown_usage_calls"] == 0
    assert ledger.reserve(MESSAGES, TOOLS) is not None


@pytest.mark.parametrize(
    "usage",
    [
        None,
        TokenUsage(0, 0, 0, reported=False),
        TokenUsage(1, 1, 3),
        TokenUsage(True, 1, 2),
        TokenUsage(-1, 1, 0),
        SimpleNamespace(reported=True, input_tokens=1, output_tokens="1", total_tokens=2),
    ],
)
def test_unknown_or_malformed_usage_consumes_the_reservation(usage):
    ledger = Budget()
    reservation = ledger.reserve(MESSAGES, TOOLS)
    assert ledger.account(usage, reservation)
    snapshot = ledger.snapshot()
    assert snapshot["charged_tokens"] == reservation["total_tokens"]
    assert snapshot["unknown_usage_calls"] == 1
    assert snapshot["total_tokens"] is None
    assert snapshot["reported_input_tokens"] == 0
    assert snapshot["reported_output_tokens"] == 0
    assert ledger.account(TokenUsage(2, 3, 5), ledger.reserve(MESSAGES, TOOLS))
    assert ledger.snapshot()["total_tokens"] is None


def test_retries_share_one_ledger_and_cannot_reset_the_tool_or_token_ceiling():
    probe = Budget(output_limit=128)
    reserved = probe.reserve(MESSAGES, TOOLS)["total_tokens"]
    ledger = Budget(max_tokens=reserved * 3, max_tools=24, output_limit=128)
    calls = []
    for _attempt in range(3):
        reservation = ledger.reserve(MESSAGES, TOOLS)
        assert reservation is not None
        calls.append("model request")
        assert ledger.account(None, reservation)
        for _tool in range(8):
            assert ledger.use_tool()
            calls.append("tool request")
    assert ledger.reserve(MESSAGES, TOOLS) is None
    assert ledger.use_tool() is False
    assert ledger.tools == ledger.max_tools == 24
    assert ledger.charged_tokens == reserved * 3
    assert calls.count("model request") == 3
    assert calls.count("tool request") == 24


@pytest.mark.parametrize("which", ["input", "output"])
def test_backend_overruns_are_charged_honestly_and_block_later_requests(which):
    ledger = Budget()
    reservation = ledger.reserve(MESSAGES, TOOLS)
    input_tokens = reservation["input_tokens"] + (1 if which == "input" else 0)
    output_tokens = reservation["output_tokens"] + (1 if which == "output" else 0)
    observed = input_tokens + output_tokens
    assert ledger.account(TokenUsage(input_tokens, output_tokens, observed), reservation) is False
    assert ledger.charged_tokens == observed
    assert ledger.snapshot()["total_tokens"] == observed
    assert ledger.snapshot()["overrun"] is True
    assert ledger.reserve(MESSAGES, TOOLS) is None


def test_backend_overrun_of_remaining_allowance_is_not_clamped():
    reserved = Budget().reserve(MESSAGES, TOOLS)["total_tokens"]
    ledger = Budget(max_tokens=reserved, context_window=reserved)
    reservation = ledger.reserve(MESSAGES, TOOLS)
    observed_input = reservation["input_tokens"] + 1
    assert ledger.account(TokenUsage(observed_input, 512, reserved + 1), reservation) is False
    assert ledger.charged_tokens == reserved + 1
    assert ledger.reserve(MESSAGES, TOOLS) is None


def test_native_messages_are_projected_without_private_metadata_or_repr():
    class Private:
        def __repr__(self):
            raise AssertionError("private data was stringified")

    prompts = []
    native = AIMessage(
        content="Checking listings.",
        tool_calls=[{"name": "search", "args": {"city": "San Jose"}, "id": "call-1"}],
        response_metadata={"Authorization": "Bearer SECRET"},
        additional_kwargs={"private": Private()},
    )
    namespace = SimpleNamespace(
        content="Result",
        tool_calls={"private_credential": "SECRET"},
        invalid_tool_calls=[{"id": "bad", "name": "search", "args": "{", "error": Private()}],
        response_metadata=Private(),
        private_credential="SECRET",
    )
    ledger = Budget(token_counter=lambda prompt: prompts.append(prompt) or 7)
    reservation = ledger.reserve([native, namespace], TOOLS)
    assert reservation is not None
    payload = json.loads(prompts[0])
    assert all(
        set(item) == {"content", "tool_calls", "invalid_tool_calls"} for item in payload["messages"]
    )
    assert payload["messages"][0]["tool_calls"][0]["args"] == {"city": "San Jose"}
    assert "error" not in payload["messages"][1]["invalid_tool_calls"][0]
    assert "SECRET" not in prompts[0]
    assert "metadata" not in prompts[0]


@pytest.mark.parametrize("field", ["max_tokens", "max_tools", "context_window", "output_limit"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "24"])
def test_limits_are_strictly_positive_integers(field, value):
    with pytest.raises(ValueError):
        Budget(**{field: value})


def test_output_cap_must_be_smaller_than_the_context_window():
    for output in (512, 513):
        with pytest.raises(ValueError):
            Budget(context_window=512, output_limit=output)
