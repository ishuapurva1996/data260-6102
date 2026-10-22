"""Run a command and retain timestamped, credential-redacted console evidence."""

import argparse
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=True)
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("Supply a command after --")
    secrets = [
        v
        for k, v in os.environ.items()
        if len(v) >= 8
        and any(word in k for word in ("PASSWORD", "SECRET", "DATABASE_URL", "MONGO_URI"))
    ]

    def redact(value):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[JWT REDACTED]", value)

    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a") as log:

        def emit(value):
            value = redact(value)
            print(value, end="", flush=True)
            log.write(value)
            log.flush()

        emit(f"\nPragya Apurva | DATA 260 HW7 | {datetime.now(timezone.utc).isoformat()}\n")
        emit(f"$ {shlex.join(command)}\n")
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=os.environ
        )
        for line in process.stdout:
            emit(line)
        code = process.wait()
        emit(f"exit_code={code} | finished_at={datetime.now(timezone.utc).isoformat()}\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
