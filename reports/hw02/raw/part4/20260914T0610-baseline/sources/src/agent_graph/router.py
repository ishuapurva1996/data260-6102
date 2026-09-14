"""Pure decisions over state; counting and terminal updates belong to the supervisor."""

from __future__ import annotations

from langgraph.graph import END

from .contracts import (
    ResponseContractError,
    validate_planner_proposal,
    validate_reviewer_feedback,
)
from .state import AgentState


def has_current_approval(state: AgentState) -> bool:
    if state["proposal_revision"] < 1 or state["reviewed_revision"] != state["proposal_revision"]:
        return False
    try:
        validate_planner_proposal(state["planner_proposal"])
        feedback = validate_reviewer_feedback(state["reviewer_feedback"])
    except ResponseContractError:
        return False
    return not feedback["issues"]


def router_logic(state: AgentState) -> str:
    """Choose the next node without modifying state or calling a model."""

    if state["status"] != "running":
        return END
    if state["retry_target"] is not None:
        return state["retry_target"]
    if state["planner_proposal"] is None:
        return "planner"
    if state["reviewed_revision"] == state["proposal_revision"]:
        feedback = state["reviewer_feedback"]
        if feedback is not None and feedback["issues"]:
            return "planner"
    return "reviewer"
