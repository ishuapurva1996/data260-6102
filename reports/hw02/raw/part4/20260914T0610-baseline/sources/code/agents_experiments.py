#!/usr/bin/env python3
"""Prepare/run real Part 4 campaigns; report saved evidence offline (no model calls)."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import urllib.request
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_graph.evaluation import IntegrityError, aggregate_records, classify_result

SOURCE_PATHS = [
    "code/agents_graph.py", "code/agents_experiments.py", "src/model_client.py",
    "src/agent_graph/__init__.py", "src/agent_graph/contracts.py", "src/agent_graph/nodes.py",
    "src/agent_graph/state.py", "src/agent_graph/router.py", "src/agent_graph/workflow.py",
    "src/agent_graph/evaluation.py", "requirements-agents.txt", "scripts/verify_part4.py",
]
CONFIG = dict(model="qwen3:1.7b", base_url="http://localhost:11434", temperature=0.0,
              timeout=120.0, num_ctx=4096, response_format="json", reasoning=False,
              controlled_reviewer=False, model_seed=None)
IDENTITY = dict(homework="HW2", SID4=6102, DOMAIN_ID=6, SEED=6102, VERIFY_SEED=266102)
METRICS = {
    "turn": "one Planner or Reviewer execution; supervisor is not a turn",
    "latency": "application-run elapsed_ms: Git inspection, adapter and graph construction, execution and trace handling; excludes process startup/imports and evidence writing",
    "schema_category": "terminal acceptance grouped by Planner attempts (1, 2, >=3); ceiling takes precedence; operational error/unknown separate",
    "completion": "accepted with schema-valid current proposal and matching normal Reviewer approval / all planned cohort trials",
    "choice": "higher completion rate, then lower all-run mean application latency, then smaller ceiling",
    "usage": "reported usage only; zero may mean missing metadata",
    "seeds": "SEED and VERIFY_SEED are assignment identity, not model RNG seeds",
    "residency": "sequential fresh processes; normal Ollama caching and residency; excluded warm-up each session",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def fingerprint(value):
    return digest(json_bytes(value))


def read_json(path):
    try:
        return parse_json_bytes(Path(path).read_bytes(), str(path))
    except (OSError, ValueError) as exc:
        raise IntegrityError(f"Cannot read {path}: {exc}") from exc


def parse_json_bytes(data, label):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise IntegrityError(f"Duplicate JSON key in {label}: {key}")
            obj[key] = value
        return obj
    def invalid_constant(value):
        raise IntegrityError(f"Nonfinite JSON: {value}")
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or Path(relative).is_absolute():
        raise IntegrityError(f"Unsafe campaign reference: {relative}")
    return path


def schedule_trials():
    items = []
    def add(trial_id, cohort, ceiling, input_key="schema", pair=None):
        items.append(dict(trial_id=trial_id, cohort=cohort, order=len(items)+1,
                          max_turns=ceiling, input_key=input_key, pair=pair))
    for n in range(1, 31):
        add(f"schema-{n:02}", "schema", 10)
    for pair in range(1, 21):
        for ceiling in ((2, 10) if pair % 2 else (10, 2)):
            add(f"pair-{pair:02}-c{ceiling}", f"ceiling_{ceiling}", ceiling, pair=pair)
    for n in range(1, 6):
        add(f"adversarial-{n:02}", "adversarial", 10, "adversarial")
    return items


def environment():
    packages = {d.metadata["Name"].lower(): d.version for d in importlib.metadata.distributions()}
    return dict(python=platform.python_version(), platform=platform.platform(),
                machine=platform.machine(), packages=dict(sorted(packages.items())))


def model_identity(config):
    # Metadata queries only. All generation remains in src/model_client.py.
    with urllib.request.urlopen(config["base_url"] + "/api/tags", timeout=10) as response:
        installed = json.load(response)["models"]
    matches = [m for m in installed if m["name"] == config["model"]]
    if len(matches) != 1 or not matches[0].get("digest"):
        raise IntegrityError(f"Installed model/digest unavailable: {config['model']}")
    with urllib.request.urlopen(config["base_url"] + "/api/version", timeout=10) as response:
        version = json.load(response)
    return dict(name=config["model"], digest=matches[0]["digest"], details=matches[0].get("details"),
                ollama_version=version["version"])


def git_metadata():
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=True).stdout.strip()
    status = git("status", "--porcelain=v1")
    return dict(commit=git("rev-parse", "HEAD"), branch=git("branch", "--show-current"),
                status=status, dirty=bool(status))


def prepare_campaign(path, schema_input, adversarial_input, *, config=None):
    path = Path(path).resolve()
    config = dict(CONFIG if config is None else config)
    if config != CONFIG:
        raise IntegrityError("Part 4 baseline configuration must match the frozen protocol")
    inputs = {}
    for key, source in (("schema", schema_input), ("adversarial", adversarial_input)):
        data = Path(source).read_bytes()
        case = parse_json_bytes(data, str(source))
        if not isinstance(case, dict) or set(case)-{"title", "content", "email"} or any(
            not isinstance(case.get(k), str) or not case[k].strip() for k in ("title", "content")
        ) or ("email" in case and (not isinstance(case["email"], str) or not case["email"].strip())):
            raise IntegrityError(f"Invalid {key} CLI input")
        inputs[key] = dict(path=f"inputs/{key}_input.json", sha256=digest(data), data=data)
    if inputs["schema"]["sha256"] == inputs["adversarial"]["sha256"]:
        raise IntegrityError("Adversarial input must differ from the ordinary input")
    sources = {name: (REPO_ROOT/name).read_bytes() for name in SOURCE_PATHS}
    source_hashes = {name: digest(data) for name, data in sources.items()}
    env, model, git = environment(), model_identity(config), git_metadata()
    manifest = dict(schema_version=1, campaign_id=path.name, prepared_at=utc_now(), identity=IDENTITY,
                    config=config, config_fingerprint=fingerprint(config), source_fingerprint=fingerprint(source_hashes),
                    source_sha256=source_hashes, environment=env, model_identity=model, git=git,
                    metric_definitions=METRICS, schedule=schedule_trials(),
                    inputs={k: {a:b for a,b in v.items() if a != "data"} for k,v in inputs.items()})
    path.mkdir(parents=True, exist_ok=False)
    for item in inputs.values():
        target = path/item["path"]
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(item["data"])
    for name, data in sources.items():
        target = path/"sources"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_new(path/"source-sha256.json", source_hashes)
    (path/"environment.txt").write_bytes(json_bytes(env))
    write_new(path/"manifest.json", manifest)
    (path/"manifest.sha256").write_text(digest((path/"manifest.json").read_bytes()) + "\n")
    return manifest


def load_manifest(path, *, execution=False):
    path = Path(path).resolve()
    manifest = read_json(path/"manifest.json")
    if digest((path/"manifest.json").read_bytes()) != (path/"manifest.sha256").read_text().strip():
        raise IntegrityError("Manifest hash mismatch")
    if manifest["schema_version"] != 1 or manifest["schedule"] != schedule_trials():
        raise IntegrityError("Wrong manifest version or 30/20/20/5 alternating schedule")
    if manifest["identity"] != IDENTITY or manifest["config"] != CONFIG or manifest["metric_definitions"] != METRICS:
        raise IntegrityError("Protocol or identity mismatch")
    if fingerprint(manifest["config"]) != manifest["config_fingerprint"]:
        raise IntegrityError("Configuration fingerprint mismatch")
    hashes = read_json(path/"source-sha256.json")
    if hashes != manifest["source_sha256"] or fingerprint(hashes) != manifest["source_fingerprint"] or set(hashes) != set(SOURCE_PATHS):
        raise IntegrityError("Source fingerprint mismatch")
    for name, sha in hashes.items():
        if digest(safe_path(path, "sources/"+name).read_bytes()) != sha:
            raise IntegrityError(f"Frozen source mismatch: {name}")
        if execution and digest((REPO_ROOT/name).read_bytes()) != sha:
            raise IntegrityError(f"Execution source changed: {name}; preserve campaign and prepare a new one")
    if read_json(path/"environment.txt") != manifest["environment"]:
        raise IntegrityError("Environment snapshot mismatch")
    for item in manifest["inputs"].values():
        if digest(safe_path(path, item["path"]).read_bytes()) != item["sha256"]:
            raise IntegrityError("Frozen input hash mismatch")
    if set(manifest["inputs"]) != {"schema", "adversarial"} or manifest["inputs"]["schema"]["sha256"] == manifest["inputs"]["adversarial"]["sha256"]:
        raise IntegrityError("Ordinary and adversarial input snapshots must be distinct")
    if execution and (environment() != manifest["environment"] or model_identity(manifest["config"]) != manifest["model_identity"]):
        raise IntegrityError("Execution environment or installed model changed")
    return manifest


@contextmanager
def campaign_lock(path):
    lock = Path(path)/"runner.lock"
    try:
        write_new(lock, dict(pid=os.getpid(), acquired_at=utc_now()))
    except FileExistsError as exc:
        raise IntegrityError("Campaign already owned (runner.lock); inspect owner before removing a stale lock") from exc
    try:
        yield
    finally:
        lock.unlink()


def trial_base(manifest, slot):
    return dict(schema_version=1, campaign_id=manifest["campaign_id"], trial_id=slot["trial_id"],
                cohort=slot["cohort"], order=slot["order"], max_turns=slot["max_turns"],
                input_sha256=manifest["inputs"][slot["input_key"]]["sha256"],
                config_fingerprint=manifest["config_fingerprint"], source_fingerprint=manifest["source_fingerprint"])


def execute_trial(path, manifest, slot, *, folder="trials"):
    path = Path(path).resolve()
    directory = path/folder/slot["trial_id"]
    directory.mkdir(parents=True, exist_ok=False)
    config = manifest["config"]
    args = [sys.executable, str(REPO_ROOT/"code/agents_graph.py"), "--input-json",
            str(path/manifest["inputs"][slot["input_key"]]["path"]), "--max-turns", str(slot["max_turns"]),
            "--model", config["model"], "--base-url", config["base_url"], "--temperature", str(config["temperature"]),
            "--timeout", str(config["timeout"]), "--evidence-dir", str(directory/"cli")]
    base = trial_base(manifest, slot)
    write_new(directory/"started.json", dict(**base, started_at=utc_now(), command=args, git=git_metadata()))
    started = time.perf_counter()
    returncode = None
    failure = None
    with (directory/"stdout.json").open("wb") as out, (directory/"stderr.txt").open("wb") as err:
        try:
            process = subprocess.run(args, cwd=REPO_ROOT, stdout=out, stderr=err,
                                     timeout=slot["max_turns"]*config["timeout"]+90, check=False)
            returncode = process.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            failure = f"{type(exc).__name__}: {exc}"
    record = dict(**base, finished_at=utc_now(), subprocess_wall_ms=(time.perf_counter()-started)*1000,
                  returncode=returncode, run_id=None, elapsed_ms=None, status="error", operational_error=failure,
                  evidence=(directory/"stdout.json").relative_to(path).as_posix(), cli_evidence=False)
    try:
        if failure:
            raise IntegrityError(failure)
        result = read_json(directory/"stdout.json")
        expected = {"accepted": 0, "turn_limit": 1, "error": 2}.get(result.get("status"))
        if returncode != expected or expected is None:
            raise IntegrityError("Subprocess exit/status mismatch")
        cli = directory/"cli"/result["run_id"]
        if read_json(cli/"result.json") != result:
            raise IntegrityError("CLI evidence differs from stdout")
        record.update(classify_result(result))
        record["evidence"] = (cli/"result.json").relative_to(path).as_posix()
        record["cli_evidence"] = True
    except (IntegrityError, KeyError, OSError, TypeError, ValueError) as exc:
        record.update(status="error", operational_error=str(exc))
    record["files_sha256"] = {f.relative_to(directory).as_posix(): digest(f.read_bytes())
                              for f in directory.rglob("*") if f.is_file()}
    write_new(directory/"result.json", record)
    print(f"{utc_now()} {slot['trial_id']} status={record['status']} turns={record.get('turn_count')} elapsed_ms={record.get('elapsed_ms')}", flush=True)
    return record


def read_trial(path, manifest, slot, *, folder="trials"):
    path = Path(path).resolve()
    directory = path/folder/slot["trial_id"]
    if not directory.exists():
        return None
    base = trial_base(manifest, slot)
    if not (directory/"started.json").exists():
        raise IntegrityError(f"Partial trial directory without start marker: {directory}")
    started = read_json(directory/"started.json")
    if "--controlled-reviewer" in started.get("command", []):
        raise IntegrityError("Controlled Reviewer command is not a measured trial")
    if any(started.get(k) != v for k,v in base.items()):
        raise IntegrityError("Start marker metadata mismatch")
    if not (directory/"result.json").exists():
        return dict(**base, status="unknown", run_id=None, elapsed_ms=None,
                    evidence=(directory/"started.json").relative_to(path).as_posix(),
                    operational_error="Started trial has no terminal record; never rerun this ID")
    record = read_json(directory/"result.json")
    if any(record.get(k) != v for k,v in base.items()):
        raise IntegrityError("Trial metadata mismatch")
    files = {f.relative_to(directory).as_posix(): digest(f.read_bytes())
             for f in directory.rglob("*") if f.is_file() and f != directory/"result.json"}
    if files != record.get("files_sha256"):
        raise IntegrityError(f"Trial file hash mismatch: {slot['trial_id']}")
    if record.get("cli_evidence"):
        result_path = safe_path(path, record["evidence"])
        if result_path.parent.parent != directory/"cli":
            raise IntegrityError("Evidence belongs to another trial")
        result = read_json(result_path)
        derived = classify_result(result)
        if any(record.get(k) != v for k,v in derived.items()):
            raise IntegrityError("Derived trial counters differ from raw trace")
        if record["returncode"] != {"accepted":0,"turn_limit":1,"error":2}[result["status"]]:
            raise IntegrityError("Exit code differs from raw status")
        if read_json(directory/"stdout.json") != result or read_json(result_path.parent/"stdout.json") != result:
            raise IntegrityError("Raw stdout differs from terminal evidence")
        if read_json(result_path.parent/"events.json") != {"trace":result["trace"],"events":result["events"]}:
            raise IntegrityError("CLI event evidence differs")
        case = read_json(path/manifest["inputs"][slot["input_key"]]["path"])
        if result["input"] != {"title":case["title"],"content":case["content"],"email":case.get("email")}:
            raise IntegrityError("Actual CLI input differs from frozen case")
        actual_config = {k:v for k,v in manifest["config"].items() if k not in {"num_ctx","model_seed"}}
        actual_config.update(max_turns=slot["max_turns"], turn_definition="one Planner or Reviewer execution")
        if result["config"] != actual_config:
            raise IntegrityError("Actual CLI configuration differs from manifest")
        if result["git"]["commit"] != started["git"]["commit"] or result["git"]["dirty"] != started["git"]["dirty"]:
            raise IntegrityError("Execution Git metadata differs from start marker")
    elif record["status"] != "error":
        raise IntegrityError("Content outcome missing raw evidence")
    return record


def load_campaign(path):
    """Offline only: validate frozen bytes and raw records; never construct a model."""
    path = Path(path).resolve()
    manifest = load_manifest(path)
    allowed = {s["trial_id"] for s in manifest["schedule"]}
    if (path/"trials").exists() and any(p.name not in allowed for p in (path/"trials").iterdir()):
        raise IntegrityError("Unexpected measured trial directory")
    records = [r for slot in manifest["schedule"] if (r := read_trial(path, manifest, slot)) is not None]
    summary = aggregate_records(records, manifest["schedule"])
    return manifest, records, summary


def run_campaign(path, *, limit=None):
    path = Path(path).resolve()
    with campaign_lock(path):
        manifest = load_manifest(path, execution=True)
        _, records, summary = load_campaign(path)
        if summary["error"] or summary["unknown"]:
            raise IntegrityError("Campaign has error/unknown trials; preserve it and diagnose before a new campaign")
        done = {r["trial_id"] for r in records}
        pending = [s for s in manifest["schedule"] if s["trial_id"] not in done]
        if not pending:
            return summary
        warmup = dict(trial_id="warmup-"+uuid.uuid4().hex[:12], cohort="warmup", order=0,
                      max_turns=10, input_key="schema", pair=None)
        warm = execute_trial(path, manifest, warmup, folder="warmups")
        if warm["status"] == "error":
            raise IntegrityError("Excluded warm-up failed; no measured trial started")
        for slot in pending[:limit]:
            # Detect changes before every launch, including source edits between sessions.
            load_manifest(path, execution=True)
            record = execute_trial(path, manifest, slot)
            if record["status"] == "error":
                raise IntegrityError("Measured operational error; stopped without replacing the trial")
        return load_campaign(path)[2]


def write_report(path):
    path = Path(path).resolve()
    _, records, summary = load_campaign(path)
    # Derived reports alone are replaceable. No trial or manifest is ever rewritten.
    (path/"results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True, allow_nan=False)+"\n" for r in records))
    fields = sorted({key for r in records for key in r if key != "files_sha256"})
    with (path/"results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    (path/"summary.json").write_bytes(json_bytes(summary))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Freeze schedule, cases, sources, environment and installed model metadata; no generation")
    prepare.add_argument("--campaign", type=Path, required=True)
    prepare.add_argument("--schema-input", type=Path, default=REPO_ROOT/"reports/hw02/cases/schema_input.json")
    prepare.add_argument("--adversarial-input", type=Path, default=REPO_ROOT/"reports/hw02/cases/adversarial_input.json")
    run = commands.add_parser("run", help="EXPENSIVE: excluded warm-up plus pending real-model trials, sequentially")
    run.add_argument("--campaign", type=Path, required=True)
    run.add_argument("--limit", type=int, help="Stop cleanly after this many pending trials; resume never-started slots only")
    report = commands.add_parser("report", help="OFFLINE: verify saved evidence and regenerate CSV/JSON; zero model calls")
    report.add_argument("--campaign", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            value = prepare_campaign(args.campaign, args.schema_input, args.adversarial_input)
            print(f"Prepared {value['campaign_id']}: {len(value['schedule'])} frozen measured slots")
        elif args.command == "run":
            if args.limit is not None and args.limit < 1:
                raise IntegrityError("--limit must be positive")
            print(json.dumps(run_campaign(args.campaign, limit=args.limit), indent=2))
        else:
            summary = write_report(args.campaign)
            print(json.dumps(summary, indent=2))
            return 0 if summary["complete"] else 1
    except (IntegrityError, OSError, KeyError, ValueError) as exc:
        print(f"Experiment error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
