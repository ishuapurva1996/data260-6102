"""Stable model adapter with per-turn and cumulative token accounting."""

from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Sequence
from uuid import uuid4

_OLLAMA_HISTORY: ContextVar[list[Any] | None] = ContextVar("ollama_history", default=None)


@dataclass(frozen=True)
class TokenUsage:
    """Token counts reported for one model response."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    reported: bool = True


@dataclass
class CumulativeUsage:
    """Token totals accumulated by one client instance."""

    turn_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class CompletionResult:
    """Normalized response returned by the adapter."""

    content: Any
    usage: TokenUsage
    raw_response: Any


def _integer(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _token_usage(response: Any) -> TokenUsage:
    usage = getattr(response, "usage_metadata", None) or {}
    metadata = getattr(response, "response_metadata", None) or {}

    input_tokens = _integer(usage.get("input_tokens", metadata.get("prompt_eval_count", 0)))
    output_tokens = _integer(usage.get("output_tokens", metadata.get("eval_count", 0)))
    total_tokens = _integer(usage.get("total_tokens", 0))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens

    reported = all(
        isinstance(usage.get(key, metadata.get(legacy)), int)
        and not isinstance(usage.get(key, metadata.get(legacy)), bool)
        and usage.get(key, metadata.get(legacy)) >= 0
        for key, legacy in (("input_tokens", "prompt_eval_count"), ("output_tokens", "eval_count"))
    )
    return TokenUsage(input_tokens, output_tokens, total_tokens, reported=reported)


class _InvalidOllamaArguments(Exception):
    """Carry a rejected provider response without exposing it in error text."""

    def __init__(self, diagnostic: Any) -> None:
        super().__init__("Ollama returned invalid tool arguments.")
        # LangChain copies exceptions' `response` attributes into error traces.
        self.diagnostic = diagnostic


def _invalid_ollama_response(parts: list[dict[str, Any]]) -> Any:
    """Keep rejected arguments before Ollama 0.6.3's typed decoder loses them."""
    from langchain_core.messages import AIMessage

    calls, invalid, content = [], [], []
    for part in parts:
        message = part.get("message", {})
        if not isinstance(message, dict):
            return None
        text = message.get("content", "")
        if isinstance(text, str):
            content.append(text)
        raw_calls = message.get("tool_calls") or []
        if not isinstance(raw_calls, list):
            return None
        for call in raw_calls:
            if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                return None
            function = call["function"]
            if not isinstance(function.get("name"), str) or "arguments" not in function:
                return None
            call_id = call.get("id") or str(uuid4())
            if not isinstance(call_id, str):
                return None
            arguments = function["arguments"]
            if isinstance(arguments, dict):
                calls.append({"id": call_id, "name": function["name"], "args": arguments})
            else:
                invalid.append(
                    {
                        "id": call_id,
                        "name": function["name"],
                        "args": arguments if isinstance(arguments, str) else json.dumps(arguments),
                        "error": "Ollama tool arguments must be a JSON object.",
                    }
                )
    if not invalid:
        return None
    # Completed NDJSON streams report usage in their last chunk. Missing counts
    # remain absent so the adapter does not claim an observed zero-token response.
    metadata = {
        key: parts[-1][key] for key in ("prompt_eval_count", "eval_count") if key in parts[-1]
    }
    return AIMessage(
        content="".join(content),
        tool_calls=calls,
        invalid_tool_calls=invalid,
        response_metadata=metadata,
    )


def _preserve_invalid_ollama_arguments(response: Any) -> None:
    """Public sync HTTPX hook, before Ollama validates provider tool arguments."""
    if not response.is_success or not response.request.url.path.endswith("/api/chat"):
        return
    # complete() is blocking and already aggregates the bounded model output.
    # Buffering also retains the final usage chunk when an earlier call is invalid.
    response.read()
    try:
        try:
            parts = [response.json()]
        except ValueError:
            parts = [json.loads(line) for line in response.iter_lines() if line.strip()]
    except ValueError:
        return  # Leave malformed envelopes to the provider's normal decoder.
    if not parts or any(not isinstance(part, dict) or part.get("error") for part in parts):
        return
    diagnostic = _invalid_ollama_response(parts)
    if diagnostic is not None:
        raise _InvalidOllamaArguments(diagnostic)


def _native_id_auth() -> Any:
    """Restore native history IDs after Ollama 0.6.3's request model drops them."""
    import httpx
    from langchain_core.messages import AIMessage, ToolMessage, convert_to_messages

    class NativeIdAuth(httpx.Auth):
        requires_request_body = True

        def auth_flow(self, request):
            history = _OLLAMA_HISTORY.get()
            if history is None or not request.url.path.endswith("/api/chat"):
                yield request
                return
            payload = json.loads(request.content)
            wire_messages = payload.get("messages", [])
            messages = convert_to_messages(history)
            if len(messages) != len(wire_messages):
                yield request
                return
            changed = False
            for message, wire in zip(messages, wire_messages):
                if isinstance(message, AIMessage) and wire.get("role") == "assistant":
                    wire_calls = wire.get("tool_calls", [])
                    if len(message.tool_calls) != len(wire_calls):
                        yield request
                        return
                    for call, wire_call in zip(message.tool_calls, wire_calls):
                        if call.get("id") and wire_call.get("id") != call["id"]:
                            wire_call["id"] = call["id"]
                            changed = True
                elif isinstance(message, ToolMessage) and wire.get("role") == "tool":
                    if message.tool_call_id and wire.get("tool_call_id") != message.tool_call_id:
                        wire["tool_call_id"] = message.tool_call_id
                        changed = True
            if changed:
                headers = request.headers.copy()
                del headers["content-length"]
                # A new public Request recalculates body framing; retain auth,
                # custom headers and timeout/trace extensions from the SDK request.
                request = httpx.Request(
                    request.method,
                    request.url,
                    headers=headers,
                    json=payload,
                    extensions=request.extensions,
                )
            yield request

    return NativeIdAuth()


class OllamaModelClient:
    """Adapter that owns every call to the underlying Ollama chat model."""

    def __init__(self, model: Any) -> None:
        self._model = model
        self.stats = CumulativeUsage()

    def complete(
        self,
        messages: Sequence[Any],
        tools: Sequence[Any] | None = None,
    ) -> CompletionResult:
        """Complete one chat turn and update cumulative token counts."""

        target = self._model.bind_tools(list(tools)) if tools else self._model
        request_messages = list(messages)
        history_token = _OLLAMA_HISTORY.set(request_messages)
        try:
            try:
                response = target.invoke(request_messages)
            except _InvalidOllamaArguments as exc:
                response = exc.diagnostic
        finally:
            _OLLAMA_HISTORY.reset(history_token)
        usage = _token_usage(response)

        self.stats.turn_count += 1
        self.stats.input_tokens += usage.input_tokens
        self.stats.output_tokens += usage.output_tokens

        return CompletionResult(
            content=getattr(response, "content", response),
            usage=usage,
            raw_response=response,
        )


def build_ollama_client(
    model_name: str,
    base_url: str,
    temperature: float,
    timeout: float,
    *,
    response_format: str | None = None,
    reasoning: bool | None = None,
    context_window: int = 4096,
    output_limit: int | None = None,
    seed: int | None = None,
) -> OllamaModelClient:
    """Create the LangChain Ollama implementation behind the stable adapter."""

    if context_window <= 0 or (output_limit is not None and not 0 < output_limit < context_window):
        raise ValueError("Context/output limits must be positive and output must fit context")
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'langchain-ollama'. Install "
            "reports/hw01/requirements-part2.txt in Python 3.11 or 3.12."
        ) from exc

    kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": temperature,
        "base_url": base_url,
        "num_ctx": context_window,
        "sync_client_kwargs": {
            "timeout": timeout,
            "auth": _native_id_auth(),
            "event_hooks": {"response": [_preserve_invalid_ollama_arguments]},
        },
        "async_client_kwargs": {"timeout": timeout},
    }
    if output_limit is not None:
        kwargs["num_predict"] = output_limit
    if seed is not None:
        kwargs["seed"] = seed
    if response_format is not None:
        kwargs["format"] = response_format
    if reasoning is not None:
        kwargs["reasoning"] = reasoning

    return OllamaModelClient(ChatOllama(**kwargs))
