#!/usr/bin/env python3
"""Run the DATA 260 Part 3 temperature experiment with checkpointed output."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from code import agents_demo  # noqa: E402  (shared application import)


DEFAULT_CASE = HERE / "cases" / "nondeterminism_input.json"
DEFAULT_OUTPUT = HERE / "raw" / "nondeterminism_runs.json"
CHECKPOINT_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def percentile(values: Sequence[float], percent: float) -> float | None:
    """Return a linearly interpolated percentile, or None for no values."""

    return percentile_from_ordered(sorted(values), percent)


def percentile_from_ordered(
    ordered: Sequence[float],
    percent: float,
) -> float | None:
    """Return a percentile from values already ordered from low to high."""

    if not ordered:
        return None
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 2)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)


def summarize_runs(runs: Iterable[Dict[str, Any]], requested: int) -> Dict[str, Any]:
    run_list = list(runs)
    successful = [run for run in run_list if run.get("status") == "ok"]
    tag_sets = {tuple(sorted(run["tags"])) for run in successful}
    tag_counts = Counter(tag for run in successful for tag in set(run["tags"]))
    latencies = sorted(run["latency_ms"]["total"] for run in successful)
    success_count = len(successful)

    return {
        "runs_requested": requested,
        "attempts": len(run_list),
        "successful_runs": success_count,
        "failed_attempts": len(run_list) - success_count,
        "distinct_tag_sets": len(tag_sets),
        "tags_in_all_successful_runs": sorted(
            tag for tag, count in tag_counts.items() if count == success_count
        )
        if success_count
        else [],
        "tags_in_exactly_one_run": sorted(
            tag for tag, count in tag_counts.items() if count == 1
        ),
        "latency_ms": {
            "p50": percentile_from_ordered(latencies, 50),
            "p95": percentile_from_ordered(latencies, 95),
            "p99": percentile_from_ordered(latencies, 99),
        },
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def load_case(path: Path) -> Dict[str, str]:
    case = json.loads(path.read_text())
    for field in ("title", "content"):
        if not isinstance(case.get(field), str) or not case[field].strip():
            raise ValueError(f"Case field '{field}' must be a non-empty string")
    email = case.get("email", "student@example.com")
    if not isinstance(email, str):
        raise ValueError("Case field 'email' must be a string when provided")
    return {"title": case["title"], "content": case["content"], "email": email}


def initial_payload(
    case: Dict[str, str],
    model_name: str,
    base_url: str,
    temperatures: Sequence[float],
    count: int,
    timeout: float,
) -> Dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "experiment": "DATA 260 HW1 Part 3 - Measuring Non-Determinism",
        "started_at": utc_now(),
        "completed_at": None,
        "status": "running",
        "model": model_name,
        "base_url": base_url,
        "timeout": timeout,
        "runs_per_temperature": count,
        "temperature_order": list(temperatures),
        "input": case,
        "runs": {str(temperature): [] for temperature in temperatures},
        "metrics": {},
    }


def _checkpoint_identity(
    case: Dict[str, str],
    model_name: str,
    base_url: str,
    temperatures: Sequence[float],
    count: int,
    timeout: float,
) -> Dict[str, Any]:
    """Return the configuration fields that define checkpoint compatibility."""

    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "model": model_name,
        "base_url": base_url,
        "timeout": timeout,
        "runs_per_temperature": count,
        "temperature_order": list(temperatures),
        "input": case,
    }


def _validate_checkpoint_identity(
    payload: Dict[str, Any],
    expected: Dict[str, Any],
) -> None:
    observed = {field: payload.get(field) for field in expected}
    if observed != expected:
        raise ValueError("Existing checkpoint configuration does not match this run")


def _validate_successful_record(record: Dict[str, Any], key: str) -> None:
    tags = record.get("tags")
    if (
        not isinstance(tags, list)
        or len(tags) != 3
        or any(not isinstance(tag, str) or not tag.strip() for tag in tags)
        or len(set(tags)) != 3
    ):
        raise ValueError(f"Completed checkpoint {key} contains invalid tags")

    summary = record.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary.split()) > 25:
        raise ValueError(f"Completed checkpoint {key} contains an invalid summary")

    latency = record.get("latency_ms")
    if not isinstance(latency, dict) or not isinstance(latency.get("total"), (int, float)):
        raise ValueError(f"Completed checkpoint {key} contains invalid latency data")


def validate_completed_checkpoint(
    payload: Dict[str, Any],
    temperatures: Sequence[float],
    count: int,
) -> None:
    """Reject a completed checkpoint unless its records and metrics are exact."""

    runs = payload.get("runs")
    if not isinstance(runs, dict):
        raise ValueError("Completed checkpoint is missing run records")
    expected_keys = {str(temperature) for temperature in temperatures}
    if set(runs) != expected_keys:
        raise ValueError("Completed checkpoint temperature records do not match this run")

    recomputed_metrics: Dict[str, Any] = {}
    for temperature in temperatures:
        key = str(temperature)
        records = runs.get(key)
        if not isinstance(records, list):
            raise ValueError(f"Completed checkpoint is missing runs for {key}")
        if any(not isinstance(record, dict) for record in records):
            raise ValueError(f"Completed checkpoint {key} contains a malformed record")
        if [record.get("attempt") for record in records] != list(
            range(1, len(records) + 1)
        ):
            raise ValueError(f"Completed checkpoint {key} has non-contiguous attempts")
        if any(record.get("status") not in {"ok", "error", "interrupted"} for record in records):
            raise ValueError(f"Completed checkpoint {key} contains an invalid status")

        successful = [record for record in records if record.get("status") == "ok"]
        if len(successful) != count:
            raise ValueError(
                f"Completed checkpoint {key} must contain exactly {count} successful runs"
            )
        if [record.get("run") for record in successful] != list(range(1, count + 1)):
            raise ValueError(f"Completed checkpoint {key} has non-contiguous run numbers")
        for record in successful:
            _validate_successful_record(record, key)
        recomputed_metrics[key] = summarize_runs(records, count)

    if payload.get("metrics") != recomputed_metrics:
        raise ValueError("Completed checkpoint metrics do not match its run records")


def _convert_stale_running_records(payload: Dict[str, Any]) -> bool:
    """Mark attempts left in flight by a stopped process as interrupted."""

    changed = False
    runs = payload.get("runs", {})
    if not isinstance(runs, dict):
        return False
    for key, records in runs.items():
        if not isinstance(records, list):
            continue
        key_changed = False
        for index, record in enumerate(records):
            if record.get("status") != "running":
                continue
            interrupted = dict(record)
            interrupted.update(
                {
                    "status": "interrupted",
                    "error": "Interrupted before the attempt completed",
                }
            )
            records[index] = interrupted
            changed = True
            key_changed = True
        if key_changed:
            payload.setdefault("metrics", {})[key] = summarize_runs(
                records,
                payload["runs_per_temperature"],
            )
    return changed


def run_experiment(
    case_path: Path,
    output_path: Path,
    model_name: str,
    base_url: str,
    temperatures: Sequence[float],
    count: int,
    timeout: float,
    max_errors: int,
    resume: bool,
    overwrite: bool = False,
) -> Dict[str, Any]:
    case = load_case(case_path)
    if resume and overwrite:
        raise ValueError("resume and overwrite cannot be used together")
    if not resume and output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}. Use --overwrite to replace it."
        )

    expected_identity = _checkpoint_identity(
        case,
        model_name,
        base_url,
        temperatures,
        count,
        timeout,
    )
    payload = None
    if resume:
        try:
            payload = json.loads(output_path.read_text())
        except FileNotFoundError:
            pass
    if payload is not None:
        _validate_checkpoint_identity(payload, expected_identity)
        if _convert_stale_running_records(payload):
            payload["status"] = "running"
            payload["completed_at"] = None
            write_json(output_path, payload)
        if payload.get("status") == "complete":
            validate_completed_checkpoint(payload, temperatures, count)
            return payload
    else:
        payload = initial_payload(
            case,
            model_name,
            base_url,
            temperatures,
            count,
            timeout,
        )
        write_json(output_path, payload)

    for temperature in temperatures:
        key = str(temperature)
        records: List[Dict[str, Any]] = payload["runs"].setdefault(key, [])
        successes = sum(record.get("status") == "ok" for record in records)
        errors = sum(record.get("status") == "error" for record in records)
        if successes >= count:
            continue
        model = agents_demo.create_model(model_name, base_url, temperature, timeout)

        while successes < count:
            if errors >= max_errors:
                payload["status"] = "failed"
                payload["completed_at"] = utc_now()
                payload["metrics"][key] = summarize_runs(records, count)
                write_json(output_path, payload)
                raise RuntimeError(
                    f"Temperature {temperature} reached {max_errors} failed attempts "
                    f"before completing {count} successful runs"
                )
            attempt = len(records) + 1
            started_at = utc_now()
            records.append(
                {
                    "attempt": attempt,
                    "status": "running",
                    "started_at": started_at,
                }
            )
            payload["status"] = "running"
            payload["completed_at"] = None
            payload["metrics"][key] = summarize_runs(records, count)
            write_json(output_path, payload)
            started = time.perf_counter()
            try:
                result = agents_demo.run_pipeline(
                    model=model,
                    title=case["title"],
                    content=case["content"],
                    email=case["email"],
                )
            except KeyboardInterrupt:
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                records[-1] = {
                    "attempt": attempt,
                    "status": "interrupted",
                    "started_at": started_at,
                    "elapsed_ms": elapsed_ms,
                    "error": "KeyboardInterrupt: experiment interrupted",
                }
                payload["status"] = "interrupted"
                payload["metrics"][key] = summarize_runs(records, count)
                write_json(output_path, payload)
                raise
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                errors += 1
                record = {
                    "attempt": attempt,
                    "status": "error",
                    "started_at": started_at,
                    "elapsed_ms": elapsed_ms,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                print(
                    f"temp={temperature} attempt={attempt} ERROR "
                    f"elapsed_ms={elapsed_ms}: {exc}",
                    flush=True,
                )
            else:
                successes += 1
                latency = result["latency_ms"]
                record = {
                    "attempt": attempt,
                    "run": successes,
                    "status": "ok",
                    "started_at": started_at,
                    "tags": result["finalized"]["data"]["tags"],
                    "summary": result["finalized"]["data"]["summary"],
                    "reviewer_changed": result["reviewer_changed"],
                    "latency_ms": {
                        "planner": latency["planner"],
                        "reviewer": latency["reviewer"],
                        "total": latency["planner"] + latency["reviewer"],
                    },
                }
                print(
                    f"temp={temperature} run={successes}/{count} "
                    f"latency_ms={record['latency_ms']['total']} "
                    f"tags={json.dumps(record['tags'], ensure_ascii=False)}",
                    flush=True,
                )
            records[-1] = record
            payload["metrics"][key] = summarize_runs(records, count)
            write_json(output_path, payload)

    payload["status"] = "complete"
    payload["completed_at"] = utc_now()
    validate_completed_checkpoint(payload, temperatures, count)
    write_json(output_path, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=os.environ.get("SMOL_MODEL", "qwen3:1.7b"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    )
    parser.add_argument("--temperatures", nargs="+", type=float, default=[0.7, 0.0])
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-errors", type=int, default=10)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.count <= 0 or args.timeout <= 0 or args.max_errors <= 0:
        print("count, timeout, and max-errors must be greater than zero", file=sys.stderr)
        return 2
    try:
        payload = run_experiment(
            case_path=args.case,
            output_path=args.output,
            model_name=args.model,
            base_url=args.base_url,
            temperatures=args.temperatures,
            count=args.count,
            timeout=args.timeout,
            max_errors=args.max_errors,
            resume=args.resume,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"Experiment failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload["metrics"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
