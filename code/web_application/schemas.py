"""Strict camelCase HTTP schemas, separate from snake_case database models."""
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_validator


ListingCode = Annotated[str, Field(pattern=r"^S6102-R-[1-9][0-9]*$", max_length=64)]
AvailableUnits = Annotated[int, Field(strict=True, ge=0, le=2147483647)]
ManagerId = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
PropertyType = Literal["apartment", "house", "condo", "townhouse"]


class RentalUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    listingTitle: str = Field(min_length=1, max_length=255)
    propertyAddress: str = Field(min_length=1, max_length=255)
    listingCode: ListingCode | None = None
    availableUnits: AvailableUnits | None = None
    managerId: ManagerId | None = None
    submitterEmail: EmailStr | None = Field(default=None, max_length=254)
    description: str | None = Field(default=None, min_length=26, max_length=16000)
    propertyType: PropertyType | None = None
    termsAccepted: StrictBool | None = None

    @field_validator("listingCode", "availableUnits", "submitterEmail", "description",
                     "propertyType", "termsAccepted", mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null when supplied.")
        return value

    @field_validator("termsAccepted")
    @classmethod
    def accepted(cls, value):
        if not value:
            raise ValueError("Please agree to the terms and conditions.")
        return value


class RentalCreate(RentalUpdate):
    availableUnits: AvailableUnits = 1
    submitterEmail: EmailStr = Field(max_length=254)
    description: str = Field(min_length=26, max_length=16000)
    propertyType: PropertyType
    termsAccepted: StrictBool


class RentalResponse(RentalCreate):
    id: int = Field(gt=0)
    listingCode: ListingCode
    createdAt: datetime
    updatedAt: datetime


class ManagerCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    email: EmailStr = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.casefold() if isinstance(value, str) else value


class ManagerResponse(ManagerCreate):
    id: int = Field(gt=0)
    createdAt: datetime
    updatedAt: datetime


def as_utc(value):
    """Stored naive MySQL datetimes represent UTC, exposed with a UTC offset."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def rental_json(row):
    """Shared explicit serialization; performance routes append a manager field."""
    return {"id": row.id, "listingTitle": row.listing_title,
            "propertyAddress": row.property_address, "submitterEmail": row.submitter_email,
            "description": row.description, "propertyType": row.property_type,
            "termsAccepted": row.terms_accepted, "listingCode": row.listing_code,
            "availableUnits": row.available_units, "managerId": row.manager_id,
            "createdAt": as_utc(row.created_at), "updatedAt": as_utc(row.updated_at)}


def manager_json(row):
    return {"id": row.id, "name": row.name, "company": row.company, "email": row.email,
            "createdAt": as_utc(row.created_at), "updatedAt": as_utc(row.updated_at)}
