#!/usr/bin/env python3
"""Run the serial HW4 Part 3 HTTPS experiment and preserve every attempt.

Supply credentials only through environment variables. Login, payload equality
checks and warmups are outside the 180 measured requests. Each invocation creates
a new run directory; failed and partial attempts remain separate from later runs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


SIZES = (10, 50, 200)
VERSIONS = ("naive", "fixed")
REPETITIONS = 30
CONFIG_FIELDS = {
    "database", "database_host", "database_port", "mysql_version", "schema_revision",
    "seed", "seed_manifest", "seed_manifest_sha256", "dataset_sha256", "rental_count",
    "manager_count", "foundation_commit", "index_state", "runtime", "server", "notes",
    "instance_id", "instance_ownership", "worker_count", "reload", "sqlalchemy_version",
    "python_version", "uvicorn_version", "fastapi_version", "host_platform", "tls",
}
SECRET_KEYS = re.compile(r"password|passwd|secret|token|cookie|credential|authorization|database_url|dsn", re.I)


class BenchmarkError(ValueError):
    def __init__(self, message, attempt_path=None):
        super().__init__(message)
        self.attempt_path = attempt_path


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_base_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("base URL must be an HTTPS origin without credentials, path, query or fragment")
    return value.rstrip("/")


def validate_config(config):
    """Copy only an explicit, non-secret experiment configuration, never the env."""
    if not isinstance(config, dict) or set(config) - CONFIG_FIELDS:
        raise ValueError("Configuration has unknown fields; use the documented non-secret field names")

    def inspect(value):
        if isinstance(value, dict):
            if any(not isinstance(key, str) or SECRET_KEYS.search(key) for key in value):
                raise ValueError("Configuration must not contain credential or session fields")
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
        elif isinstance(value, str):
            if "://" in value and urlsplit(value).username:
                raise ValueError("Configuration must not contain credential-bearing URLs")
        elif value is not None and type(value) not in (int, float, bool):
            raise ValueError("Configuration must contain only JSON values")

    inspect(config)
    canonical_json(config)  # Reject non-finite floats as well.
    return config


def revision_metadata(repository):
    def git(*args):
        return subprocess.run(["git", "-C", str(repository), *args], text=True,
                              capture_output=True, check=True).stdout.strip()
    revision = git("rev-parse", "HEAD")
    if not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError("Could not establish the actual Git revision")
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    return {"code_revision": revision, "dirty": bool(status), "git_status": status.splitlines()}


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _append(handle, row):
    handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
    handle.flush()


def _validate_payload(payload, page_size):
    if not isinstance(payload, list) or len(payload) != page_size:
        raise BenchmarkError("Response must be an array with exactly the requested number of rentals")
    previous = 0
    required = {"id", "listingTitle", "propertyAddress", "submitterEmail", "description",
                "propertyType", "termsAccepted", "manager"}
    for rental in payload:
        if not isinstance(rental, dict) or not required <= rental.keys():
            raise BenchmarkError("Rental response is missing required fields")
        rental_id = rental["id"]
        if type(rental_id) is not int or rental_id <= previous:
            raise BenchmarkError("Rental IDs must be positive, unique and ordered")
        previous = rental_id
        manager = rental["manager"]
        if (not isinstance(manager, dict) or type(manager.get("id")) is not int
                or manager["id"] <= 0 or not isinstance(manager.get("name"), str) or not manager["name"]):
            raise BenchmarkError("Every seeded rental must contain its manager ID and name")


def _sample(client, *, page_size, version, iteration, phase, identity, expected_payload, handle, expected_digest=None):
    row = {**identity, "timestamp": utc_now(), "phase": phase, "page_size": page_size,
           "version": version, "iteration": iteration, "http_status": None,
           "returned_count": None, "elapsed_ms": None, "total_sql": None, "data_sql": None,
           "payload_sha256": None, "valid": False, "error": None}
    started = time.perf_counter_ns()
    try:
        response = client.get(f"/api/rentals/{version}", params={"page_size": page_size, "offset": 0})
        # httpx non-streaming requests consume the response body before returning.
        row["elapsed_ms"] = (time.perf_counter_ns() - started) / 1_000_000
        row["http_status"] = response.status_code
        if response.status_code != 200:
            raise BenchmarkError(f"Expected HTTP 200; received {response.status_code}")
        try:
            payload = response.json()
        except (ValueError, UnicodeError) as error:
            raise BenchmarkError("Response is not valid JSON") from error
        row["returned_count"] = len(payload) if isinstance(payload, list) else None
        _validate_payload(payload, page_size)
        row["payload_sha256"] = digest(payload)
        for header, field in (("X-SQL-Statements", "total_sql"), ("X-Data-SQL-Statements", "data_sql")):
            observed = response.headers.get(header, "")
            if not re.fullmatch(r"[0-9]+", observed):
                raise BenchmarkError(f"Missing or invalid actual SQL instrumentation header {header}")
            row[field] = int(observed)
        if row["total_sql"] <= row["data_sql"]:
            raise BenchmarkError("Total SQL counter must include authentication in addition to data queries")
        if row["data_sql"] != (page_size + 1 if version == "naive" else 1):
            raise BenchmarkError("Observed data-query count does not demonstrate the required N+1/join strategy")
        if expected_payload is not None and (payload != expected_payload or row["payload_sha256"] != (expected_digest or digest(expected_payload))):
            raise BenchmarkError("Full ordered response payload differs from the validated baseline")
        row["valid"] = True
    except (Exception, KeyboardInterrupt) as error:
        if row["elapsed_ms"] is None:
            row["elapsed_ms"] = (time.perf_counter_ns() - started) / 1_000_000
        # Transport errors may include request information; retain only their type.
        row["error"] = str(error) if isinstance(error, BenchmarkError) else f"Request failed ({type(error).__name__})"
        _append(handle, row)
        raise BenchmarkError(row["error"]) from error
    _append(handle, row)
    return payload


def run_benchmark(client, output_root, *, email, password, metadata, warmups=3):
    """Run one complete attempt. Exceptions expose the preserved attempt_path."""
    if type(warmups) is not int or warmups < 1:
        raise ValueError("At least one separate warmup per size/version is required")
    if not email or not password:
        raise ValueError("Benchmark credentials must be supplied outside tracked files")
    validate_base_url(str(client.base_url))
    config = validate_config(metadata.get("config", {}))
    if not re.fullmatch(r"[0-9a-f]{40}", metadata.get("code_revision", "")) or type(metadata.get("dirty")) is not bool:
        raise ValueError("Metadata must record the actual measured Git revision and dirty state")
    started_at = utc_now()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    attempt = Path(output_root) / run_id
    attempt.mkdir(parents=True, exist_ok=False)
    identity = {"run_id": run_id, "code_revision": metadata["code_revision"], "dirty": metadata["dirty"],
                "config_sha256": digest(config)}
    manifest = {**metadata, **identity, "started_at": started_at, "finished_at": None,
                "status": "running", "base_url": str(client.base_url).rstrip("/"),
                "page_sizes": list(SIZES), "versions": list(VERSIONS), "offset": 0,
                "requests_per_group": REPETITIONS, "expected_measured_requests": 180,
                "warmups_per_group": warmups, "measured_requests": 0,
                "order": "page size 10,50,200; iteration 1..30; naive then fixed; serial",
                "timer": "time.perf_counter_ns around a fully buffered HTTP GET; milliseconds",
                "client_runtime": {"python": sys.version, "httpx": httpx.__version__, "platform": platform.platform()},
                "credentials": "Supplied through environment; values and login body omitted"}
    manifest_path = attempt / "manifest.json"
    _write_json(manifest_path, manifest)
    measured_rows = 0
    with (attempt / "requests.jsonl").open("x", encoding="utf-8") as measured, \
            (attempt / "preflight.jsonl").open("x", encoding="utf-8") as preflight, \
            (attempt / "warmups.jsonl").open("x", encoding="utf-8") as warming:
        try:
            response = client.post("/api/auth/login", json={"email": email, "password": password})
            manifest["login_status"] = response.status_code
            if response.status_code != 200:
                raise BenchmarkError(f"Login failed with HTTP {response.status_code}")
            baselines = {}
            for size in SIZES:
                for version in VERSIONS:
                    payload = _sample(client, page_size=size, version=version, iteration=0,
                                      phase="preflight", identity=identity, expected_payload=baselines.get(size), handle=preflight)
                    if version == "naive":
                        baselines[size] = payload
            manifest["preflight_equal_payloads"] = True
            manifest["baseline_payload_sha256"] = {str(size): digest(payload) for size, payload in baselines.items()}
            for size in SIZES:
                for iteration in range(1, warmups + 1):
                    for version in VERSIONS:
                        _sample(client, page_size=size, version=version, iteration=iteration,
                                phase="warmup", identity=identity, expected_payload=baselines[size], handle=warming,
                                expected_digest=manifest["baseline_payload_sha256"][str(size)])
            for size in SIZES:
                for iteration in range(1, REPETITIONS + 1):
                    for version in VERSIONS:
                        # Count attempted requests as well; a failed final row remains auditable.
                        measured_rows += 1
                        _sample(client, page_size=size, version=version, iteration=iteration,
                                phase="measured", identity=identity, expected_payload=baselines[size], handle=measured,
                                expected_digest=manifest["baseline_payload_sha256"][str(size)])
            manifest["status"] = "success"
        except (Exception, KeyboardInterrupt) as error:
            manifest["status"] = "failed"
            manifest["failure"] = str(error) if isinstance(error, BenchmarkError) else f"Attempt stopped ({type(error).__name__})"
            raise BenchmarkError(manifest["failure"], attempt_path=attempt) from error
        finally:
            manifest["measured_requests"] = measured_rows
            manifest["finished_at"] = utc_now()
            _write_json(manifest_path, manifest)
    return attempt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Non-secret --config fields: " + ", ".join(sorted(CONFIG_FIELDS)))
    parser.add_argument("--base-url", default="https://localhost:8702", help="HTTPS origin; final evidence uses port 8702")
    parser.add_argument("--output-root", type=Path, default=Path("reports/hw04/raw/part3/attempts"), help="Parent of new immutable attempt directories")
    parser.add_argument("--config", type=Path, required=True, help="Non-secret experiment JSON: schema/seed/database/runtime/index state")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3], help="Repository whose actual revision/status will be recorded")
    parser.add_argument("--email-env", default="HW4_BENCHMARK_EMAIL", help="Environment variable holding the login email")
    parser.add_argument("--password-env", default="HW4_BENCHMARK_PASSWORD", help="Environment variable holding the login password")
    parser.add_argument("--warmups", type=int, default=3, help="Unmeasured warmups per size/version, at least 1 (default: 3)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds (default: 30)")
    tls = parser.add_mutually_exclusive_group()
    tls.add_argument("--ca-file", type=Path, help="Trust this local HTTPS CA/certificate")
    tls.add_argument("--insecure", action="store_true", help="Explicitly disable local TLS certificate verification; recorded in manifest")
    args = parser.parse_args(argv)
    try:
        base_url = validate_base_url(args.base_url)
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        config = validate_config(json.loads(args.config.read_text(encoding="utf-8")))
        metadata = {**revision_metadata(args.repo), "config": config,
                    "config_source": str(args.config.resolve()), "timeout_seconds": args.timeout,
                    "tls_verification": "disabled explicitly" if args.insecure else str(args.ca_file) if args.ca_file else "system trust"}
        verify = False if args.insecure else str(args.ca_file) if args.ca_file else True
        with httpx.Client(base_url=base_url, verify=verify, timeout=args.timeout,
                          follow_redirects=False, trust_env=False) as client:
            attempt = run_benchmark(client, args.output_root, email=os.environ.get(args.email_env),
                                    password=os.environ.get(args.password_env), metadata=metadata, warmups=args.warmups)
    except BenchmarkError as error:
        parser.exit(1, f"Benchmark failed: {error}. Preserved attempt: {error.attempt_path}\n")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Benchmark configuration failed ({type(error).__name__}): {error}\n")
    print(f"Completed exactly 180 validated measured requests: {attempt}")


if __name__ == "__main__":
    main()
