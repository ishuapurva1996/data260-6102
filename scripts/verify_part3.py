"""Verify Part 3 only; --live also records two real Ollama graph runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.agent_graph.contracts import validate_planner_proposal, validate_reviewer_feedback


def command_result(command: list[str], timeout: float) -> dict:
    """Keep command output even when a verification process fails."""
    try:
        result = subprocess.run(
            command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout
        )
        return {"command": command, "exit_code": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired as exc:
        def text(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        return {"command": command, "exit_code": None, "error": "verification timeout",
                "stdout": text(exc.stdout), "stderr": text(exc.stderr)}


def inspect_live_run(run: dict, *, controlled: bool) -> dict:
    """A demo's expected exit 1 is a passing check, never accepted metadata."""
    try:
        result = json.loads(run["stdout"])
        evidence = result["evidence"]
        if evidence["status"] != "saved":
            raise ValueError("CLI did not save complete evidence")
        folder = Path(evidence["directory"])
        events = json.loads((folder / "events.json").read_text())
        # events.json contains the serializable worker trace, not runtime state.
        workers = events["trace"]
        if len(workers) != result["turn_count"] or len(workers) != result["worker_attempts"]:
            raise ValueError("trace length differs from worker turn count")
        if not 1 <= result["turn_count"] <= result["max_turns"]:
            raise ValueError("worker count is outside the configured budget")
        if [event["attempt"] for event in workers] != list(range(1, len(workers) + 1)):
            raise ValueError("trace attempt sequence is incomplete")
        if controlled:
            if run["exit_code"] != 1 or result["status"] != "turn_limit":
                raise ValueError("controlled run did not stop at its ceiling")
            if result["max_turns"] != 10 or result["turn_count"] != 10 or result["final_output"] is not None:
                raise ValueError("controlled run returned a wrong count or accepted output")
            loop = any(
                a["worker"] == "reviewer" and a.get("outcome") == "valid" and a.get("controlled")
                and a.get("parsed", {}).get("issues")
                and b["worker"] == "planner"
                for a, b in zip(workers, workers[1:])
            )
            if not loop or not result["config"]["controlled_reviewer"]:
                raise ValueError("no observed controlled Reviewer-to-Planner loop")
        else:
            if run["exit_code"] != 0 or result["status"] != "accepted":
                raise ValueError("ordinary run was not accepted")
            validate_planner_proposal(result["final_output"])
            review = validate_reviewer_feedback(result["review"])
            if review["issues"] or result["final_output"] != result["proposal"]:
                raise ValueError("accepted output does not match an approved current proposal")
            if result["config"]["controlled_reviewer"]:
                raise ValueError("ordinary acceptance cannot use the controlled Reviewer")
            if result["reviewed_revision"] != result["proposal_revision"]:
                raise ValueError("acceptance refers to an older proposal")
        return {"passed": True, "run_id": result["run_id"],
                "status": result["status"], "turn_count": result["turn_count"],
                "evidence_directory": str(folder)}
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        return {"passed": False, "error": str(exc)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="also call local Ollama")
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "reports/hw02")
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    commit = command_result(["git", "rev-parse", "HEAD"], 10)["stdout"].strip()
    dirty = bool(command_result(["git", "status", "--porcelain"], 10)["stdout"].strip())
    records = []
    checks = {}
    unit = command_result(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests/agent_graph", "-v"], 120
    )
    records.append({"name": "graph_tests", **unit})
    checks["graph_tests"] = {"passed": unit["exit_code"] == 0}
    dependency_check = command_result([sys.executable, "-m", "pip", "check"], 60)
    records.append({"name": "dependency_check", **dependency_check})
    checks["dependency_check"] = {"passed": dependency_check["exit_code"] == 0}
    if args.live:
        for controlled in (False, True):
            name = "controlled_loop" if controlled else "ordinary_model_run"
            print(f"Running {name} with {args.model}...", flush=True)
            command = [sys.executable, str(REPO_ROOT / "code/agents_graph.py"),
                       "--input-json", str(REPO_ROOT / "reports/hw02/cases/part3_listing.json"),
                       "--model", args.model, "--base-url", args.base_url,
                       "--temperature", "0", "--timeout", "120", "--max-turns", "10",
                       "--evidence-dir", str(output / "raw/part3")]
            if controlled:
                command.append("--controlled-reviewer")
            run = command_result(command, 1230)
            records.append({"name": name, **run})
            checks[name] = inspect_live_run(run, controlled=controlled)
            print(f"{name}: {checks[name]}", flush=True)
    report = {
        "assignment": "HW2", "part": 3, "SID4": "6102", "SEED": 6102,
        "VERIFY_SEED": 266102,
        "seed_note": "Assignment identity metadata; these seeds were not passed to the model.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "observed_commit": commit, "dirty_working_tree": dirty,
        "scope": "Part 3 implementation verification; not final tagged HW2 submission",
        "python": platform.python_version(),
        "dependencies": {name: importlib.metadata.version(name) for name in
                         ("langgraph", "langchain-ollama", "langchain-core", "ollama")},
        "live_requested": args.live, "checks": checks,
        "passed": all(check["passed"] for check in checks.values()),
    }
    (output / "verification_part3.json").write_text(json.dumps(report, indent=2) + "\n")
    with (output / "RUN_LOG_PART3.txt").open("w") as log:
        for record in records:
            log.write(f"CHECK: {record['name']}\nCOMMAND: {json.dumps(record['command'])}\n")
            log.write(f"EXIT: {record['exit_code']}\nSTDOUT:\n{record['stdout']}\n")
            log.write(f"STDERR:\n{record['stderr']}\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
