"""Thin STDIO transport for the three shared rental operations."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from src.rental_tools.contracts import PositiveId, SearchLimit, SearchQuery, ToolResult
from src.rental_tools.reader import MySQLRentalReader, RentalReader
from src.rental_tools.registry import TOOL_REGISTRY
from src.rental_tools.service import RentalService


def create_server(reader: RentalReader | None = None) -> FastMCP:
    server = FastMCP("rentals", log_level="WARNING")
    service = RentalService(reader if reader is not None else MySQLRentalReader())
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                idempotentHint=True, openWorldHint=False)

    @server.tool(description=TOOL_REGISTRY["search_rentals"].description, annotations=read_only)
    def search_rentals(query: SearchQuery, limit: SearchLimit = 5) -> ToolResult:
        return service.search_rentals(query=query, limit=limit)

    @server.tool(description=TOOL_REGISTRY["get_rental"].description, annotations=read_only)
    def get_rental(rental_id: PositiveId) -> ToolResult:
        return service.get_rental(rental_id=rental_id)

    @server.tool(description=TOOL_REGISTRY["count_rentals"].description, annotations=read_only)
    def count_rentals(manager_id: PositiveId) -> ToolResult:
        return service.count_rentals(manager_id=manager_id)

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
