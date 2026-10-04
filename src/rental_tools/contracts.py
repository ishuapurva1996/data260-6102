"""The single input contract for the three public rental tools."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator

SearchQuery = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=255)]
SearchLimit = Annotated[StrictInt, Field(ge=1, le=25)]
PositiveId = Annotated[StrictInt, Field(gt=0)]
ToolResult = dict[str, Any]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchRentalsInput(ToolInput):
    query: SearchQuery
    limit: SearchLimit = 5

    @field_validator("query")
    @classmethod
    def trim_nonempty_query(cls, query: str) -> str:
        # Field length validation runs first, so surrounding spaces count toward 255.
        query = query.strip()
        if not query:
            raise ValueError("query must contain non-whitespace characters")
        return query


class GetRentalInput(ToolInput):
    rental_id: PositiveId


class CountRentalsInput(ToolInput):
    manager_id: PositiveId


def success(data: dict[str, Any]) -> ToolResult:
    return {"ok": True, "data": data, "error": None}


def failure(message: str) -> ToolResult:
    return {"ok": False, "data": None, "error": message}
