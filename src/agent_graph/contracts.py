"""Small strict output checks; Part 4's Pydantic experiment is separate."""

from __future__ import annotations

import json
from typing import Any


class ResponseContractError(ValueError):
    """A returned response is malformed or violates the role's output contract."""


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

    if not isinstance(value, dict) or set(value) != {"tags", "summary"}:
        raise ResponseContractError("Planner object must contain only tags and summary")
    tags = value["tags"]
    if not isinstance(tags, list) or len(tags) != 3:
        raise ResponseContractError("tags must contain exactly three strings")
    if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise ResponseContractError("Every tag must be a nonblank string")
    summary = value["summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise ResponseContractError("summary must be a nonblank string")
    if len(summary.split()) > 25:
        raise ResponseContractError("summary must contain at most 25 whitespace-delimited words")
    return value


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
