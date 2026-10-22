from __future__ import annotations

import json
import math
from typing import Any, Callable, Sequence

from src.model_client import TokenUsage


def _json_value(value: Any) -> Any:
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else "<non-finite number>"
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items() if isinstance(key, str)}
    return "<unsupported model value>"


def _native_calls(value: Any) -> Any:
    if not isinstance(value, (list, tuple)):
        return "<invalid native call collection>"
    # Parser error strings can contain provider details or credentials. Only the
    # native request fields belong in the prompt projection used for counting.
    return [
        {key: _json_value(call[key]) for key in ("id", "name", "args", "type") if key in call}
        if isinstance(call, dict)
        else "<unsupported native call>"
        for call in value
    ]


def _message(message: Any) -> dict[str, Any]:
    def field(name: str, default: Any) -> Any:
        if isinstance(message, dict):
            return message.get(name, default)
        return getattr(message, name, default)

    return {
        "content": _json_value(field("content", "")),
        "tool_calls": _native_calls(field("tool_calls", [])),
        "invalid_tool_calls": _native_calls(field("invalid_tool_calls", [])),
    }


class Budget:
    """A sequential ledger shared by every attempt at the same task.

    ``reserve`` is a read-only preflight. Call ``account`` once after each model
    request, including requests whose usage is unavailable. The optional pinned
    tokenizer accepts the compact JSON prompt as text and returns an integer.
    """

    def __init__(
        self,
        max_tokens: int = 24_000,
        max_tools: int = 24,
        context_window: int = 8_192,
        output_limit: int = 512,
        token_counter: Callable[[str], int] | None = None,
    ) -> None:
        for name, value in (
            ("max_tokens", max_tokens),
            ("max_tools", max_tools),
            ("context_window", context_window),
            ("output_limit", output_limit),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer, not a Boolean.")
        if output_limit >= context_window:
            raise ValueError("output_limit must be smaller than context_window.")
        self.max_tokens = max_tokens
        self.max_tools = max_tools
        self.context_window = context_window
        self.output_limit = output_limit
        self.tools = 0
        self.charged_tokens = 0
        self._token_counter = token_counter
        self._reported_input_tokens = 0
        self._reported_output_tokens = 0
        self._unknown_usage_calls = 0
        self._overrun = False

    def reserve(
        self, messages: Sequence[Any], tools: Sequence[Any] | None
    ) -> dict[str, Any] | None:
        """Return a JSON-safe allowance only when the full call can fit."""
        if self._overrun or self.charged_tokens >= self.max_tokens:
            return None
        projected = [_message(message) for message in messages]
        prompt = json.dumps(
            {"messages": projected, "tools": _json_value(tools or [])},
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        # UTF-8 bytes upper-bound the pinned tokenizer's byte-based encoding;
        # fixed and per-message allowances cover chat formatting and roles.
        input_tokens = len(prompt.encode("utf-8")) + 1024 + 64 * len(projected)
        estimate = None
        if self._token_counter is not None:
            estimate = self._token_counter(prompt)
            if type(estimate) is not int or estimate < 0:
                raise ValueError("token_counter must return a nonnegative integer.")
            input_tokens = max(input_tokens, estimate)
        total_tokens = input_tokens + self.output_limit
        if (
            total_tokens > self.context_window
            or total_tokens > self.max_tokens - self.charged_tokens
        ):
            return None
        return {
            "input_tokens": input_tokens,
            "output_tokens": self.output_limit,
            "total_tokens": total_tokens,
            "context_window": self.context_window,
            "token_counter_input_tokens": estimate,
        }

    def account(self, usage: TokenUsage | None, reservation: dict[str, Any]) -> bool:
        """Charge one response honestly; unknown usage consumes its allowance."""
        counts = tuple(
            getattr(usage, name, None) for name in ("input_tokens", "output_tokens", "total_tokens")
        )
        reported = (
            getattr(usage, "reported", False) is True
            and all(type(value) is int and value >= 0 for value in counts)
            and counts[2] == counts[0] + counts[1]
        )
        if not reported:
            self._unknown_usage_calls += 1
            charged = reservation["total_tokens"]
        else:
            input_tokens, output_tokens, charged = counts
            self._reported_input_tokens += input_tokens
            self._reported_output_tokens += output_tokens
            if (
                input_tokens > reservation["input_tokens"]
                or output_tokens > reservation["output_tokens"]
                or charged > reservation["total_tokens"]
                or charged > self.context_window
            ):
                self._overrun = True
        self.charged_tokens += charged
        if self.charged_tokens > self.max_tokens:
            self._overrun = True
        return not self._overrun

    def use_tool(self) -> bool:
        """Claim one tool execution before it runs, without resetting on retry."""
        if self.tools >= self.max_tools:
            return False
        self.tools += 1
        return True

    def snapshot(self) -> dict[str, Any]:
        """Separate conservative charges from known backend-reported usage."""
        return {
            "max_tools": self.max_tools,
            "max_tokens": self.max_tokens,
            "tools": self.tools,
            "charged_tokens": self.charged_tokens,
            "reported_input_tokens": self._reported_input_tokens,
            "reported_output_tokens": self._reported_output_tokens,
            "unknown_usage_calls": self._unknown_usage_calls,
            "total_tokens": (
                None
                if self._unknown_usage_calls
                else self._reported_input_tokens + self._reported_output_tokens
            ),
            "overrun": self._overrun,
        }
