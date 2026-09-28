#!/usr/bin/env python3
"""Validate and summarize the selected HW4 Part 3 HTTP measurement attempt."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


SIZES = (10, 50, 200)
VERSIONS = ("naive", "fixed")
REPETITIONS = 30
PERCENTILE_METHOD = "R7 linear interpolation: rank=(n-1)*p, interpolate adjacent sorted values"


def percentile(values, probability):
    """Compute the R7/NumPy-default percentile without an extra dependency."""
    if not values or not 0 <= probability <= 1:
        raise ValueError("A percentile needs samples and a probability between zero and one")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * probability
    lower = math.floor(rank)
    upper = math.ceil(rank)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _sha(value, length):
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def validate_rows(rows):
    """Fail closed: partial, mixed, duplicated or invalid attempts are not evidence."""
    if len(rows) != len(SIZES) * len(VERSIONS) * REPETITIONS:
        raise ValueError("A selected attempt must contain exactly 180 measured requests")
    expected_order = [(size, iteration, version) for size in SIZES
                      for iteration in range(1, REPETITIONS + 1) for version in VERSIONS]
    common = None
    payloads = {}
    for index, (row, expected) in enumerate(zip(rows, expected_order), 1):
        if not isinstance(row, dict):
            raise ValueError(f"Row {index}: expected an object")
        try:
            size, iteration, version = row["page_size"], row["iteration"], row["version"]
            if row["phase"] != "measured":
                raise ValueError("only measured requests belong in the selected raw dataset")
            if (size, iteration, version) != expected or not _integer(size, 1) or not _integer(iteration, 1):
                raise ValueError("requests must be serial, ordered by size, iteration, then naive/fixed")
            if row["valid"] is not True or row.get("error") is not None or row["http_status"] != 200:
                raise ValueError("unsuccessful request")
            if type(row["http_status"]) is not int or not _integer(row["returned_count"], 1) or row["returned_count"] != size:
                raise ValueError("wrong status or returned count")
            elapsed = row["elapsed_ms"]
            if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed <= 0:
                raise ValueError("elapsed_ms must be a finite positive number")
            if not _integer(row["total_sql"], 1) or not _integer(row["data_sql"], 1):
                raise ValueError("SQL counters must be actual positive integers")
            if row["total_sql"] <= row["data_sql"]:
                raise ValueError("total SQL must include authentication work in addition to data SQL")
            expected_data = size + 1 if version == "naive" else 1
            if row["data_sql"] != expected_data:
                raise ValueError("observed data SQL does not demonstrate the required query strategy")
            if not _sha(row["payload_sha256"], 64) or not _sha(row["config_sha256"], 64):
                raise ValueError("invalid payload/config SHA-256")
            if not _sha(row["code_revision"], 40) or type(row["dirty"]) is not bool:
                raise ValueError("invalid measured revision or dirty state")
            if not isinstance(row["run_id"], str) or not row["run_id"]:
                raise ValueError("missing run ID")
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("timestamp needs a timezone")
            identity = (row["run_id"], row["code_revision"], row["dirty"], row["config_sha256"])
            if common is None:
                common = identity
            if identity != common:
                raise ValueError("rows mix attempts, revisions or configurations")
            if size in payloads and payloads[size] != row["payload_sha256"]:
                raise ValueError("payload changed between requests or query versions")
            payloads[size] = row["payload_sha256"]
        except (KeyError, TypeError, AttributeError, ValueError) as error:
            raise ValueError(f"Row {index}: {error}") from error


def summarize_rows(rows):
    validate_rows(rows)
    groups = []
    for size in SIZES:
        for version in VERSIONS:
            samples = [row for row in rows if row["page_size"] == size and row["version"] == version]
            latencies = [row["elapsed_ms"] for row in samples]
            group = {"page_size": size, "version": version, "samples": len(samples)}
            for name, probability in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
                group[f"{name}_ms"] = percentile(latencies, probability)
            for counter in ("total_sql", "data_sql"):
                observed = [row[counter] for row in samples]
                group[f"{counter}_min"] = min(observed)
                group[f"{counter}_max"] = max(observed)
                group[f"{counter}_mean"] = statistics.mean(observed)
                group[f"{counter}_distribution"] = dict(sorted(Counter(observed).items()))
            groups.append(group)
    speedups = []
    for size in SIZES:
        naive, fixed = [group for group in groups if group["page_size"] == size]
        speedups.append({"page_size": size, **{
            f"{name}_ratio": naive[f"{name}_ms"] / fixed[f"{name}_ms"]
            for name in ("p50", "p95", "p99")}})
    return {"run_id": rows[0]["run_id"], "code_revision": rows[0]["code_revision"],
            "dirty": rows[0]["dirty"], "config_sha256": rows[0]["config_sha256"],
            "request_count": len(rows), "percentile_method": PERCENTILE_METHOD,
            "speedup_definition": "naive latency percentile / fixed latency at the same percentile",
            "groups": groups, "speedups": speedups}


def read_rows(path):
    rows = []
    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                raise ValueError(f"Blank measurement at line {line_number}")
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at line {line_number}") from error
    return rows


def render_markdown(result):
    lines = ["# HW4 Part 3 measured results", "", f"Run: `{result['run_id']}`  ",
             f"Measured revision: `{result['code_revision']}`; dirty: `{str(result['dirty']).lower()}`.  ",
             f"Selected requests: **{result['request_count']}** (30 per endpoint and page size).", "",
             f"Percentiles: {result['percentile_method']}. All latencies are end-to-end HTTP milliseconds.", "",
             "| Page size | Version | Requests | Total SQL/request (min–max) | Data SQL/request (min–max) | p50 ms | p95 ms | p99 ms |",
             "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in result["groups"]:
        lines.append(f"| {row['page_size']} | {row['version']} | {row['samples']} | "
                     f"{row['total_sql_min']}–{row['total_sql_max']} | {row['data_sql_min']}–{row['data_sql_max']} | "
                     f"{row['p50_ms']:.3f} | {row['p95_ms']:.3f} | {row['p99_ms']:.3f} |")
    lines.extend(["", "SQL counts come from response instrumentation, including authentication and session activity in the total. "
                  "The JSON summary preserves every observed counter value and frequency.", "",
                  "| Page size | p50 speed-up | p95 speed-up | p99 speed-up |",
                  "| ---: | ---: | ---: | ---: |"])
    for row in result["speedups"]:
        lines.append(f"| {row['page_size']} | {row['p50_ratio']:.3f}× | {row['p95_ratio']:.3f}× | {row['p99_ratio']:.3f}× |")
    lines.extend(["", "Each speed-up divides the naive percentile by the corresponding fixed percentile. "
                  "Values above 1 mean the fixed version was faster; values below 1 mean it was slower. "
                  "These are ratios of percentiles, not percentiles of paired ratios.", "",
                  "With only 30 requests in each group, p95 and p99 depend strongly on the slowest observations. "
                  "These observations do not establish performance outside this recorded environment.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="Successful attempt's requests.jsonl (exactly 180 rows)")
    parser.add_argument("--output-dir", type=Path, required=True, help="Write metrics.json and METRICS.md here; raw rows are never modified")
    args = parser.parse_args(argv)
    try:
        result = summarize_rows(read_rows(args.raw))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Cannot summarize: {error}\n")
    result["raw_path"] = str(args.raw)
    result["raw_sha256"] = hashlib.sha256(args.raw.read_bytes()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "metrics.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output_dir / "METRICS.md").write_text(render_markdown(result), encoding="utf-8")
    print(f"Validated {result['request_count']} requests; summaries: {args.output_dir}")


if __name__ == "__main__":
    main()
