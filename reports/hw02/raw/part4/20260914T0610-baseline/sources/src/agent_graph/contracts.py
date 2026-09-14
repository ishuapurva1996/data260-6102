"""Strict JSON parsing and Pydantic validation for Planner proposals."""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictStr, ValidationError


class ResponseContractError(ValueError):
    """A returned response is malformed or violates the role's output contract."""


def _tag_text(value: str) -> str:
    """Count the original Python string, including whitespace, without rewriting it."""

    if not value.strip():
        raise ValueError("tag must be a nonblank string")
    if len(value) < 3:
        raise ValueError("tag must contain at least 3 characters (Python string length)")
    if len(value) > 30:
        raise ValueError("tag must contain at most 30 characters (Python string length)")
    return value


def _summary_text(value: str) -> str:
    if not value.strip():
        raise ValueError("summary must be a nonblank string")
    if len(value.split()) > 25:
        raise ValueError("summary must contain at most 25 whitespace-delimited words")
    return value


class PlannerProposal(BaseModel):
    """Part 4 contract; validation rejects invalid data without coercion or repair."""

    model_config = ConfigDict(strict=True, extra="forbid")

    tags: list[Annotated[StrictStr, AfterValidator(_tag_text)]] = Field(
        min_length=3, max_length=3,
    )
    summary: Annotated[StrictStr, AfterValidator(_summary_text)]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResponseContractError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ResponseContractError(f"Invalid JSON constant: {value}")


def _object(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise ResponseContractError("Response must be text containing one JSON object")
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
    except json.JSONDecodeError as exc:
        raise ResponseContractError(f"Response must be one whole JSON object: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ResponseContractError("Response must be a JSON object")
    return value


def validate_planner_proposal(value: Any) -> dict[str, Any]:
    """Validate without changing tags, trimming text, or supplying missing values."""

    if not isinstance(value, dict):
        raise ResponseContractError("Planner response must be a JSON object")
    try:
        proposal = PlannerProposal.model_validate(value)
    except ValidationError as exc:
        # Keep diagnostics useful to the Planner and safe for JSON trace evidence.
        # Pydantic's context may contain exception objects; retain plain messages only.
        details = []
        for error in exc.errors(include_context=False, include_url=False):
            location = ".".join(str(part) for part in error["loc"]) or "proposal"
            details.append(f"{location}: {error['msg']}")
        raise ResponseContractError("; ".join(details)) from exc
    return proposal.model_dump()


def parse_planner_response(raw: Any) -> dict[str, Any]:
    return validate_planner_proposal(_object(raw))


def validate_reviewer_feedback(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or "issues" not in value:
        raise ResponseContractError("Reviewer object must contain an explicit issues array")
    if set(value) - {"issues", "message", "explanation"}:
        raise ResponseContractError("Reviewer may return only issues and an optional message or explanation")
    issues = value["issues"]
    if not isinstance(issues, list) or any(not isinstance(issue, str) for issue in issues):
        raise ResponseContractError("issues must be an array of strings; [] explicitly means approval")
    for key in ("message", "explanation"):
        if key in value and not isinstance(value[key], str):
            raise ResponseContractError(f"Reviewer {key} must be a string")
    return value


def parse_reviewer_response(raw: Any) -> dict[str, Any]:
    return validate_reviewer_feedback(_object(raw))
