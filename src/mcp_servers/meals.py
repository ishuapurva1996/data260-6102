"""The four tutorial tools, using the official MCP SDK's FastMCP STDIO server."""
import json
from typing import Annotated

from pydantic import Field

from .meals_client import MealsClient, MealsError


TextInput = Annotated[str, Field(strict=True, min_length=1)]
SearchLimit = Annotated[int, Field(strict=True, ge=1, le=25)]
IngredientLimit = Annotated[int, Field(strict=True, ge=1)]
MealId = (
    Annotated[str, Field(strict=True, pattern=r"^[0-9]*[1-9][0-9]*$")]
    | Annotated[int, Field(strict=True, gt=0)]
)


def create_server(*, client: MealsClient | None = None):
    """Construct a server without opening a connection or starting its event loop."""
    from mcp.server.fastmcp import FastMCP
    from mcp.types import CallToolResult, TextContent, ToolAnnotations

    upstream = client if client is not None else MealsClient()
    server = FastMCP("meals", log_level="WARNING")
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)

    async def call(awaitable):
        try:
            data = await awaitable
        except (MealsError, ValueError) as error:
            return CallToolResult(content=[TextContent(type="text", text=str(error))], isError=True)
        content = [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]
        if data is None or data == []:
            content.append(TextContent(type="text", text="No matches."))
        return CallToolResult(content=content)

    @server.tool(structured_output=False, annotations=read_only)
    async def search_meals_by_name(query: TextInput, limit: SearchLimit = 5):
        """Search TheMealDB by meal name; return id, name, area, category, and thumb."""
        return await call(upstream.search_meals_by_name(query, limit))

    @server.tool(structured_output=False, annotations=read_only)
    async def meals_by_ingredient(ingredient: TextInput, limit: IngredientLimit = 12):
        """Find meals by one main ingredient; return id, name, and thumb."""
        return await call(upstream.meals_by_ingredient(ingredient, limit))

    @server.tool(structured_output=False, annotations=read_only)
    async def random_meal():
        """Return one random full recipe, including its ingredient measurements."""
        return await call(upstream.random_meal())

    @server.tool(structured_output=False, annotations=read_only)
    async def meal_details(id: MealId):
        """Look up a positive meal ID and return the full recipe."""
        return await call(upstream.meal_details(id))

    return server


def main():
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
