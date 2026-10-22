"""Run one private framework job inside the shared model lease."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]

from scripts.hw06.runtime_lease import LeaseBusy, RuntimeLease
from src.bikeshare.agent import run_bike_agent
from src.bikeshare.config import BikeConfig
from src.bikeshare.service import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    directory = args.request.parent

    def console(row):
        if row["event"] in {"tool_request", "tool_result", "tool_rejected"}:
            print(json.dumps(row, ensure_ascii=False), flush=True)

    try:
        with RuntimeLease(
            request["runtime_dir"],
            owner="HW7-P4-" + request["run_id"],
            purpose="authenticated framework bike-share run",
        ):
            result = run_bike_agent(
                (directory / "input.csv").read_bytes(),
                request["pricing_url"],
                config=BikeConfig(**request["configuration"]),
                run_id=request["run_id"],
                user_id=request["user_id"],
                run_dir=directory,
                event_callback=console,
            )
        print(
            "Pragya Apurva |",
            result["metrics"]["stop_reason"],
            "| steps",
            result["metrics"]["steps"],
            "| actual tools",
            result["metrics"]["tool_calls"],
            "| tokens",
            result["metrics"]["total_tokens"],
            flush=True,
        )
        print("MODEL_FINAL", result["model_answer"], flush=True)
        print("VERIFICATION", json.dumps(result["verification"]), flush=True)
        write_json(directory / "state.json", {"status": "completed", "error": result.get("error")})
    except LeaseBusy:
        write_json(
            directory / "state.json",
            {
                "status": "failed",
                "error": "The shared model runtime is busy. Try again after the active run finishes.",
            },
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
