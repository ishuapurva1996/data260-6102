"""Three explicitly scripted outcomes, separate from the seeded experiment."""
import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from src.rental_tools.registry import TOOL_REGISTRY
from src.rental_tools.reliability import InjectedTransientError, RetryPolicy

from .fixture import FixtureReader, fixture_sha256
from .provenance import provenance, sha256_file, utc_now
from .run_fault_experiment import fixture_service, write_json


class ScriptedReader(FixtureReader):
    def __init__(self, failures):
        self.failures = iter(failures)
        self.decisions = []

    def get_rental(self, rental_id):
        injected = next(self.failures)
        self.decisions.append({"injected": injected})
        if injected:
            raise InjectedTransientError("Scripted fixture failure.")
        return super().get_rental(rental_id)


def run_demos(*, _sleep=None, _clock=time.perf_counter):
    demonstrations = []
    for name, failures in (
        ("immediate_success", (False,)),
        ("transient_then_success", (True, False)),
        ("retry_exhaustion", (True, True, True)),
    ):
        reader, trace = ScriptedReader(failures), []

        def observe(event):
            trace.append({**reader.decisions[-1], **event})

        service = fixture_service(reader, RetryPolicy(), observe, _sleep)
        try:
            started = _clock()
            envelope = TOOL_REGISTRY["get_rental"].handler(service, rental_id=1)
            elapsed_ms = (_clock() - started) * 1000
            if len(trace) != len(failures):
                raise RuntimeError("Incomplete scripted attempt observation.")
            demonstrations.append({
                "name": name, "scripted_injections": list(failures), "tool": "get_rental",
                "inputs": {"rental_id": 1}, "envelope": envelope, "elapsed_ms": elapsed_ms,
                "attempt_count": len(trace), "trace": trace,
            })
        finally:
            service.reader.close()
    return demonstrations


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output_dir.exists():
            raise FileExistsError("Output directory already exists; choose a fresh explicit path.")
        manifest = {
            "schema_version": 1, "student": "Pragya Apurva",
            "evidence_kind": "three scripted fixture demonstrations; real sleeps and elapsed time",
            "started_at_utc": utc_now(), "policy": asdict(RetryPolicy()),
            "fixture_sha256": fixture_sha256(),
            **provenance("scripts.hw05.part3.run_retry_demos", argv),
        }
        args.output_dir.mkdir(parents=True, exist_ok=False)
        demos = run_demos()
        result_path = args.output_dir / "demonstrations.json"
        write_json(result_path, demos)
        manifest["completed_at_utc"] = utc_now()
        manifest["artifacts_sha256"] = {result_path.name: sha256_file(result_path)}
        write_json(args.output_dir / "manifest.json", manifest)
        print("Pragya Apurva — Part 3 explicitly scripted retry demonstrations")
        for demo in demos:
            sleeps = [event["sleep_s"] for event in demo["trace"] if event["sleep_s"]]
            print(f"{demo['name']}: ok={demo['envelope']['ok']} attempts={demo['attempt_count']} "
                  f"sleeps={sleeps} elapsed_ms={demo['elapsed_ms']:.6f}")
            print("  envelope=" + json.dumps(demo["envelope"], sort_keys=True))
            print("  trace=" + json.dumps([
                {key: event[key] for key in ("attempt", "injected", "outcome", "sleep_s")}
                for event in demo["trace"]
            ], sort_keys=True))
        print(f"Evidence: {args.output_dir.resolve()}")
        return 0
    except (OSError, ValueError) as error:
        print(f"Demonstrations could not complete: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
