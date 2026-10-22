"""Required append-only JSONL logging without dependency exception disclosure."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


class AgentLogError(RuntimeError):
    """A run cannot claim success when its required evidence cannot be saved."""


class RunLogger:
    def __init__(self, run_id: str, *, stream: TextIO | None, path: str | Path | None):
        if stream is not None and path is not None:
            raise ValueError("Choose log_stream or log_path, not both.")
        self.run_id = run_id
        self.sequence = 0
        self.owned = stream is None
        try:
            if stream is None:
                destination = (
                    Path(path)
                    if path is not None
                    else (
                        Path.home()
                        / "code/agent_outputs/data260-hw5/agent-runs"
                        / f"{run_id}.jsonl"
                    )
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                stream = destination.open("a", encoding="utf-8")
            self.stream = stream
        except Exception:
            raise AgentLogError("Agent log could not be opened.") from None

    def emit(self, event: str, **fields: Any) -> None:
        record = {
            "run_id": self.run_id,
            "sequence": self.sequence + 1,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        try:
            line = json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
            written = self.stream.write(line)
            if written != len(line):
                raise OSError("short write")
            self.stream.flush()
        except Exception:
            raise AgentLogError("Agent log could not be written.") from None
        self.sequence += 1

    def close(self) -> None:
        if self.owned:
            try:
                self.stream.close()
            except Exception:
                raise AgentLogError("Agent log could not be closed.") from None
