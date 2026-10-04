"""Thin STDIO transport for the three shared rental operations."""

from typing import Any

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, ToolAnnotations
from pydantic import TypeAdapter

from src.rental_tools.contracts import ToolResult
from src.rental_tools.reader import RentalReader
from src.rental_tools.registry import TOOL_REGISTRY
from src.rental_tools.runtime import build_service


def create_server(reader: RentalReader | None = None) -> Server:
    server = Server("rentals")
    service = build_service(reader=reader)
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                idempotentHint=True, openWorldHint=False)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [Tool(
            name=name,
            description=definition.description,
            inputSchema=definition.input_model.model_json_schema(),
            # Retain the original broad dictionary output schema and envelope.
            outputSchema={**TypeAdapter(ToolResult).json_schema(), "title": name + "DictOutput"},
            annotations=read_only,
        ) for name, definition in TOOL_REGISTRY.items()]

    # FastMCP 1.28.1 drops extra fields before handler validation. The public
    # low-level API validates our shared schema against the original arguments.
    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> ToolResult:
        definition = TOOL_REGISTRY.get(name)
        if definition is None:
            raise ValueError("Unknown rental tool.")
        return definition.handler(service, **arguments)

    return server


async def run_stdio(server: Server) -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    anyio.run(run_stdio, create_server())


if __name__ == "__main__":
    main()
