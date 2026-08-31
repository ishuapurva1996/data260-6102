#!/usr/bin/env python3
"""Command-line demonstration of the reusable model adapter."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.model_client import CumulativeUsage, OllamaModelClient, build_ollama_client


DEFAULT_AGENT_FILE = REPO_ROOT / "AGENT.md"
DEMO_PROMPTS = [
    "Review this Python function for correctness: def average(values): return sum(values) / len(values)",
    "Now focus only on the empty-list edge case.",
    "Suggest one minimal fix without changing the function's purpose.",
    "Review this revision: def average(values): return None if not values else sum(values) / len(values)",
    "Give a final two-bullet assessment covering behavior and readability.",
]


class TeeStream:
    """Mirror text to the terminal and a transcript stream."""

    def __init__(self, terminal: TextIO, transcript: TextIO) -> None:
        self.terminal = terminal
        self.transcript = transcript

    def write(self, text: str) -> int:
        self.terminal.write(text)
        self.transcript.write(text)
        return len(text)

    def flush(self) -> None:
        self.terminal.flush()
        self.transcript.flush()


def is_bullet_only(text: str) -> bool:
    """Return true when every non-empty response line is a Markdown bullet."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("- ") for line in lines)


def conversation_stats(
    history: list[dict[str, str]],
    usage: CumulativeUsage,
) -> dict[str, int]:
    """Build /stats output without changing conversation history."""

    serialized = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    return {
        "turn_count": usage.turn_count,
        "cumulative_input_tokens": usage.input_tokens,
        "cumulative_output_tokens": usage.output_tokens,
        "cumulative_total_tokens": usage.total_tokens,
        "serialized_history_characters": len(serialized),
    }


def print_stats(history: list[dict[str, str]], usage: CumulativeUsage) -> None:
    print("/stats")
    print(json.dumps(conversation_stats(history, usage), indent=2))


def save_output(path: Path, text: str, *, overwrite: bool = False) -> None:
    """Write a complete console transcript without silently replacing evidence."""

    if path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {path}; pass --overwrite to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def save_json_output(path: Path, payload: dict[str, Any], *, overwrite: bool = False) -> None:
    save_output(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        overwrite=overwrite,
    )


def run_turn(
    client: OllamaModelClient,
    system_prompt: str,
    history: list[dict[str, str]],
    user_text: str,
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_text},
    ]
    result = client.complete(messages)
    assistant_text = str(result.content).strip()

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})

    print(f"User: {user_text}")
    print("Assistant:")
    print(assistant_text)
    print(
        "Tokens: "
        f"input={result.usage.input_tokens}, "
        f"output={result.usage.output_tokens}, "
        f"total={result.usage.total_tokens}"
    )
    followed = is_bullet_only(assistant_text)
    print(f"Bullet-only check: {'PASS' if followed else 'FAIL'}")
    return {
        "user": user_text,
        "assistant": assistant_text,
        "tokens": {
            "input": result.usage.input_tokens,
            "output": result.usage.output_tokens,
            "total": result.usage.total_tokens,
        },
        "bullet_only": followed,
    }


def run_demo(
    client: OllamaModelClient,
    system_prompt: str,
    metrics: dict[str, Any] | None = None,
) -> int:
    history: list[dict[str, str]] = []
    all_bullet_only = True
    turn_records: list[dict[str, Any]] = []
    stats_snapshots: dict[str, dict[str, int]] = {}

    for turn, prompt in enumerate(DEMO_PROMPTS, start=1):
        print(f"\n--- Turn {turn} ---")
        record = run_turn(client, system_prompt, history, prompt)
        record["turn"] = turn
        turn_records.append(record)
        all_bullet_only &= record["bullet_only"]
        if turn in {3, 5}:
            print()
            print_stats(history, client.stats)
            stats_snapshots[str(turn)] = conversation_stats(history, client.stats)

    print("\n--- Cumulative usage on exit ---")
    print(
        f"turns={client.stats.turn_count}, "
        f"input_tokens={client.stats.input_tokens}, "
        f"output_tokens={client.stats.output_tokens}, "
        f"total_tokens={client.stats.total_tokens}"
    )
    print(f"AGENT.md bullet-only verification: {'PASS' if all_bullet_only else 'FAIL'}")
    if metrics is not None:
        metrics.update(
            {
                "turns": turn_records,
                "stats_after_turn": stats_snapshots,
                "cumulative": {
                    "turn_count": client.stats.turn_count,
                    "input_tokens": client.stats.input_tokens,
                    "output_tokens": client.stats.output_tokens,
                    "total_tokens": client.stats.total_tokens,
                },
                "bullet_only_verification": all_bullet_only,
            }
        )
    return 0 if all_bullet_only else 1


def run_interactive(client: OllamaModelClient, system_prompt: str) -> int:
    history: list[dict[str, str]] = []
    print("Enter code-review requests. Use /stats for counters and /exit to quit.")

    while True:
        try:
            user_text = input("> ").strip()
        except EOFError:
            user_text = "/exit"

        if not user_text:
            continue
        if user_text == "/stats":
            print_stats(history, client.stats)
            continue
        if user_text in {"/exit", "/quit"}:
            break

        run_turn(client, system_prompt, history, user_text)

    print(
        "Cumulative usage: "
        f"turns={client.stats.turn_count}, "
        f"input_tokens={client.stats.input_tokens}, "
        f"output_tokens={client.stats.output_tokens}, "
        f"total_tokens={client.stats.total_tokens}"
    )
    return 0


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DATA 260 model-client and token demo")
    parser.add_argument("--demo", action="store_true", help="Run the recorded five-turn demo")
    parser.add_argument("--agent-file", type=Path, default=DEFAULT_AGENT_FILE)
    parser.add_argument("--model", default=os.environ.get("SMOL_MODEL", "qwen3:1.7b"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=_positive_float, default=120.0)
    parser.add_argument("--output", type=Path, help="Save the complete console transcript")
    parser.add_argument("--metrics-output", type=Path, help="Save machine-readable token counts")
    parser.add_argument("--overwrite", action="store_true", help="Replace --output if it exists")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if sys.version_info[:2] not in {(3, 11), (3, 12)}:
        print("Error: use Python 3.11 or 3.12 for this assignment.", file=sys.stderr)
        return 2

    try:
        system_prompt = args.agent_file.read_text(encoding="utf-8").strip()
        client = build_ollama_client(
            args.model,
            args.base_url,
            args.temperature,
            args.timeout,
            reasoning=False,
        )
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        metrics: dict[str, Any] = {
            "schema_version": 1,
            "run_timestamp_utc": timestamp,
            "model": args.model,
            "temperature": args.temperature,
        }
        with tempfile.SpooledTemporaryFile(
            mode="w+", encoding="utf-8", max_size=1_000_000
        ) as capture:
            stream = (
                contextlib.redirect_stdout(TeeStream(sys.stdout, capture))
                if args.output
                else contextlib.nullcontext()
            )
            with stream:
                print("DATA 260 HW1 - Part 4 Model Client Demo")
                print(f"Run timestamp (UTC): {timestamp}")
                print(f"Model: {args.model}")
                print(f"Temperature: {args.temperature}")
                status = (
                    run_demo(client, system_prompt, metrics)
                    if args.demo
                    else run_interactive(client, system_prompt)
                )

            if args.output:
                capture.seek(0)
                save_output(args.output, capture.read(), overwrite=args.overwrite)
        if args.metrics_output:
            save_json_output(args.metrics_output, metrics, overwrite=args.overwrite)
        return status
    except Exception as exc:
        print(f"Model client failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
