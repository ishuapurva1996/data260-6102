"""Independent raw-record audit: no imports from the experiment implementation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys


def audit(directory):
    rows_path = directory / "rows.jsonl"
    rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
    manifest = json.loads((directory / "manifest.json").read_text())
    saved = json.loads((directory / "metrics.json").read_text())
    assert len(rows) == 150 and len(saved) == 3
    assert manifest["seed"] == 266102
    assert manifest["policy"] == {"max_attempts": 3, "initial_backoff_s": 0.1,
                                   "backoff_multiplier": 2.0, "max_backoff_s": 0.2}
    assert manifest["fixture_sha256"] == hashlib.sha256(json.dumps(
        manifest["fixture"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert manifest["artifacts_sha256"]["rows.jsonl"] == hashlib.sha256(rows_path.read_bytes()).hexdigest()
    metrics = []
    for rate, expected in zip((0.0, 0.2, 0.5), saved, strict=True):
        group = [row for row in rows if row["rate"] == rate]
        assert len(group) == 50
        assert [row["logical_index"] for row in group] == list(range(1, 51))
        assert Counter(row["tool"] for row in group) == {
            "search_rentals": 17, "get_rental": 17, "count_rentals": 16}
        rng = random.Random(266102)
        for row in group:
            cycle = manifest["call_cycle"][(row["logical_index"] - 1) % 3]
            assert row["tool"] == cycle["tool"] and row["inputs"] == cycle["inputs"]
            assert row["attempt_count"] == len(row["trace"]) <= 3
            for number, event in enumerate(row["trace"], 1):
                draw = rng.random()
                injected = draw < rate
                assert event["draw"] == draw and event["injected"] is injected
                assert event["attempt"] == number and event["operation"] == row["tool"]
                assert event["outcome"] == ("transient_error" if injected else "success")
                assert event["sleep_s"] == (0.1 * number if injected and number < 3 else 0)
                if not injected:
                    assert number == row["attempt_count"]
            ok = not row["trace"][-1]["injected"]
            assert row["envelope"]["ok"] is ok
            if not ok:
                assert row["attempt_count"] == 3
                assert row["envelope"] == {"ok": False, "data": None,
                                            "error": "Rental data is temporarily unavailable."}
            else:
                assert row["envelope"]["error"] is None and row["envelope"]["data"] is not None
            assert math.isfinite(row["elapsed_ms"]) and row["elapsed_ms"] >= 0
        durations = [row["elapsed_ms"] for row in group]
        successes = sum(row["envelope"]["ok"] for row in group)
        computed = {"rate": rate, "logical_calls": 50, "successes": successes,
                    "success_rate": successes / 50, "mean_latency_ms": statistics.fmean(durations),
                    "p99_latency_ms": max(durations),
                    "total_attempts": sum(row["attempt_count"] for row in group),
                    "first_attempt_successes": sum(not row["trace"][0]["injected"] for row in group),
                    "recovered_calls": sum(row["envelope"]["ok"] and row["attempt_count"] > 1 for row in group)}
        for key in ("rate", "logical_calls", "successes", "success_rate", "p99_latency_ms",
                    "total_attempts", "recovered_calls"):
            assert computed[key] == expected[key]
        assert math.isclose(computed["mean_latency_ms"], expected["mean_latency_ms"], rel_tol=1e-12)
        metrics.append(computed)
    return {"student": "Pragya Apurva", "passed": True, "rows_checked": len(rows),
            "verified_utc": datetime.now(timezone.utc).isoformat(),
            "rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
            "independent_method": "Standalone standard-library audit; fmean over all 50 durations and max for nearest-rank p99; rebuild every RNG draw.",
            "metrics": metrics}


def main():
    if not __debug__:
        print("Recomputation requires enabled assertions.", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = audit(args.selected_dir)
        receipt["command"] = [sys.executable, *sys.argv]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as output:
            json.dump(receipt, output, indent=2, allow_nan=False)
            output.write("\n")
    except Exception:
        print("Independent raw-record audit FAILED; no passing receipt produced.", file=sys.stderr)
        return 1
    print("Pragya Apurva — independent raw-record audit PASS: 150 rows, every RNG decision, and all 3 metrics rows.")
    for metric in receipt["metrics"]:
        print(f"{metric['rate']:.0%}: {metric['successes']}/50; mean={metric['mean_latency_ms']:.6f} ms; "
              f"p99={metric['p99_latency_ms']:.6f} ms; attempts={metric['total_attempts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
