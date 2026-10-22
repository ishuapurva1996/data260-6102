"""Single JSON-string entry point for the three public rental tools.

The injected service stays caller-owned. The default Part 3 runtime is imported
only after input validation and contact policy, and its per-call reader is always
closed. Direct service/MCP calls do not pass through this policy boundary.
"""

import json
import sys
from typing import Any

from pydantic import ValidationError

from .contracts import failure
from .registry import TOOL_REGISTRY
from .service import RentalService, _error

_INVALID_RESULT = '{"ok":false,"data":null,"error":"Rental tool returned an invalid result."}'
SAFETY_BLOCK_ERROR = "Safety block: rental submitter contact information is private."


def _serialize(result: Any) -> str:
    """Validate the common envelope before allowing strict JSON serialization."""
    try:
        if not isinstance(result, dict) or set(result) != {"ok", "data", "error"}:
            return _INVALID_RESULT
        if type(result["ok"]) is not bool:
            return _INVALID_RESULT
        if result["ok"]:
            if not isinstance(result["data"], dict) or result["error"] is not None:
                return _INVALID_RESULT
        elif (
            result["data"] is not None
            or not isinstance(result["error"], str)
            or not result["error"].strip()
        ):
            return _INVALID_RESULT
        return json.dumps(result, allow_nan=False)
    except Exception:
        # Do not stringify exceptions or partially emit untrusted result values.
        return _INVALID_RESULT


def validate_call(name, inputs):
    """Share the executor's pure validation with bounded agent repair."""
    if not isinstance(name, str) or name not in TOOL_REGISTRY:
        return None, failure("Unknown rental tool.")
    if not isinstance(inputs, dict) or any(not isinstance(key, str) for key in inputs):
        return None, failure("Invalid input: expected a dictionary with string keys.")
    try:
        return TOOL_REGISTRY[name].input_model.model_validate(inputs), None
    except ValidationError as exc:
        # Redact caller-controlled extra-field names while retaining the
        # shared formatter and every declared-field validation diagnostic.
        details = exc.errors(include_input=False, include_url=False)
        if any(error["type"] == "extra_forbidden" for error in details):
            for error in details:
                if error["type"] == "extra_forbidden":
                    error["loc"] = ("unexpected_field",)
            exc = ValidationError.from_exception_data(exc.title, details)
        return None, _error(exc)


def execute_tool(name: str, inputs: dict[str, Any], *, service: RentalService | None = None) -> str:
    """Validate arguments and policy, call one allowlisted handler, and return JSON."""
    owned_service = None
    try:
        arguments, error = validate_call(name, inputs)
        if error is not None:
            return _serialize(error)
        definition = TOOL_REGISTRY[name]

        if name == "get_rental" and arguments.include_contact:
            return _serialize(failure(SAFETY_BLOCK_ERROR))

        if service is None:
            try:
                from .runtime import build_service
            except ImportError:
                return _serialize(failure("Rental tool runtime is unavailable."))
            owned_service = build_service()
            service = owned_service

        return _serialize(definition.handler(service, **arguments.model_dump()))
    except Exception:
        return _serialize(failure("Rental data is temporarily unavailable."))
    finally:
        if owned_service is not None:
            try:
                owned_service.reader.close()
            except Exception:
                # A closed/broken stderr must not replace an already computed result.
                try:
                    print("Rental tool cleanup failed.", file=sys.stderr)
                except Exception:
                    pass
