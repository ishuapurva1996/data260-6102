#!/usr/bin/env python3
"""Refresh report artifact hashes while retaining a prior successful live HW2 check.

This makes no model calls or HTTP requests. Runtime changes require a new full
verification; report-only edits can reuse the recorded live evidence explicitly.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hw02_frozen_verifier", ROOT / "scripts/verify_hw02.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
REQUIRED_CHECKS = {
    "source_ref_matches_checkout", "isolated_web_crud", "deterministic_graph_smoke",
    "saved_part4_evidence", "live_web_8702", "live_graph_termination",
    "submission_artifacts", "source_unchanged_during_checks",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_prior(prior):
    require(isinstance(prior, dict), "Prior verification must be a JSON object")
    require(prior.get("assignment") == "HW2" and prior.get("HW") == 2 and str(prior.get("SID4")) == "6102",
            "Prior verification identifies another assignment")
    for flag in ("passed", "submission_ready", "live_requested", "submission_artifacts_required"):
        require(prior.get(flag) is True, f"Prior verification requires {flag}=true")
    require(isinstance(prior.get("generated_at"), str) and bool(prior["generated_at"]), "Prior run timestamp is missing")
    require(isinstance(prior.get("command"), list) and bool(prior["command"]), "Prior run command is missing")
    require(isinstance(prior.get("ref"), str) and bool(prior["ref"]), "Prior verified ref is missing")
    require(re.fullmatch(r"[0-9a-f]{40}", prior.get("commit_hash", "")) is not None, "Prior commit hash is invalid")
    checks = prior.get("checks")
    require(isinstance(checks, dict) and REQUIRED_CHECKS <= checks.keys(), "Prior verification lacks required checks")
    require(all(isinstance(check, dict) and check.get("passed") is True for check in checks.values()),
            "Every prior check must have passed; skipped live checks cannot be reused")
    live = checks["live_graph_termination"]
    details = live.get("details", {})
    require(live.get("exit_code") == 0 and details.get("passed") is True and details.get("real_model") is True,
            "Prior graph check lacks successful real-model execution")
    require(type(details.get("model_calls")) is int and details["model_calls"] > 0, "Prior graph made no recorded model calls")
    runs = details.get("outcomes", [])
    require(len(runs) == 2 and {run.get("name") for run in runs} == {"normal_reviewer", "controlled_always_issue"},
            "Prior live check must include normal and controlled Reviewer runs")
    for outcome in runs:
        controlled = outcome["name"] == "controlled_always_issue"
        run, validation = outcome["run"], outcome["validation"]
        require(outcome.get("passed") is True and validation.get("passed") is True,
                "Prior live run or its validation did not pass")
        require(outcome.get("exit_code") == int(controlled), "Prior live CLI exit does not match its expected outcome")
        require(run.get("status") == ("turn_limit" if controlled else "accepted") and run.get("error") is None,
                "Prior live run has an invalid terminal outcome")
        require(validation.get("status") == run["status"] and validation.get("turn_count") == run["turn_count"],
                "Prior live validation disagrees with its recorded run")
        require(run["config"]["model"] == prior["model"] and run["config"]["controlled_reviewer"] is controlled,
                "Prior live run model/mode differs from verification metadata")
        for key in ("base_url", "temperature", "timeout", "max_turns", "response_format", "reasoning"):
            require(run["config"][key] == prior["config"][key], f"Prior live configuration mismatch: {key}")
        require(type(run.get("turn_count")) is int and 1 <= run["turn_count"] <= run["max_turns"],
                "Prior live run exceeded its worker ceiling")
        if controlled:
            require(run["turn_count"] == run["max_turns"] and run.get("final_output") is None,
                    "Controlled run did not finish at its ceiling without final output")
    return {"passed": True, "historical_generated_at": prior["generated_at"], "checks_reused": len(checks),
            "live_runs_reused": len(runs)}


def matching_source(prior):
    """Bind current bytes to the tag AND both stored before/after source maps."""
    current = verifier.source_snapshot(ROOT, prior["ref"])
    require(current.get("passed") is True and not current.get("mismatches"), "Current runtime does not match the verified tag")
    require(current.get("commit") == prior["commit_hash"], "Prior tag now resolves to a different commit")
    expected = current["ref_sha256"]
    require(isinstance(expected, dict) and bool(expected) and current["checkout_sha256"] == expected,
            "Current source snapshot is empty or internally inconsistent")
    for name in ("source_ref_matches_checkout", "source_unchanged_during_checks"):
        stored = prior["checks"][name]
        require(stored.get("commit") == prior["commit_hash"] and not stored.get("mismatches"),
                f"Prior {name} does not identify the verified commit")
        for key in ("ref_sha256", "checkout_sha256"):
            require(stored.get(key) == expected, f"Prior {name}.{key} differs from verified runtime bytes")
    return {"passed": True, "ref": prior["ref"], "commit": current["commit"], "files_checked": len(expected),
            "source_map_sha256": sha256(json.dumps(expected, sort_keys=True).encode())}


def refresh(prior_path: Path, refresh_command: list[str]) -> dict:
    """Return a refreshed record or an explicit failed record; never write files."""
    prior_path = Path(prior_path).resolve()
    record = {}
    audit = {
        "checked_at": now(), "command": refresh_command,
        "helper_source_sha256": sha256(Path(__file__).read_bytes()),
        "prior_verification": {"path": str(prior_path), "sha256": None},
        "scope": "Only report artifacts and runtime-source continuity checked now. All live/model checks and their timestamps/results are retained from the prior verification and were not rerun.",
        "live_checks_rerun": False, "model_calls": 0, "checks": {}, "passed": False,
    }
    stage = "prior_verification"
    try:
        prior_bytes = prior_path.read_bytes()
        audit["prior_verification"]["sha256"] = sha256(prior_bytes)
        prior = json.loads(prior_bytes)
        if isinstance(prior, dict):
            record = deepcopy(prior)
        audit["checks"][stage] = validate_prior(prior)
        if "artifact_refresh" in prior:
            audit["previous_refresh"] = deepcopy(prior["artifact_refresh"])
        stage = "runtime_matches_prior_and_tag"
        audit["checks"][stage] = matching_source(prior)
        stage = "submission_artifacts"
        artifacts = verifier.submission_artifacts()
        require(artifacts.get("passed") is True, "Current submission artifacts failed verification")
        artifacts = {**artifacts, "checked_at": now()}
        record["checks"]["submission_artifacts"] = artifacts
        audit["checks"][stage] = {"passed": True, "files_checked": len(artifacts["files"]), "checked_at": artifacts["checked_at"]}
        stage = "runtime_unchanged_during_refresh"
        audit["checks"][stage] = matching_source(prior)
        stage = "prior_file_unchanged"
        require(prior_path.read_bytes() == prior_bytes, "Prior verification changed during refresh")
        audit["checks"][stage] = {"passed": True}
        audit["passed"] = True
    except Exception as exc:
        audit["checks"][stage] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(record.get("checks"), dict):
            record["checks"] = {}
        if "submission_artifacts" not in audit["checks"] or not audit["checks"]["submission_artifacts"].get("passed"):
            record["checks"]["submission_artifacts"] = {
                "passed": False, "status": "not_run" if stage != "submission_artifacts" else "failed",
                "checked_at": now(), "error": f"Artifact refresh blocked at {stage}: {exc}",
            }
    audit["finished_at"] = now()
    record["artifact_refresh"] = audit
    record["passed"] = record["submission_ready"] = audit["passed"]
    return record


def atomic_write(output: Path, record):
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=".hw02-artifact-refresh-", suffix=".json", delete=False) as stream:
            pending = Path(stream.name)
            json.dump(record, stream, indent=2, allow_nan=False)
            stream.write("\n")
        pending.replace(output)
    finally:
        if pending is not None and pending.exists():
            pending.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", required=True, type=Path, help="Preserved successful live verification; never overwritten")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/hw02/verification.json")
    args = parser.parse_args(argv)
    prior, output = args.prior.resolve(), args.output.resolve()
    try:
        verifier.validate_output(output, ROOT)
        require(output != prior, "Output must differ from the preserved prior verification")
    except ValueError as exc:
        parser.error(str(exc))
    command = [sys.executable, str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)]
    result = refresh(prior, command)
    atomic_write(output, result)
    print(json.dumps({"passed": result["passed"], "output": str(output), "model_calls": 0,
                      "refresh_checks": result["artifact_refresh"]["checks"]}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
