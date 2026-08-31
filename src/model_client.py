"""Stable model adapter with per-turn and cumulative token accounting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class TokenUsage:
    """Token counts reported for one model response."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


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

    input_tokens = _integer(
        usage.get("input_tokens", metadata.get("prompt_eval_count", 0))
    )
    output_tokens = _integer(
        usage.get("output_tokens", metadata.get("eval_count", 0))
    )
    total_tokens = _integer(usage.get("total_tokens", 0))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens

    return TokenUsage(input_tokens, output_tokens, total_tokens)


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
        response = target.invoke(list(messages))
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
) -> OllamaModelClient:
    """Create the LangChain Ollama implementation behind the stable adapter."""

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
        "num_ctx": 4096,
        "sync_client_kwargs": {"timeout": timeout},
        "async_client_kwargs": {"timeout": timeout},
    }
    if response_format is not None:
        kwargs["format"] = response_format
    if reasoning is not None:
        kwargs["reasoning"] = reasoning

    return OllamaModelClient(ChatOllama(**kwargs))
