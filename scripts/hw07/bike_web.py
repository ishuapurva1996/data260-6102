"""Serve the shared application; each bike worker owns the model runtime lease."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.run_root, args.events):
        if path.resolve().is_relative_to(ROOT):
            parser.error("Run data and telemetry must be stored outside the repository.")
    from dotenv import load_dotenv

    load_dotenv(args.env_file, override=True)
    os.environ["HW7_SHARED_RUNTIME_DIR"] = str(args.runtime_dir.resolve())
    os.environ["HW7_BIKE_RUN_ROOT"] = str(args.run_root.resolve())
    import uvicorn
    from web_application.main import create_app

    from scripts.hw06.live_support import port_busy
    from scripts.hw06.runtime_lease import RuntimeLease
    from src.hw06_shared.config import HW6Config
    from src.hw06_shared.runtime import source_revision
    from src.hw06_shared.telemetry import JsonlTelemetry

    if port_busy():
        parser.error("Port 8702 is in use; do not stop an unowned server.")
    with RuntimeLease(
        args.runtime_dir, owner="HW7-P4-web-startup", purpose="initialize the shared application"
    ):
        config = HW6Config(
            **{**HW6Config.from_env().model_dump(), "source_commit": source_revision()}
        )
        app = create_app(hw6_config=config, hw6_telemetry=JsonlTelemetry(args.events))
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8702,
        workers=1,
        ssl_certfile=str(args.cert),
        ssl_keyfile=str(args.key),
        access_log=False,
    )


if __name__ == "__main__":
    main()
