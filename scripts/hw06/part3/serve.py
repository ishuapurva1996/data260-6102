"""Owned child server using A's published create_app injections, under D's lease."""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, action="append", required=True)
    parser.add_argument("--config-json", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    owner = json.loads((args.runtime_dir / "owner.json").read_text())
    if (owner.get("owner") != "D" or owner.get("pid") != os.getppid() or
            not os.environ.get("HW6_D_LEASE_TOKEN") or owner.get("token") != os.environ["HW6_D_LEASE_TOKEN"]):
        parser.error("Only the D lease-owning parent may start this server")
    from dotenv import load_dotenv
    for path in args.env_file:
        load_dotenv(path, override=True)
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / "code"))
    from src.hw06_shared.config import HW6Config
    from src.hw06_shared.telemetry import JsonlTelemetry
    from src.hw06_experiments.policy import token_budget_window
    from web_application.main import create_app
    import uvicorn
    base = HW6Config.from_env()
    config = HW6Config(**{**base.model_dump(), **json.loads(args.config_json.read_text())})
    app = create_app(hw6_config=config,
                     hw6_window_policy=token_budget_window if config.policy == "token_budget" else None,
                     hw6_telemetry=JsonlTelemetry(args.events))
    uvicorn.run(app, host="127.0.0.1", port=8702, ssl_certfile=str(args.cert), ssl_keyfile=str(args.key),
                access_log=False)


if __name__ == "__main__":
    main()
