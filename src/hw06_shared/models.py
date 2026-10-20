"""Local generation, embedding and token counting behind injectable interfaces."""
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path

import httpx

from src.model_client import CompletionResult, build_ollama_client
from .config import HW6Config


@dataclass(frozen=True)
class UsageCounts:
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    usage_source: str


def usage_counts(result: CompletionResult) -> UsageCounts:
    if not result.usage.reported:
        return UsageCounts(None, None, None, "missing")
    return UsageCounts(result.usage.input_tokens, result.usage.output_tokens,
                       result.usage.total_tokens, "model_reported")


def build_generation_client(config: HW6Config):
    return build_ollama_client(config.model, config.ollama_url, config.temperature,
                               config.model_timeout, context_window=config.context_window,
                               output_limit=config.output_limit, seed=config.seed)


class QwenTokenCounter:
    """Exact text tokens, estimated prompt components (chat template excluded)."""
    def __init__(self, path: Path | str, *, expected_sha256: str | None = None):
        from tokenizers import Tokenizer
        path = Path(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("Tokenizer SHA256 mismatch")
        self.identity = f"Qwen2.5/tokenizer.json:sha256:{digest}"
        self._tokenizer = Tokenizer.from_file(str(path))

    def __call__(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)


class OllamaEmbedder:
    """No model download or generation fallback. Caller owns the runtime lease."""
    def __init__(self, config: HW6Config):
        self.config = config
        self._client = httpx.Client(base_url=config.ollama_url, timeout=config.model_timeout)

    def __call__(self, text: str) -> list[float]:
        response = self._client.post("/api/embed", json={
            "model": self.config.embedding_model, "input": text, "truncate": False})
        response.raise_for_status()
        vectors = response.json().get("embeddings", [])
        if len(vectors) != 1 or len(vectors[0]) != self.config.embedding_dimension:
            raise ValueError("Embedding dimension differs from frozen configuration")
        vector = [float(value) for value in vectors[0]]
        if not all(math.isfinite(value) for value in vector) or not any(vector):
            raise ValueError("Embedding must be finite and nonzero")
        return vector

    def close(self) -> None:
        self._client.close()
