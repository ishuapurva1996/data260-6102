"""Static allowlist for reuse by future executors; no dynamic dispatch or I/O."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .contracts import CountRentalsInput, GetRentalInput, SearchRentalsInput, ToolInput, ToolResult
from .service import RentalService


@dataclass(frozen=True)
class ToolDefinition:
    description: str
    input_model: type[ToolInput]
    handler: Callable[..., ToolResult]


TOOL_REGISTRY: Mapping[str, ToolDefinition] = MappingProxyType({
    "search_rentals": ToolDefinition(
        "Search public rental titles and addresses using literal case-insensitive text; return IDs in ascending order.",
        SearchRentalsInput, RentalService.search_rentals,
    ),
    "get_rental": ToolDefinition(
        "Get public rental details by positive integer ID. Submitter contact information is private; "
        "the assistant executor blocks include_contact=true. Direct service/MCP calls remain public-only.",
        GetRentalInput, RentalService.get_rental,
    ),
    "count_rentals": ToolDefinition(
        "Count rentals assigned to an existing property manager, including a count of zero.",
        CountRentalsInput, RentalService.count_rentals,
    ),
})
