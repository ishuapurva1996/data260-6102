"""Rental inputs and JSON responses; BSON dates have UTC millisecond precision."""
from datetime import datetime, timezone
import re
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


Status = Literal["available", "reserved", "rented"]
PropertyType = Literal["apartment", "house", "condo", "townhouse"]
ISO_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})")


def bson_utc(value: datetime) -> datetime:
    """Match PyMongo's millisecond storage so POST, PUT and GET agree exactly."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Date/time must include a timezone")
    value = value.astimezone(timezone.utc)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


class RentalFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listingTitle: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    description: Annotated[str | None, Field(strict=True, max_length=5000)] = None
    status: Status = "available"
    propertyType: PropertyType
    availableFrom: AwareDatetime

    @field_validator("listingTitle", mode="before")
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("availableFrom", mode="before")
    @classmethod
    def require_iso_datetime(cls, value):
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or ISO_DATETIME.fullmatch(value) is None:
            raise ValueError("Use ISO 8601 YYYY-MM-DDTHH:MM:SS[.ffffff]Z or an explicit ±HH:MM offset")
        return value

    @field_validator("availableFrom")
    @classmethod
    def normalize_utc(cls, value):
        return bson_utc(value)


class RentalCreate(RentalFields):
    """Server assigns the identifier and both timestamps; those inputs are forbidden."""


class RentalUpdate(RentalFields):
    """Full PUT: all required fields; omitted status/description reset to defaults."""


class RentalResponse(RentalFields):
    id: str = Field(pattern=r"^[0-9a-f]{24}$")
    created_at: AwareDatetime
    updated_at: AwareDatetime
