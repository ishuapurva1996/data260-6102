"""Versioned event schema; absent model counts are null, never measured zeros."""
from datetime import datetime
from collections.abc import Mapping
import json
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .serialization import new_id


class RequestContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: str = Field(default_factory=new_id)
    run_id: str | None = None
    condition: str | None = None
    turn_id: int | None = Field(default=None, ge=1)
    probe_id: str | None = None
    phase: Literal["demo", "warmup", "primary", "probe", "test"] = "demo"
    source_commit: str | None = None


def request_context_from_headers(headers: Mapping[str, str], *, source_commit: str | None = None) -> RequestContext:
    """Experiment headers supply correlation; the server supplies its revision."""
    headers = {key.lower(): value for key, value in headers.items()}
    names = ("request_id", "run_id", "condition", "turn_id", "probe_id", "phase")
    values = {name: headers[key] for name in names
              if (key := "x-hw6-" + name.replace("_", "-")) in headers}
    return RequestContext(**values, source_commit=source_commit)


class TokenComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: int = Field(default=0, ge=0)
    session_summary: int = Field(default=0, ge=0)
    lifetime_summary: int = Field(default=0, ge=0)
    window: int = Field(default=0, ge=0)
    episodes: int = Field(default=0, ge=0)
    current_message: int = Field(default=0, ge=0)
    template_residual: int | None = None
    count_method: str = "model_tokenizer_text_estimate"
    tokenizer_identity: str | None = None


class PromptText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: str = ""
    session_summary: str = ""
    lifetime_summary: str = ""
    window: str = ""
    episodes: str = ""
    current_message: str = ""


class CallEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["hw06.v1"] = "hw06.v1"
    event_id: str = Field(default_factory=new_id)
    context: RequestContext
    kind: Literal["request", "generation", "embedding"]
    operation: Literal["chat", "extraction", "session_summary", "lifetime_summary", "query", "fact"]
    started_at: AwareDatetime
    user_id: str
    session_id: str
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    status: Literal["ok", "error"] = "ok"
    error_code: str | None = None
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    usage_source: Literal["model_reported", "missing", "not_applicable"] = "missing"
    finish_reason: str | None = None
    components: TokenComponents | None = None
    component_text: PromptText | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    embedding_dimension: int | None = Field(default=None, gt=0)
    input_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_usage(self):
        if self.usage_source == "model_reported":
            if self.prompt_tokens is None or self.completion_tokens is None:
                raise ValueError("model_reported requires prompt and completion counts")
        elif any(value is not None for value in
                 (self.prompt_tokens, self.completion_tokens, self.total_tokens)):
            raise ValueError("Missing or inapplicable usage must have null token totals")
        operations = {"request": {"chat"}, "generation": {
            "extraction", "session_summary", "lifetime_summary"}, "embedding": {"query", "fact"}}
        if self.operation not in operations[self.kind]:
            raise ValueError("Event kind and operation do not match")
        return self


class NullTelemetry:
    def emit(self, event: CallEvent) -> None:
        pass


class JsonlTelemetry:
    """One writer process per file; thread-safe within that process."""
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = Lock()

    def emit(self, event: CallEvent) -> None:
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, allow_nan=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
