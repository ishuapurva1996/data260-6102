"""Per-run state for the bounded Planner/Reviewer workflow."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class AgentState(TypedDict):
    title: str
    content: str
    email: str | None
    strict: bool
    task: str
    llm: Any  # Runtime adapter only; never serialize or checkpoint it.
    planner_proposal: dict[str, Any] | None
    planner_raw: Any
    proposal_revision: int
    reviewer_feedback: dict[str, Any] | None
    reviewer_raw: Any
    reviewed_revision: int | None
    revision_context: dict[str, Any]
    retry_target: Literal["planner", "reviewer"] | None
    retry_feedback: str | None
    turn_count: int
    max_turns: int
    pending_worker_turn: bool
    status: Literal["running", "accepted", "turn_limit", "error"]
    stop_reason: str | None
    error: dict[str, str] | None
    controlled_reviewer: bool
    trace: list[dict[str, Any]]
    adapter_response_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


def create_initial_state(
    *,
    title: str,
    content: str,
    llm: Any,
    email: str | None = None,
    max_turns: int = 10,
    controlled_reviewer: bool = False,
) -> AgentState:
    """Validate configuration and create fresh mutable state for one listing."""

    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a nonblank string")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("content must be a nonblank string")
    if type(max_turns) is not int or max_turns < 1:
        raise ValueError("max_turns must be a positive integer")
    if email is not None and not isinstance(email, str):
        raise ValueError("email must be a string or null")
    if not callable(getattr(llm, "complete", None)):
        raise ValueError("llm must provide the existing adapter's complete() interface")
    if not isinstance(controlled_reviewer, bool):
        raise ValueError("controlled_reviewer must be a boolean")
    return AgentState(
        title=title,
        content=content,
        email=email,
        strict=True,
        task="Generate exactly three topical tags and a summary of at most 25 words.",
        llm=llm,
        planner_proposal=None,
        planner_raw=None,
        proposal_revision=0,
        reviewer_feedback=None,
        reviewer_raw=None,
        reviewed_revision=None,
        revision_context={},
        retry_target=None,
        retry_feedback=None,
        turn_count=0,
        max_turns=max_turns,
        pending_worker_turn=False,
        status="running",
        stop_reason=None,
        error=None,
        controlled_reviewer=controlled_reviewer,
        trace=[],
        adapter_response_count=0,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
    )
