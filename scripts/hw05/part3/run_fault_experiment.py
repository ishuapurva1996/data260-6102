"""Measure a fixed 150-call fixture experiment with real retry sleeps by default.

Run from the repository root using ``python -m scripts.hw05.part3.run_fault_experiment``.
Each invocation requires a fresh output directory; replay output is retained separately.
The underscored sleep/clock hooks exist only for fast deterministic unit tests.
"""
import argparse
import json
import math
import random
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from types import MappingProxyType

from src.rental_tools.registry import TOOL_REGISTRY
from src.rental_tools.reliability import InjectedTransientError, RetryPolicy, RetryingRentalReader
from src.rental_tools.runtime import build_service

from .fixture import FixtureReader, fixture_payload, fixture_sha256
from .provenance import provenance, sha256_file, utc_now


VERIFY_SEED = 266102
RATES = (0.0, 0.2, 0.5)
CALLS_PER_RATE = 50
CALL_CYCLE = (
    ("search_rentals", MappingProxyType({"query": "campus", "limit": 5})),
    ("get_rental", MappingProxyType({"rental_id": 1})),
    ("count_rentals", MappingProxyType({"manager_id": 1})),
)


class FaultInjectingReader(FixtureReader):
    """Draw exactly once before each attempted fixture read, including rate zero."""

    def __init__(self, rate, seed):
        if type(rate) not in (float, int) or not math.isfinite(rate) or not 0 <= rate <= 1:
            raise ValueError("rate must be a finite number from 0 to 1.")
        if type(seed) is not int or seed < 0:
            raise ValueError("seed must be a nonnegative integer.")
        self.rate = rate
        self.rng = random.Random(seed)
        self.decisions = []

    def _inject(self, operation):
        draw = self.rng.random()
        injected = draw < self.rate
        self.decisions.append({"operation": operation, "draw": draw, "injected": injected})
        if injected:
            raise InjectedTransientError("Controlled fixture failure.")

    def search_rentals(self, query, limit):
        self._inject("search_rentals")
        return super().search_rentals(query, limit)

    def get_rental(self, rental_id):
        self._inject("get_rental")
        return super().get_rental(rental_id)

    def count_rentals(self, manager_id):
        self._inject("count_rentals")
        return super().count_rentals(manager_id)


def fixture_service(reader, policy, observer, _sleep=None):
    """Use the production factory; only unit tests may replace retry sleeping."""
    if _sleep is None:
        return build_service(reader=reader, policy=policy, attempt_observer=observer)
    wrapped = RetryingRentalReader(reader, policy, observer, sleep=_sleep)
    return build_service(reader=wrapped)


def run_rate(rate, *, seed=VERIFY_SEED, policy=None, run_id=None,
             _sleep=None, _clock=time.perf_counter):
    policy = policy if policy is not None else RetryPolicy()
    if not isinstance(policy, RetryPolicy):
        raise TypeError("policy must be a RetryPolicy.")
    reader = FaultInjectingReader(rate, seed)
    run_id = run_id if run_id is not None else str(uuid.uuid4())
    trace = []

    def observe(event):
        trace.append({**reader.decisions[-1], **event})

    service = fixture_service(reader, policy, observe, _sleep)
    rows = []
    try:
        for logical_index in range(1, CALLS_PER_RATE + 1):
            tool, frozen_inputs = CALL_CYCLE[(logical_index - 1) % len(CALL_CYCLE)]
            inputs = dict(frozen_inputs)
            reader.decisions.clear()
            trace.clear()
            started = _clock()
            envelope = TOOL_REGISTRY[tool].handler(service, **inputs)
            elapsed_ms = (_clock() - started) * 1000
            if not trace or len(trace) != len(reader.decisions):
                raise RuntimeError("Incomplete controlled attempt observation.")
            rows.append({
                "run_id": run_id, "rate": float(rate), "logical_index": logical_index,
                "tool": tool, "inputs": inputs, "envelope": envelope,
                "elapsed_ms": elapsed_ms, "attempt_count": len(trace),
                "trace": [dict(event) for event in trace],
            })
    finally:
        service.reader.close()
    return rows


def run_experiment(*, seed=VERIFY_SEED, policy=None, run_id=None,
                   _sleep=None, _clock=time.perf_counter):
    """Exactly 50 calls per rate, with a new local seeded RNG for each rate."""
    run_id = run_id if run_id is not None else str(uuid.uuid4())
    return [row for rate in RATES for row in run_rate(
        rate, seed=seed, policy=policy, run_id=run_id, _sleep=_sleep, _clock=_clock,
    )]


def validate_rows(rows):
    if len(rows) != len(RATES) * CALLS_PER_RATE:
        raise ValueError("A selected experiment must contain exactly 150 logical-call rows.")
    for rate_index, rate in enumerate(RATES):
        for logical_index in range(1, CALLS_PER_RATE + 1):
            row = rows[rate_index * CALLS_PER_RATE + logical_index - 1]
            tool, inputs = CALL_CYCLE[(logical_index - 1) % len(CALL_CYCLE)]
            if (row["rate"] != rate or row["logical_index"] != logical_index
                    or row["tool"] != tool or row["inputs"] != inputs):
                raise ValueError("Rows must preserve the fixed rates and search/detail/count call order.")
            duration = row["elapsed_ms"]
            if type(duration) not in (float, int) or not math.isfinite(duration) or duration < 0:
                raise ValueError("Each duration must be a finite nonnegative number.")
            if type(row["envelope"]["ok"]) is not bool:
                raise ValueError("Each envelope must have a Boolean ok value.")
            if (type(row["attempt_count"]) is not int or row["attempt_count"] < 1
                    or row["attempt_count"] != len(row["trace"])):
                raise ValueError("Each row must retain every observed attempt.")


def derive_metrics(rows):
    """Recompute solely from raw rows; failed-call durations remain in both statistics."""
    validate_rows(rows)
    metrics = []
    for rate in RATES:
        group = [row for row in rows if row["rate"] == rate]
        durations = sorted(row["elapsed_ms"] for row in group)
        successes = sum(row["envelope"]["ok"] for row in group)
        metrics.append({
            "rate": rate, "logical_calls": CALLS_PER_RATE, "successes": successes,
            "success_rate": successes / CALLS_PER_RATE,
            "mean_latency_ms": math.fsum(durations) / CALLS_PER_RATE,
            "p99_latency_ms": durations[math.ceil(0.99 * CALLS_PER_RATE) - 1],
            "maximum_latency_ms": durations[-1],
            "total_attempts": sum(row["attempt_count"] for row in group),
            "injected_attempts": sum(event["injected"] for row in group for event in row["trace"]),
            "recovered_calls": sum(row["envelope"]["ok"] and row["attempt_count"] > 1 for row in group),
        })
    return metrics


def deterministic_projection(rows):
    """Retain decisions/outcomes/backoff; omit UUIDs, timestamps and elapsed times."""
    validate_rows(rows)
    return [{
        **{key: row[key] for key in ("rate", "logical_index", "tool", "inputs", "envelope", "attempt_count")},
        "trace": [{key: event[key] for key in ("operation", "attempt", "draw", "injected", "outcome", "sleep_s")}
                  for event in row["trace"]],
    } for row in rows]


def compare_replay(selected, replay):
    expected, actual = deterministic_projection(selected), deterministic_projection(replay)
    mismatches = [index + 1 for index, pair in enumerate(zip(expected, actual)) if pair[0] != pair[1]]
    return {
        "matched": not mismatches, "logical_calls_compared": len(expected),
        "mismatched_row_numbers": mismatches,
        "compared": "rate, call order, inputs, envelopes, attempts, RNG draws, injection, outcomes, backoff",
        "excluded": "run IDs, UTC timestamps, logical-call and attempt elapsed times",
    }


def read_rows(path):
    with Path(path).open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as destination:
        destination.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--label", choices=("selected", "replay", "diagnostic"), required=True)
    parser.add_argument("--compare-to", type=Path, help="Selected rows.jsonl; required for replay.")
    args = parser.parse_args(argv)
    if (args.label == "replay") != (args.compare_to is not None):
        parser.error("--compare-to must be supplied exactly when --label is replay.")
    try:
        if args.output_dir.exists():
            raise FileExistsError("Output directory already exists; choose a fresh explicit path.")
        selected = read_rows(args.compare_to) if args.compare_to is not None else None
        if selected is not None:
            validate_rows(selected)
        policy = RetryPolicy()
        manifest = {
            "schema_version": 1, "run_id": str(uuid.uuid4()), "label": args.label,
            "student": "Pragya Apurva", "evidence_kind": "controlled immutable fixture; real sleeps and elapsed time",
            "started_at_utc": utc_now(), "seed": VERIFY_SEED, "rates": list(RATES),
            "calls_per_rate": CALLS_PER_RATE, "policy": asdict(policy),
            "fixture": fixture_payload(), "fixture_sha256": fixture_sha256(),
            "call_cycle": [{"tool": tool, "inputs": dict(inputs)} for tool, inputs in CALL_CYCLE],
            "rng_rule": "New random.Random(seed) per rate; one draw per storage attempt including rate zero; inject iff draw < rate.",
            "latency_rule": "perf_counter around each full service call, including failures and real retry sleeps.",
            "p99_rule": "Nearest rank ceil(0.99 * 50), therefore maximum of all 50 durations.",
            **provenance("scripts.hw05.part3.run_fault_experiment", argv),
        }
        args.output_dir.mkdir(parents=True, exist_ok=False)
        rows = run_experiment(policy=policy, run_id=manifest["run_id"])
        rows_path = args.output_dir / "rows.jsonl"
        with rows_path.open("x", encoding="utf-8") as destination:
            for row in rows:
                destination.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        # Re-read persisted raw rows before calculating any summary or replay result.
        saved_rows = read_rows(rows_path)
        metrics = derive_metrics(saved_rows)
        write_json(args.output_dir / "metrics.json", metrics)
        matched = True
        if selected is not None:
            receipt = compare_replay(selected, saved_rows)
            receipt["selected_rows_path"] = str(args.compare_to.resolve())
            receipt["selected_rows_sha256"] = sha256_file(args.compare_to)
            write_json(args.output_dir / "replay-comparison.json", receipt)
            matched = receipt["matched"]
        manifest["completed_at_utc"] = utc_now()
        manifest["artifacts_sha256"] = {
            path.name: sha256_file(path) for path in sorted(args.output_dir.iterdir()) if path.is_file()
        }
        write_json(args.output_dir / "manifest.json", manifest)
        print("Pragya Apurva — Part 3 controlled fixture experiment")
        print(f"Label: {args.label}; 150 logical calls; seed {VERIFY_SEED}; real retry sleeps")
        for metric in metrics:
            print(f"rate={metric['rate']:.0%} successes={metric['successes']}/50 "
                  f"mean_ms={metric['mean_latency_ms']:.6f} p99_ms={metric['p99_latency_ms']:.6f} "
                  f"attempts={metric['total_attempts']}")
        if selected is not None:
            print(f"Deterministic replay: {'PASS' if matched else 'FAIL'}")
        print(f"Evidence: {args.output_dir.resolve()}")
        return 0 if matched else 1
    except (OSError, ValueError, KeyError) as error:
        print(f"Experiment could not complete: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
