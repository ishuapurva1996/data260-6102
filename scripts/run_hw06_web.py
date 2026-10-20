#!/usr/bin/env python3
"""Run the extended application on 8702 using external configuration and TLS."""
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'code')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', action='append', type=Path, required=True)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--cert', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--config-json', type=Path)
    parser.add_argument('--inherited-lease', action='store_true')
    args = parser.parse_args()
    from dotenv import load_dotenv
    for path in args.env_file:
        load_dotenv(path, override=True)
    from scripts.hw06.runtime_lease import RuntimeLease
    if args.inherited_lease:
        owner = json.loads((args.runtime_dir / 'owner.json').read_text())
        if (owner['pid'] != os.getppid() or not os.environ.get('HW6_PARENT_LEASE_TOKEN')
                or owner['token'] != os.environ['HW6_PARENT_LEASE_TOKEN']):
            parser.error('Only a lease-owning parent may start this child server')
        lease = nullcontext()
    else:
        lease = RuntimeLease(args.runtime_dir, owner='A-app', purpose='integrated HTTPS application')
    from src.hw06_shared.config import HW6Config
    from src.hw06_shared.telemetry import JsonlTelemetry
    from web_application.main import create_app
    import uvicorn
    config = HW6Config.from_env()
    if args.config_json:
        config = HW6Config(**{**config.model_dump(), **json.loads(args.config_json.read_text())})
    with lease:
        app = create_app(hw6_config=config, hw6_telemetry=JsonlTelemetry(args.events))
        uvicorn.run(app, host='127.0.0.1', port=8702, workers=1,
                    ssl_certfile=str(args.cert), ssl_keyfile=str(args.key), access_log=False)


if __name__ == '__main__':
    main()
