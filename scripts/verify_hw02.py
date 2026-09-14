#!/usr/bin/env python3
"""Verify HW2 without changing application source or the running server's records.

Offline checks are the default. Add --live for localhost:8702 GET checks and two
real Ollama graph runs; add --require-submission for the final artifact gate.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
# Freeze application, verifier, and dependency inputs. Reports and presentation
# helpers are deliberately excluded, so recording a result cannot change its ref.
SOURCE_DIRS = ("code", "src")
SOURCE_FILES = ("requirements.txt", "requirements-agents.txt", "package.json",
                "package-lock.json", "scripts/verify_hw02.py", "scripts/verify_part3.py",
                "scripts/verify_part4.py", "reports/hw02/cases/schema_input.json")
ARTIFACTS = ("report.pdf", "RUN_LOG.txt", "METRICS.md", "AI_USE.md",
             "REPRODUCIBLE_RUN_INSTRUCTIONS.md", "README.md")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          check=True, timeout=20).stdout


def is_source(name):
    path = Path(name)
    return (name in SOURCE_FILES or path.parts[0] in SOURCE_DIRS) and not (
        "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"})


def source_snapshot(root, ref):
    """Compare bytes, including added/deleted files, against one immutable commit."""
    commit = git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    names = [name for name in git(root, "ls-tree", "-rz", "--name-only", commit).decode().split("\0")
             if name and is_source(name)]
    expected = {name: digest(git(root, "show", f"{commit}:{name}")) for name in names}
    current_names = {name for name in SOURCE_FILES if (root / name).exists()}
    for directory in SOURCE_DIRS:
        current_names.update(p.relative_to(root).as_posix() for p in (root / directory).rglob("*")
                             if p.is_file() and is_source(p.relative_to(root).as_posix()))
    actual = {name: digest((root / name).read_bytes()) for name in sorted(current_names)}
    mismatches = {name: {"ref_sha256": expected.get(name), "checkout_sha256": actual.get(name)}
                  for name in sorted(expected.keys() | actual.keys()) if expected.get(name) != actual.get(name)}
    return {"passed": bool(expected) and not mismatches, "commit": commit, "ref": ref,
            "scope": {"directories": SOURCE_DIRS, "files": SOURCE_FILES,
                      "excluded": "reports, presentation helpers, tests, Python bytecode"},
            "ref_sha256": expected, "checkout_sha256": actual, "mismatches": mismatches}


def command(arguments, root, timeout=90):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run([str(a) for a in arguments], cwd=root, env=env,
                                capture_output=True, text=True, timeout=timeout)
        return {"passed": result.returncode == 0, "command": [str(a) for a in arguments],
                "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"passed": False, "command": [str(a) for a in arguments], "exit_code": None,
                "error": str(exc)}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def web_smoke():
    from fastapi.testclient import TestClient
    web = load_module("hw02_web_smoke", ROOT / "code/web_application/main.py")
    require(web.PORT_BASE == 8702, "Application port differs from SID4-derived 8702")
    with TestClient(web.create_app()) as client:
        seed = client.get("/api/rentals").json()
        require([row["id"] for row in seed] == [1, 2], "Fresh application lacks seed IDs 1 and 2")
        require(client.get("/").content == (web.STATIC_DIRECTORY / "index.html").read_bytes(), "Home differs from source")
        for asset in ("app.js", "styles.css"):
            require(client.get("/static/" + asset).content == (web.STATIC_DIRECTORY / asset).read_bytes(), "Asset differs from source")
        payload = {key: value for key, value in seed[0].items() if key != "id"}
        payload.update(listingTitle="Verification listing", propertyAddress="8702 Verification Lane")
        created = client.post("/api/rentals", json=payload)
        require(created.status_code == 201 and created.json()["id"] == 3, "Create/next ID failed")
        updated = client.put("/api/rentals/3", json={"listingTitle": "Updated verification", "propertyAddress": "6102 Test Street"})
        require(updated.status_code == 200 and updated.json()["propertyAddress"] == "6102 Test Street", "Update failed")
        require([row["id"] for row in client.get("/api/rentals?q=updated").json()] == [3], "Title search failed")
        require([row["id"] for row in client.get("/api/rentals?q=6102").json()] == [3], "Address search failed")
        require(client.post("/api/rentals", json={**payload, "termsAccepted": False}).status_code == 422, "Invalid create accepted")
        require(client.delete("/api/rentals/highest").status_code == 204, "Highest-ID delete failed")
        require(client.delete("/api/rentals/1").status_code == 204, "Row delete failed")
        require(client.delete("/api/rentals/999").status_code == 404, "Missing row lacks 404")
        require([row["id"] for row in client.get("/api/rentals").json()] == [2], "Delete result incorrect")
        schema_hash = digest(json.dumps(client.get("/openapi.json").json(), sort_keys=True).encode())
    with TestClient(web.create_app()) as fresh:
        require([row["id"] for row in fresh.get("/api/rentals").json()] == [1, 2], "App instances share state")
    return {"passed": True, "transport": "isolated FastAPI TestClient", "port_config": 8702,
            "checks": ["seed", "home/assets", "create", "update", "title/address search", "422", "highest/row delete", "404", "isolation"],
            "openapi_sha256": schema_hash, "live_server_mutations": 0}


def graph_smoke(args):
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT))
    graph = load_module("hw02_graph_smoke", ROOT / "code/agents_graph.py")
    verifier = load_module("hw02_trace_verifier", ROOT / "scripts/verify_part4.py")
    from src.model_client import OllamaModelClient
    draft = {"tags": ["apartment", "parking", "transit"], "summary": "Apartment with covered parking near light rail."}

    class FixtureTransport:
        def __init__(self, responses):
            self.responses = iter(responses)

        def invoke(self, messages):
            return SimpleNamespace(content=json.dumps(next(self.responses)), usage_metadata={}, response_metadata={})

    with tempfile.TemporaryDirectory(prefix="hw02-graph-") as folder:
        base = ["--input-json", str(ROOT / "reports/hw02/cases/schema_input.json"),
                "--model", args.model, "--base-url", args.base_url, "--timeout", str(args.model_timeout),
                "--temperature", "0.0", "--evidence-dir", folder]
        outcomes = []
        cases = [
            ("approval", [draft, {"issues": []}], 2, "accepted"),
            ("schema_repair", [{**draft, "tags": ["ab"]}, draft, {"issues": []}], 3, "accepted"),
            ("bounded_rejection", [draft, {"issues": ["Revise the listing"]}, draft], 3, "turn_limit"),
        ]
        for name, responses, ceiling, expected in cases:
            config = graph.parse_args([*base, "--max-turns", str(ceiling)])
            model = OllamaModelClient(FixtureTransport(responses))
            result = graph.run_graph(config, llm=model)
            # Save and re-read the actual serializable CLI artifact in temporary storage.
            graph._write_evidence(result, Path(folder), "HW2 smoke; temporary evidence.\n")
            saved = json.loads((Path(result["evidence"]["directory"]) / "result.json").read_text())
            counters = verifier.inspect_trace(saved)
            require(expected is None or result["status"] == expected, f"{name}: unexpected terminal outcome")
            if name == "schema_repair":
                require(counters["schema_failure_count"] == 1, "Repair did not record the invalid first proposal")
            outcomes.append({"name": name, "status": result["status"], "turn_count": result["turn_count"],
                             "trace_checks": counters, "run": saved})
    return {"passed": True, "real_model": False, "temporary_evidence_removed": True,
            "model_calls": 0,
            "outcomes": outcomes}


def live_graph_smoke(args):
    """Use the real CLI, retaining both console streams and all saved artifacts."""
    sys.path.insert(0, str(ROOT))
    verifier = load_module("hw02_live_verifier", ROOT / "scripts/verify_part3.py")

    def run_pair(folder):
        outcomes = []
        for controlled in (False, True):
            name = "controlled_always_issue" if controlled else "normal_reviewer"
            arguments = [sys.executable, ROOT / "code/agents_graph.py", "--input-json",
                         ROOT / "reports/hw02/cases/schema_input.json", "--model", args.model,
                         "--base-url", args.base_url, "--temperature", "0.0", "--max-turns", "10",
                         "--timeout", str(args.model_timeout), "--evidence-dir", Path(folder) / name]
            if controlled:
                arguments.append("--controlled-reviewer")
            result = command(arguments, ROOT, timeout=args.model_timeout * 10 + 30)
            validation = verifier.inspect_live_run(result, controlled=controlled)
            # Exit 1 is expected for the deliberately unapprovable controlled run.
            result.update(name=name, passed=validation["passed"], validation=validation)
            if "stdout" in result:
                try:
                    result["run"] = json.loads(result["stdout"])
                except json.JSONDecodeError:
                    pass
            outcomes.append(result)
        return {"passed": all(run["passed"] for run in outcomes), "real_model": True,
                "outcomes": outcomes, "evidence_directory": str(Path(folder).resolve()),
                "temporary_evidence_removed": args.evidence_dir is None,
                "model_calls": sum(run.get("run", {}).get("adapter_response_count", 0) for run in outcomes)}

    if args.evidence_dir is not None:
        return run_pair(args.evidence_dir)
    with tempfile.TemporaryDirectory(prefix="hw02-live-") as temporary:
        return run_pair(temporary)


def read_url(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        require(response.status == 200, f"HTTP {response.status}: {url}")
        return response.read()


def live_web(expected_schema):
    base = "http://127.0.0.1:8702"
    hashes = {}
    for url_path, name in (("/", "index.html"), ("/static/app.js", "app.js"), ("/static/styles.css", "styles.css")):
        hashes[url_path] = digest(read_url(base + url_path))
        require(hashes[url_path] == digest((ROOT / "code/web_application/static" / name).read_bytes()), "Served asset differs from verified checkout: " + name)
    schema = json.loads(read_url(base + "/openapi.json"))
    require(digest(json.dumps(schema, sort_keys=True).encode()) == expected_schema, "Live OpenAPI differs from isolated app")
    rows = json.loads(read_url(base + "/api/rentals"))
    require(isinstance(rows, list), "GET rentals did not return a list")
    require(all(isinstance(row, dict) and type(row.get("id")) is int for row in rows), "Invalid live rental rows")
    return {"passed": True, "url": base, "methods": ["GET"], "record_count": len(rows), "asset_sha256": hashes,
            "provenance_limit": "Observed existing server assets and API schema match this checkout; another process's loaded Python bytes are not attested."}


def submission_artifacts():
    directory = ROOT / "reports/hw02"
    result = {}
    for name in ARTIFACTS:
        data = (directory / name).read_bytes()
        require(bool(data.strip()), "Empty submission artifact: " + name)
        if name == "report.pdf":
            require(data.startswith(b"%PDF-"), "report.pdf lacks a PDF header")
        result[name] = {"bytes": len(data), "sha256": digest(data)}
    return {"passed": True, "files": result,
            "scope": "Presence/nonempty/PDF-header only; report content and AI-use authorship require human review."}


def validate_output(output, root):
    output, root = output.resolve(), root.resolve()
    if output.is_relative_to(root):
        relative = output.relative_to(root)
        require(relative.parent == Path("reports/hw02") and
                (relative.name == "verification.json" or relative.name.startswith("verification_hw02")) and
                relative.suffix == ".json", "Within this repository output must be reports/hw02/verification.json or verification_hw02*.json")
    require(output.suffix == ".json", "Output must be a JSON file")


def validate_evidence(directory, root):
    directory, root = directory.resolve(), root.resolve()
    if directory.is_relative_to(root):
        require(directory.is_relative_to(root / "reports/hw02/raw/submission-smoke"),
                "Within this repository live evidence must be under reports/hw02/raw/submission-smoke")


def outcome(checks, *, live, submission):
    ran = [item["passed"] for item in checks.values() if item["passed"] is not None]
    passed = bool(ran) and all(ran)
    if live or submission:
        passed = passed and all(item["passed"] is True for item in checks.values())
    return passed, passed and live and submission


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="Git tag/hash whose code must match the current runtime checkout")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/hw02/verification.json")
    parser.add_argument("--web-python", type=Path, default=ROOT / ".venv-web/bin/python")
    parser.add_argument("--agent-python", type=Path, default=ROOT / ".venv-agents/bin/python")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--require-submission", action="store_true", help="Require report, disclosure, log, metrics and reproduction instructions")
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--model-timeout", type=float, default=30)
    parser.add_argument("--campaign", type=Path, default=ROOT / "reports/hw02/raw/part4/20260914T0610-baseline")
    parser.add_argument("--evidence-dir", type=Path, help="Retain both real CLI runs; default uses temporary storage. Use reports/hw02/raw/submission-smoke/<label> in this repository.")
    parser.add_argument("--internal", choices=("web", "graph", "live-graph"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    require(args.model_timeout > 0 and args.model_timeout < float("inf"), "Model timeout must be finite and positive")
    if args.evidence_dir is not None:
        args.evidence_dir = args.evidence_dir.resolve()
        validate_evidence(args.evidence_dir, ROOT)
    if args.internal:
        try:
            result = (web_smoke() if args.internal == "web" else
                      live_graph_smoke(args) if args.internal == "live-graph" else graph_smoke(args))
        except Exception as exc:
            result = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(result))
        return 0 if result["passed"] else 1
    output = args.output.resolve()
    validate_output(output, ROOT)
    checks = {}
    report = {"assignment": "HW2", "HW": 2, "SID4": "6102", "DOMAIN_ID": 6, "PORT_BASE": 8702,
              "SEED": 6102, "VERIFY_SEED": 266102,
              "seed_note": "Assignment identity only; neither seed is passed as model RNG configuration. Smoke inputs are deterministic.",
              "generated_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "ref": args.ref, "commit_hash": None, "live_requested": args.live,
              "submission_artifacts_required": args.require_submission,
              "model": args.model, "config": {"base_url": args.base_url, "temperature": 0.0,
              "max_turns": 10, "timeout": args.model_timeout, "num_ctx": 4096, "response_format": "json", "reasoning": False},
              "command": [sys.executable, str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)],
              "checks": checks}

    def check(name, action):
        try:
            checks[name] = action()
        except Exception as exc:
            checks[name] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        return checks[name]

    def child(kind, python):
        arguments = [python, Path(__file__).resolve(), "--internal", kind, "--model", args.model,
                     "--base-url", args.base_url, "--model-timeout", str(args.model_timeout)]
        if args.evidence_dir is not None:
            arguments.extend(["--evidence-dir", args.evidence_dir])
        result = command(arguments, ROOT, timeout=max(90, args.model_timeout * 20 + 90))
        if "stdout" in result:
            details = json.loads(result["stdout"])
            result["details"] = details
            result["passed"] = result["passed"] and details["passed"] is True
            del result["stdout"]
        return result

    source = check("source_ref_matches_checkout", lambda: source_snapshot(ROOT, args.ref))
    report["commit_hash"] = source.get("commit")
    web = check("isolated_web_crud", lambda: child("web", args.web_python))
    check("deterministic_graph_smoke", lambda: child("graph", args.agent_python))
    with tempfile.TemporaryDirectory(prefix="hw02-part4-") as temporary:
        def part4():
            target = Path(temporary) / "verification.json"
            result = command([args.agent_python, ROOT / "scripts/verify_part4.py", "--campaign", args.campaign,
                              "--report-dir", ROOT / "reports/hw02", "--output", target], ROOT)
            if target.exists():
                details = json.loads(target.read_text())
                result["details"] = details
                result["passed"] = result["passed"] and details["passed"] is True
                result.pop("stdout", None)
            return result
        check("saved_part4_evidence", part4)
    if args.live:
        check("live_web_8702", lambda: live_web(web["details"]["openapi_sha256"]))
        check("live_graph_termination", lambda: child("live-graph", args.agent_python))
    else:
        for name in ("live_web_8702", "live_graph_termination"):
            checks[name] = {"passed": None, "status": "not_run", "reason": "Use --live; no live status inferred from saved evidence."}
    if args.require_submission:
        check("submission_artifacts", submission_artifacts)
    # Recheck bytes after execution to catch edits during the verification window.
    after = check("source_unchanged_during_checks", lambda: source_snapshot(ROOT, source.get("commit", args.ref)))
    if source.get("checkout_sha256") != after.get("checkout_sha256"):
        after.update(passed=False, error="Runtime source changed during verification")
    report["passed"], report["submission_ready"] = outcome(checks, live=args.live, submission=args.require_submission)
    report["scope"] = "Whole-HW2 executable smoke and saved evidence checks; offline success alone is not final live submission verification."
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, delete=False, prefix=".hw02-verification-", suffix=".json") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    Path(stream.name).replace(output)
    print(json.dumps({"passed": report["passed"], "submission_ready": report["submission_ready"], "output": str(output),
                      "checks": {name: value["passed"] for name, value in checks.items()}}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
