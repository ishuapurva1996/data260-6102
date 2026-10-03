#!/usr/bin/env python3
"""Save genuine MCP initialization/discovery/call results. No GUI claims.

Run from the dedicated MCP environment. Domain calls use the explicitly
configured MySQL reader; fixture setup is a separate administrative action.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


async def capture(server, destination):
    environment = dict(os.environ)
    expected = ({"search_meals_by_name", "meals_by_ingredient", "random_meal", "meal_details"}
                if server == "meals" else {"search_rentals", "get_rental", "count_rentals"})
    if server == "meals":
        source = {"kind": "live public API", "base": "https://www.themealdb.com/api/json/v1/1/"}
        calls = [("search_meals_by_name", {"query": "Arrabiata", "limit": 5}),
                 ("meals_by_ingredient", {"ingredient": "chicken", "limit": 3}),
                 ("random_meal", {}), ("meal_details", {"id": "52771"})]
        launcher = "run_meals.py"
    else:
        from sqlalchemy.engine import make_url
        from src.rental_tools.reader import MySQLRentalReader, rentals, property_managers
        reader = MySQLRentalReader()
        url = make_url(environment["HW5_MCP_DATABASE_URL"])
        source = {"kind": "live MySQL", "host": url.host, "port": url.port,
                  "database": url.database, "user": url.username}
        with reader._get_engine().connect() as connection:
            first_rental, max_rental = connection.execute(select(func.min(rentals.c.id),func.max(rentals.c.id))).one()
            first_manager, max_manager = connection.execute(select(func.min(property_managers.c.id),func.max(property_managers.c.id))).one()
        if first_rental is None or first_manager is None:
            raise RuntimeError("Live capture requires at least one rental and manager.")
        missing_rental, missing_manager = max_rental + 1, max_manager + 1
        assert reader.get_rental(missing_rental) is None
        assert reader.count_rentals(missing_manager) is None
        query = reader.get_rental(first_rental)["listing_title"]
        reader.close()
        source["confirmed_absent_ids"] = {"rental_id": missing_rental, "manager_id": missing_manager}
        calls = [("search_rentals", {"query": query, "limit": 5}),
                 ("search_rentals", {"query": "   ", "limit": 5}),
                 ("get_rental", {"rental_id": first_rental}),
                 ("get_rental", {"rental_id": missing_rental}),
                 ("count_rentals", {"manager_id": first_manager}),
                 ("count_rentals", {"manager_id": missing_manager})]
        launcher = "run_domain.py"
    record = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "client": "official Python MCP SDK ClientSession over real STDIO",
              "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,text=True).strip(),
              "source": source, "calls": []}
    params = StdioServerParameters(command=sys.executable,
        args=[str(ROOT / "scripts/hw05/part2" / launcher)], cwd=str(ROOT), env=environment)
    with anyio.fail_after(120):
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            record["initialize"] = (await session.initialize()).model_dump(mode="json")
            listed = await session.list_tools()
            record["tools_list"] = listed.model_dump(mode="json")
            assert {tool.name for tool in listed.tools} == expected
            for name, arguments in calls:
                result = await session.call_tool(name, arguments)
                record["calls"].append({"request": {"method": "tools/call",
                    "params": {"name": name, "arguments": arguments}},
                    "result": result.model_dump(mode="json")})
            if server == "domain":
                record["native_sdk_errors"] = []
                for arguments in [{}, {"rental_id": False}, {"rental_id": 0}, {"rental_id": "1"}]:
                    result = await session.call_tool("get_rental", arguments)
                    record["native_sdk_errors"].append({"arguments": arguments,
                        "result": result.model_dump(mode="json")})
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n")
    if any(call["result"]["isError"] for call in record["calls"]):
        raise RuntimeError("A required live call failed; saved results are failed-run evidence.")
    if server == "domain":
        assert [json.loads(c["result"]["content"][0]["text"])["ok"] for c in record["calls"]] == [True,False,True,False,True,False]
    print(f"{server}: exact inventory and {len(calls)} STDIO calls verified; saved {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server", choices=["meals", "domain"])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    anyio.run(capture, args.server, args.output)


if __name__ == "__main__":
    main()
