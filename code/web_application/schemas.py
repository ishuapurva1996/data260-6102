"""Strict camelCase HTTP schemas, separate from snake_case database models."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_validator


class RentalUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    listingTitle: str = Field(min_length=1, max_length=255)
    propertyAddress: str = Field(min_length=1, max_length=255)


class RentalCreate(RentalUpdate):
    submitterEmail: EmailStr = Field(max_length=254)
    description: str = Field(min_length=26, max_length=16000)
    propertyType: Literal["apartment", "house", "condo", "townhouse"]
    termsAccepted: StrictBool

    @field_validator("termsAccepted")
    @classmethod
    def accepted(cls, value):
        if not value:
            raise ValueError("Please agree to the terms and conditions.")
        return value


class RentalResponse(RentalCreate):
    id: int = Field(gt=0)


def rental_json(row):
    """Shared explicit serialization; Part 3 may append a manager field."""
    return {"id": row.id, "listingTitle": row.listing_title,
            "propertyAddress": row.property_address, "submitterEmail": row.submitter_email,
            "description": row.description, "propertyType": row.property_type,
            "termsAccepted": row.terms_accepted}
