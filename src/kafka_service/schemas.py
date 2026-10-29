"""Top-level Kafka envelopes and the existing semester rental validator."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from web_application.schemas import RentalCreate

from .config import ENTITY_RESPONSES


class RentalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    correlation_id: str = Field(min_length=1, max_length=128)
    reply_to: Literal[ENTITY_RESPONSES]
    operation: str = Field(min_length=1, max_length=64)
    data: dict

    @field_validator("correlation_id")
    @classmethod
    def nonblank_identity(cls, value):
        if not value.strip():
            raise ValueError("correlation_id must not be blank")
        return value  # Preserve the caller's actual value.


class RentalLookup(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    rental_id: str

    @field_validator("rental_id")
    @classmethod
    def valid_uuid(cls, value):
        return str(UUID(value))


def validate_data(operation: str, data: dict) -> dict:
    if operation == "CREATE_RENTAL":
        return RentalCreate.model_validate(data).model_dump(mode="json", exclude_none=True)
    if operation == "GET_RENTAL":
        return RentalLookup.model_validate(data).model_dump()
    raise ValueError("Unknown operation")


def clean_validation_error(exc) -> str:
    """Keep field explanations without raw inputs or Pydantic implementation URLs."""
    return "; ".join(
        f"{'.'.join(str(p) for p in item['loc'])}: {item['msg']}" for item in exc.errors()
    )


def error_response(payload, error: str, *, transport=False) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    result = {
        "correlation_id": payload.get("correlation_id"),
        "operation": payload.get("operation"),
        "success": False,
        "error": error,
    }
    if transport:
        result["transport_error"] = True
    return result
