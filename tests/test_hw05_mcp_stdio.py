"""Exercise initialization, discovery, calls and native errors over actual pipes."""
import json
import os
from pathlib import Path
import subprocess
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def data(result):
    return json.loads(result.content[0].text)


def test_meals_stdio_inventory_and_all_four_calls():
    async def scenario():
        params = StdioServerParameters(command=sys.executable,
            args=[str(ROOT / "tests/hw05_stdio_fixture.py"), "meals"], cwd=str(ROOT))
        with anyio.fail_after(20):
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "meals"
                tools = (await session.list_tools()).tools
                assert {tool.name for tool in tools} == {
                    "search_meals_by_name", "meals_by_ingredient", "random_meal", "meal_details"}
                calls = [("search_meals_by_name", {"query": "Recipe"}),
                         ("meals_by_ingredient", {"ingredient": "tomato"}),
                         ("random_meal", {}), ("meal_details", {"id": "52772"})]
                for name, args in calls:
                    result = await session.call_tool(name, args)
                    assert not result.isError
                    payload = data(result)
                    if name in {"search_meals_by_name", "meals_by_ingredient"}:
                        assert isinstance(payload, list) and payload[0]["id"] == "52772"
                    else:
                        assert payload["ingredients"] == [{"name": "Tomato", "measure": "1 cup"}]
                empty = await session.call_tool("search_meals_by_name", {"query": "absent"})
                assert data(empty) == [] and "No matches" in empty.content[1].text
                invalid = await session.call_tool("search_meals_by_name", {"query": "x", "limit": 26})
                assert invalid.isError
    anyio.run(scenario)


def test_domain_stdio_inventory_envelopes_and_sdk_boundary():
    async def scenario():
        params = StdioServerParameters(command=sys.executable,
            args=[str(ROOT / "tests/hw05_stdio_fixture.py"), "domain"], cwd=str(ROOT))
        with anyio.fail_after(20):
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                assert set(tools) == {"search_rentals", "get_rental", "count_rentals"}
                assert tools["search_rentals"].inputSchema["properties"]["query"]["minLength"] == 1
                cases = [("search_rentals", {"query": "campus"}, True),
                         ("search_rentals", {"query": "   "}, False),
                         ("get_rental", {"rental_id": 1}, True),
                         ("get_rental", {"rental_id": 99}, False),
                         ("count_rentals", {"manager_id": 1}, True),
                         ("count_rentals", {"manager_id": 99}, False)]
                for name, args, ok in cases:
                    result = await session.call_tool(name, args)
                    assert not result.isError  # semantic failures are application envelopes
                    payload = data(result)
                    assert set(payload) == {"ok", "data", "error"} and payload["ok"] is ok
                    assert (payload["error"] is None) is ok
                    assert "PRIVATE_SENTINEL" not in result.model_dump_json()
                zero = data(await session.call_tool("count_rentals", {"manager_id": 2}))
                assert zero["ok"] and zero["data"]["count"] == 0
                for args in [{}, {"rental_id": False}, {"rental_id": 0}]:
                    invalid = await session.call_tool("get_rental", args)
                    assert invalid.isError  # native SDK validation precedes handler
    anyio.run(scenario)


def test_imports_do_not_connect_or_print_protocol_noise():
    code = """
import socket
def blocked(*args, **kwargs):
    raise AssertionError('Network access during import')
socket.create_connection = blocked
socket.socket.connect = blocked
import src.mcp_servers.meals
import src.mcp_servers.rentals
import src.rental_tools.reader
"""
    env = {k: v for k, v in os.environ.items() if k != "HW5_MCP_DATABASE_URL"}
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
