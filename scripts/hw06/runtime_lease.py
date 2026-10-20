#!/usr/bin/env python3
"""Exclusive local model/app/benchmark lease; lock and owner stay outside Git."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
from uuid import uuid4


class LeaseBusy(RuntimeError):
    pass


class RuntimeLease:
    def __init__(self, runtime_dir: Path | str, *, owner: str, purpose: str):
        self.runtime_dir = Path(runtime_dir).expanduser().resolve()
        self.owner = owner
        self.purpose = purpose
        self.token = None
        self._stream = None

    def acquire(self):
        if self._stream is not None:
            raise RuntimeError("Lease is already acquired by this object")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        stream = (self.runtime_dir / "runtime.lock").open("a+")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stream.close()
            raise LeaseBusy("Shared runtime is leased; inspect external runtime/owner.json") from None
        self._stream = stream
        self.token = uuid4().hex
        owner_file = self.runtime_dir / "owner.json"
        temporary = self.runtime_dir / f".owner-{self.token}.json"
        try:
            temporary.write_text(json.dumps({
                "owner": self.owner, "purpose": self.purpose, "pid": os.getpid(),
                "host": socket.gethostname(), "token": self.token,
                "acquired_at": datetime.now(timezone.utc).isoformat(),
            }, indent=2) + "\n")
            temporary.chmod(0o600)
            temporary.replace(owner_file)
        except BaseException:
            temporary.unlink(missing_ok=True)
            self.release()
            raise
        return self

    def release(self):
        if self._stream is None:
            return
        try:
            owner_file = self.runtime_dir / "owner.json"
            try:
                if json.loads(owner_file.read_text()).get("token") == self.token:
                    owner_file.unlink()
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        finally:
            fcntl.flock(self._stream, fcntl.LOCK_UN)
            self._stream.close()
            self._stream = None
            self.token = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Supply a command after --")
    try:
        with RuntimeLease(args.runtime_dir, owner=args.owner, purpose=args.purpose):
            return subprocess.call(command)
    except LeaseBusy as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
