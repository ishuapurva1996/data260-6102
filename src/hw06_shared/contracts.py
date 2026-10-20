"""Public role seams. Worker implementations live in their owned packages."""
from datetime import datetime
from typing import Any, Literal, Protocol, Sequence, TypedDict

from pydantic import BaseModel, ConfigDict, Field
from pymongo.database import Database

from src.model_client import CompletionResult
from .config import HW6Config
from .telemetry import CallEvent, RequestContext


class MessageRecord(TypedDict):
    id: str
    user_id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class GenerationClient(Protocol):
    def complete(self, messages: Sequence[Any], tools: Sequence[Any] | None = None) -> CompletionResult: ...


class Embedder(Protocol):
    def __call__(self, text: str) -> list[float]: ...


class TokenCounter(Protocol):
    def __call__(self, text: str) -> int: ...


class Clock(Protocol):
    def __call__(self) -> datetime: ...


class TelemetrySink(Protocol):
    def emit(self, event: CallEvent) -> None: ...


def render_window(messages: Sequence[MessageRecord]) -> str:
    """Canonical text for window policy and component estimates; oldest first."""
    return "\n".join(f"{message['role']}: {message['content']}" for message in messages)


class WindowPolicy(Protocol):
    def __call__(self, messages: Sequence[MessageRecord], *, short_term_n: int,
                 token_budget: int, count_tokens: TokenCounter) -> list[MessageRecord]: ...


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_id: str = Field(min_length=1, max_length=200)
    session_id: str | None = Field(default=None, min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=16000)


class MemoryUsed(BaseModel):
    short_term_count: int = Field(ge=0)
    short_term_messages: list[MessageRecord]
    session_summary: str | None = None
    lifetime_summary: str | None = None
    episodes: list["EpisodeUsed"] = Field(default_factory=list)
    policy: str = "baseline"


class ChatResponse(BaseModel):
    user_id: str
    session_id: str
    request_id: str
    reply: str
    memory_used: MemoryUsed


class EpisodeUsed(BaseModel):
    id: str
    fact: str
    importance: float = Field(ge=0, le=1, allow_inf_nan=False)
    similarity: float = Field(ge=-1, le=1, allow_inf_nan=False)
    created_at: datetime


class SummaryRecord(TypedDict):
    id: str
    user_id: str
    session_id: str | None
    scope: Literal["session", "user"]
    text: str
    created_at: datetime


class EpisodeRecord(TypedDict):
    id: str
    user_id: str
    session_id: str
    fact: str
    importance: float
    embedding: list[float]
    created_at: datetime


class MemorySnapshot(BaseModel):
    user_id: str
    session_id: str | None
    messages: list[MessageRecord]
    session_summary: SummaryRecord | None
    lifetime_summary: SummaryRecord | None
    episodes: list[EpisodeRecord]


class DailyCount(BaseModel):
    date: str
    count: int = Field(ge=0)


class AggregateResponse(BaseModel):
    user_id: str
    daily_message_counts: list[DailyCount]
    recent_summaries: list[SummaryRecord]


MemoryUsed.model_rebuild()


class ChatService(Protocol):
    def chat(self, request: ChatRequest, *, context: RequestContext | None = None) -> ChatResponse: ...
    def memory(self, user_id: str, *, session_id: str | None = None) -> MemorySnapshot: ...
    def aggregate(self, user_id: str) -> AggregateResponse: ...


class MemoryStorage(Protocol):
    """C owns storage operations; its database is A's shared managed database."""
    database: Database


class ChatServiceFactory(Protocol):
    def __call__(self, *, model: GenerationClient, embedder: Embedder,
                 storage: MemoryStorage, config: HW6Config, count_tokens: TokenCounter,
                 clock: Clock, telemetry: TelemetrySink,
                 window_policy: WindowPolicy | None = None) -> ChatService: ...


def authorize_memory_user(user_id: str, principal: Any) -> None:
    """Authenticated owner or synthetic experiment namespace of that owner."""
    from fastapi import HTTPException
    owner = str(principal.id)
    if user_id != owner and not user_id.startswith(owner + ":hw6:"):
        raise HTTPException(status_code=403, detail="Memory belongs to another user.")
