#!/usr/bin/env python3
"""Stream the bounded Planner/Reviewer graph through the shared model adapter."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_graph.state import create_initial_state
from src.agent_graph.workflow import build_graph, recursion_limit
from src.model_client import build_ollama_client


class ConfigurationError(ValueError):
    """Invalid CLI input, before model construction or invocation."""


class GraphArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ConfigurationError(message)


def _nonblank(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{name} must be a nonblank string")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = GraphArgumentParser(description=__doc__)
    parser.add_argument("--title")
    parser.add_argument("--content")
    parser.add_argument("--input-json", type=Path, help="JSON object with title, content, and optional email")
    parser.add_argument("--email")
    parser.add_argument("--model", default=os.environ.get("SMOL_MODEL", "qwen3:1.7b"))
    parser.add_argument("--base-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-turns", type=int, default=10, help="Maximum Planner or Reviewer executions")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--controlled-reviewer", action="store_true", help="Append a labeled forced issue to valid real Reviewer responses")
    args = parser.parse_args(argv)
    if args.input_json is not None:
        if args.title is not None or args.content is not None or args.email is not None:
            raise ConfigurationError("--input-json cannot be combined with --title, --content, or --email")
        try:
            data = json.loads(args.input_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"Cannot read input JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigurationError("Input JSON must be an object")
        unknown = sorted(set(data) - {"title", "content", "email"})
        if unknown:
            raise ConfigurationError(f"Unknown input JSON fields: {', '.join(unknown)}")
        args.title = data.get("title")
        args.content = data.get("content")
        args.email = data.get("email")
    args.title = _nonblank(args.title, "title")
    args.content = _nonblank(args.content, "content")
    if args.email is not None:
        args.email = _nonblank(args.email, "email")
    args.model = _nonblank(args.model, "model")
    args.base_url = _nonblank(args.base_url, "base URL")
    try:
        parsed_url = urlparse(args.base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("expected an HTTP(S) URL with a host")
        parsed_url.port
    except ValueError as exc:
        raise ConfigurationError(f"Invalid base URL: {exc}") from exc
    if not math.isfinite(args.temperature) or args.temperature < 0:
        raise ConfigurationError("temperature must be finite and nonnegative")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ConfigurationError("timeout must be finite and positive")
    if args.max_turns <= 0:
        raise ConfigurationError("max-turns must be a positive integer")
    return args


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_metadata() -> dict[str, Any]:
    """Observe the checkout; never change branches, stage files, or commit."""
    result: dict[str, Any] = {"commit": None, "dirty": None}
    try:
        result["commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
            text=True, capture_output=True, timeout=5,
        ).stdout.strip()
        result["dirty"] = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT, check=True,
            text=True, capture_output=True, timeout=5,
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
    return result


def _json_safe(value: Any) -> Any:
    """Remove the runtime-only adapter before constructing any artifact."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items() if key != "llm"}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"Unexpected non-JSON graph value: {type(value).__name__}")


def _stream_event(node: str, update: dict[str, Any]) -> dict[str, Any]:
    event: dict[str, Any] = {"node": node}
    if node in {"planner", "reviewer"} and update.get("trace"):
        event.update(_json_safe(update["trace"][-1]))
    else:
        for key in ("turn_count", "pending_worker_turn", "status", "stop_reason", "error"):
            if key in update:
                event[key] = _json_safe(update[key])
    return event


def _event_text(event: dict[str, Any]) -> str:
    if event["node"] in {"planner", "reviewer"}:
        text = (
            f"{event['node']} attempt={event.get('attempt')} "
            f"revision={event.get('revision')} outcome={event.get('outcome')}"
        )
        if event.get("controlled"):
            text += " controlled_reviewer=true"
        text += "\n  raw=" + json.dumps(event.get("raw"), ensure_ascii=False)
        if event.get("error"):
            text += "\n  error=" + json.dumps(event["error"], ensure_ascii=False)
        return text
    return (
        f"{event['node']} turn_count={event.get('turn_count')} "
        f"status={event.get('status')} stop_reason={event.get('stop_reason')}"
    )


def run_graph(
    args: argparse.Namespace, *, llm: Any = None,
    emit: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute exactly one stream and return terminal JSON-safe run evidence.

    ``args`` comes from :func:`parse_args`. ``llm`` accepts the same adapter
    interface for deterministic tests; normal CLI runs use the shared factory.
    """
    emit = emit or (lambda message: None)
    started_at = _utc_now()
    started = time.perf_counter()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:10]
    git = _git_metadata()
    config = {
        "model": args.model, "base_url": args.base_url,
        "temperature": args.temperature, "timeout": args.timeout,
        "max_turns": args.max_turns, "response_format": "json", "reasoning": False,
        "controlled_reviewer": args.controlled_reviewer,
        "turn_definition": "one Planner or Reviewer execution",
    }
    emit("run=" + run_id + " config=" + json.dumps(config, ensure_ascii=False))
    events: list[dict[str, Any]] = []
    state: dict[str, Any] = {}
    try:
        if llm is None:
            llm = build_ollama_client(
                args.model, args.base_url, args.temperature, args.timeout,
                response_format="json", reasoning=False,
            )
        state = create_initial_state(
            title=args.title, content=args.content, email=args.email, llm=llm,
            max_turns=args.max_turns, controlled_reviewer=args.controlled_reviewer,
        )
        graph = build_graph()
        for mode, payload in graph.stream(
            state, config={"recursion_limit": recursion_limit(args.max_turns)},
            stream_mode=["updates", "values"],
        ):
            if mode == "values":
                state = payload
            elif mode == "updates":
                for node, update in payload.items():
                    if not isinstance(update, dict):
                        raise RuntimeError(f"Unexpected update from {node}")
                    event = _stream_event(node, update)
                    events.append(event)
                    emit(_event_text(event))
        if state.get("status") not in {"accepted", "turn_limit", "error"}:
            raise RuntimeError("Graph ended without a terminal state")
    except Exception as exc:
        state = dict(state)
        state["turn_count"] = state.get("turn_count", 0) + int(bool(state.get("pending_worker_turn")))
        state["pending_worker_turn"] = False
        state["status"] = "error"
        state["stop_reason"] = "Graph execution failed"
        state["error"] = {"kind": "internal_error", "type": type(exc).__name__, "message": str(exc)}
        emit("error=" + json.dumps(state["error"], ensure_ascii=False))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    accepted = state.get("status") == "accepted"
    trace = _json_safe(state.get("trace", []))
    result = {
        "run_id": run_id, "started_at": started_at, "finished_at": _utc_now(),
        "elapsed_ms": elapsed_ms,
        "git": git, "input": {"title": args.title, "content": args.content, "email": args.email},
        "config": config, "controlled_reviewer": args.controlled_reviewer,
        "status": state.get("status", "error"), "stop_reason": state.get("stop_reason"),
        "error": _json_safe(state.get("error")), "turn_count": state.get("turn_count", 0),
        "max_turns": args.max_turns,
        "final_output": _json_safe(state.get("planner_proposal")) if accepted else None,
        "proposal": _json_safe(state.get("planner_proposal")),
        "proposal_revision": state.get("proposal_revision", 0),
        "review": _json_safe(state.get("reviewer_feedback")),
        "reviewed_revision": state.get("reviewed_revision"),
        "feedback": _json_safe(state.get("retry_feedback")),
        "worker_attempts": len(trace),
        "adapter_response_count": state.get("adapter_response_count", 0),
        "input_tokens": state.get("input_tokens", 0), "output_tokens": state.get("output_tokens", 0),
        "total_tokens": state.get("total_tokens", 0),
        "usage_note": "Reported token counts; zero can mean the adapter received no usage metadata.",
        "trace": trace, "events": events,
        "evidence": {"status": "pending" if args.evidence_dir is not None else "not_requested", "requested": args.evidence_dir is not None, "captured": False, "directory": None},
    }
    emit(f"terminal status={result['status']} turn_count={result['turn_count']}/{args.max_turns}")
    return result


def _write_evidence(result: dict[str, Any], destination: Path, stderr_text: str) -> None:
    directory = destination / result["run_id"]
    destination.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        raise FileExistsError(f"Evidence run directory already exists: {directory}")
    result["evidence"] = {"status": "saved", "requested": True, "captured": True, "directory": str(directory.resolve())}
    terminal_json = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    try:
        # Publish the run directory only after every artifact has been written.
        # A partial disk failure must not leave a result claiming capture succeeded.
        with tempfile.TemporaryDirectory(prefix=".part3-pending-", dir=destination) as pending:
            staging = Path(pending)
            events = {"trace": result["trace"], "events": result["events"]}
            (staging / "events.json").write_text(
                json.dumps(events, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            (staging / "stderr.txt").write_text(stderr_text, encoding="utf-8")
            (staging / "stdout.json").write_text(terminal_json, encoding="utf-8")
            (staging / "result.json").write_text(terminal_json, encoding="utf-8")
            staging.rename(directory)
    except OSError:
        result["evidence"]["captured"] = False
        raise


def main(argv: Sequence[str] | None = None) -> int:
    stderr_lines: list[str] = []

    def emit(message: str) -> None:
        print(message, file=sys.stderr, flush=True)
        stderr_lines.append(message + "\n")

    try:
        args = parse_args(argv)
    except ConfigurationError as exc:
        result = {"status": "error", "stop_reason": "Invalid configuration", "error": {"kind": "configuration_error", "message": str(exc)}, "final_output": None, "turn_count": 0}
        emit(f"configuration error: {exc}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    result = run_graph(args, emit=emit)
    if args.evidence_dir is not None:
        try:
            _write_evidence(result, args.evidence_dir, "".join(stderr_lines))
        except (OSError, ValueError, TypeError) as exc:
            result["application_status"] = result["status"]
            result["status"] = "error"
            result["stop_reason"] = "Evidence capture failed"
            result["final_output"] = None
            result["error"] = {"kind": "evidence_error", "type": type(exc).__name__, "message": str(exc)}
            result["evidence"].update({"status": "error", "captured": False, "error": str(exc)})
            emit(f"evidence capture failed: {exc}")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return {"accepted": 0, "turn_limit": 1}.get(result["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
