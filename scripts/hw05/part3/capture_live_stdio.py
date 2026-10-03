"""Verify the unchanged three-tool protocol against the owned Part 3 MySQL DB.

Administrative fixture setup is separate. The DSN is supplied privately through
the environment; neither it nor dependency exception text enters this receipt.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from src.rental_tools.registry import TOOL_REGISTRY


async def capture(destination: Path):
    if destination.exists():
        raise ValueError("Refusing to overwrite a live receipt.")
    url = make_url(os.environ["HW5_MCP_DATABASE_URL"])
    if (url.drivername, url.host, url.port, url.database, url.username) != (
            "mysql+pymysql", "127.0.0.1", 3310, "s6102_rel", "hw5_part3_reader"):
        raise ValueError("The live capture requires the owned Part 3 reader on localhost:3310/s6102_rel.")
    paths = [*sorted((ROOT / "src/rental_tools").glob("*.py")),
             ROOT / "src/mcp_servers/rentals.py", Path(__file__).resolve()]
    receipt = {
        "student": "Pragya Apurva", "started_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "Actual MySQL public-column SELECT through real MCP STDIO subprocess",
        "host": "127.0.0.1", "port": 3310, "database": "s6102_rel",
        "runtime_user": "hw5_part3_reader", "command": [sys.executable, *sys.argv],
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)),
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "versions": {name: version(name) for name in ("mcp", "SQLAlchemy", "PyMySQL", "pydantic")},
        "calls": [], "native_schema_rejections": [],
    }
    cases = [
        ("search_rentals", {"query": "campus", "limit": 5}, True, None),
        ("get_rental", {"rental_id": 1}, True, None),
        ("count_rentals", {"manager_id": 1}, True, None),
        ("search_rentals", {"query": "   ", "limit": 5}, False,
         "Invalid input: query: Value error, query must contain non-whitespace characters"),
        ("get_rental", {"rental_id": 8}, False, "Rental 8 was not found."),
        ("count_rentals", {"manager_id": 4}, False, "Property manager 4 was not found."),
        ("search_rentals", {"query": "no-such-listing-part3"}, True, None),
        ("count_rentals", {"manager_id": 3}, True, None),
    ]
    params = StdioServerParameters(command=sys.executable,
        args=["-B", "-m", "src.mcp_servers.rentals"], cwd=str(ROOT), env=dict(os.environ))
    with anyio.fail_after(90):
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            receipt["initialize"] = (await session.initialize()).model_dump(mode="json")
            listing = await session.list_tools()
            assert {tool.name for tool in listing.tools} == set(TOOL_REGISTRY)
            for tool in listing.tools:
                assert tool.inputSchema == TOOL_REGISTRY[tool.name].input_model.model_json_schema()
            receipt["tools_list"] = listing.model_dump(mode="json")
            for name, inputs, expected_ok, expected_error in cases:
                result = await session.call_tool(name, inputs)
                envelope = result.structuredContent
                assert result.isError is False and envelope is not None
                assert set(envelope) == {"ok", "data", "error"}
                assert envelope["ok"] is expected_ok and envelope["error"] == expected_error
                assert (envelope["data"] is None) is (not expected_ok)
                receipt["calls"].append({"tool": name, "input": inputs, "result": result.model_dump(mode="json")})
            assert [item["id"] for item in receipt["calls"][0]["result"]["structuredContent"]["data"]["items"]] == [1, 2, 3, 4, 5]
            assert receipt["calls"][1]["result"]["structuredContent"]["data"]["listingTitle"] == "Sunny Downtown Apartment"
            assert receipt["calls"][2]["result"]["structuredContent"]["data"]["count"] == 5
            assert receipt["calls"][6]["result"]["structuredContent"]["data"]["items"] == []
            assert receipt["calls"][7]["result"]["structuredContent"]["data"]["count"] == 0
            for name, inputs, *_ in cases[:3]:
                invalid = await session.call_tool(name, {**inputs, "unexpected": True})
                assert invalid.isError is True and invalid.structuredContent is None
                receipt["native_schema_rejections"].append({"tool": name, "result": invalid.model_dump(mode="json")})
    receipt["passed"] = True
    receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
    encoded = json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False)
    assert not any(secret in encoded for secret in ("submitter_email", "synthetic-owner-", "mysql+pymysql://"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x") as output:
        output.write(encoded + "\n")
    print("Pragya Apurva")
    print("PASS: exact current inventory/schemas; 8 application outcomes; 3 native schema rejections.")
    print("PASS: actual MySQL on owned port 3310; STDIO subprocess exited; no private fields returned.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        anyio.run(capture, args.output)
    except Exception:
        # Avoid a traceback containing a DSN, SQL, or raw dependency exception.
        print("Live STDIO verification failed; no passing receipt produced.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
