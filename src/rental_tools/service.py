"""Validated operations with explicit public projections and shared envelopes."""

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from .contracts import CountRentalsInput, GetRentalInput, SearchRentalsInput, ToolResult, failure, success
from .reader import RentalReader, RentalReaderConfigurationError


def _public_listing(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "listingTitle": row["listing_title"],
        "propertyAddress": row["property_address"], "propertyType": row["property_type"],
        "managerId": row["manager_id"],
    }


def _error(exc: Exception) -> ToolResult:
    if isinstance(exc, ValidationError):
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        return failure(f"Invalid input: {details}")
    if isinstance(exc, RentalReaderConfigurationError):
        return failure("Rental data is unavailable. Check HW5_MCP_DATABASE_URL configuration.")
    # Never stringify dependency exceptions: DB errors may contain credentials/SQL.
    return failure("Rental data is temporarily unavailable.")


class RentalService:
    def __init__(self, reader: RentalReader):
        self.reader = reader

    def search_rentals(self, **inputs: Any) -> ToolResult:
        try:
            args = SearchRentalsInput.model_validate(inputs)
            items = [_public_listing(row) for row in self.reader.search_rentals(args.query, args.limit)]
            return success({"items": items, "returnedCount": len(items), "limit": args.limit})
        except Exception as exc:
            return _error(exc)

    def get_rental(self, **inputs: Any) -> ToolResult:
        try:
            args = GetRentalInput.model_validate(inputs)
            row = self.reader.get_rental(args.rental_id)
            if row is None:
                return failure(f"Rental {args.rental_id} was not found.")
            data = _public_listing(row)
            data["description"] = row["description"]
            return success(data)
        except Exception as exc:
            return _error(exc)

    def count_rentals(self, **inputs: Any) -> ToolResult:
        try:
            args = CountRentalsInput.model_validate(inputs)
            row = self.reader.count_rentals(args.manager_id)
            if row is None:
                return failure(f"Property manager {args.manager_id} was not found.")
            return success({"managerId": row["manager_id"], "managerName": row["manager_name"], "count": row["count"]})
        except Exception as exc:
            return _error(exc)
