"""Freeze and run one genuine combined Part 6 demonstration in a private temp root."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]

from scripts.hw06.runtime_lease import RuntimeLease
from src.bikeshare.service import run_child
from src.course_files.agent import MODEL_OPTIONS, run_file_agent
from src.course_files.gate import SAFE_PREFIXES, confirm_bash
from src.course_files.sandbox import MAX_BYTES, MAX_FILES, MAX_OUTPUT, MAX_SECONDS, FileTools
from src.model_client import build_ollama_client

CASES = ROOT / "reports/hw07/cases"


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def source_hashes():
    paths = [
        *sorted((ROOT / "src/course_files").glob("*.py")),
        Path(__file__),
        ROOT / "src/model_client.py",
        ROOT / "src/tool_agent/budget.py",
        ROOT / "requirements-hw07-part4.lock.txt",
        CASES / "safety_commands.json",
        CASES / "file_discovery.json",
    ]
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}


def profile():
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as stream:
        model = next(m for m in json.load(stream)["models"] if m["name"] == MODEL_OPTIONS["model"])
    with urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=10) as stream:
        version = json.load(stream)
    return {"model": model, "ollama": version, "python": platform.python_version()}


def clean_source():
    return not git(
        "status",
        "--porcelain",
        "--",
        "src",
        "scripts",
        "tests",
        "code",
        "frontend",
        "experiments",
        "pyproject.toml",
        ".pre-commit-config.yaml",
    )


def freeze(path):
    assert clean_source(), "Commit reviewed implementation before freezing."
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "student": "Pragya Apurva",
        "frozen_at": utc(),
        "source_commit": git("rev-parse", "HEAD"),
        "source_sha256": source_hashes(),
        "model_configuration": MODEL_OPTIONS,
        "runtime_profile": profile(),
        "safe_prefixes": SAFE_PREFIXES,
        "file_limits": {
            "max_bytes": MAX_BYTES,
            "max_files": MAX_FILES,
            "process_seconds": MAX_SECONDS,
            "output_bytes": MAX_OUTPUT,
        },
        "cases": {
            "safety": json.loads((CASES / "safety_commands.json").read_text()),
            "discovery": json.loads((CASES / "file_discovery.json").read_text()),
        },
        "verification": "glob/search/read in order; read path from unique discovered match; exact observed contents in raw JSON; 5 allow/5 block; never execute expected-block strings",
        "bounds": "at most5 model requests/6 tools/16000 charged tokens/240s agent; CLI supervisor260s; each safe process3s and16384output bytes",
    }
    save(path, value)
    print("Pragya Apurva | FROZEN", utc(), sha(path.read_bytes()), flush=True)


def run(path, output, runtime):
    frozen = json.loads(path.read_text())
    assert source_hashes() == frozen["source_sha256"] and clean_source(), "Frozen source drift."
    assert profile() == frozen["runtime_profile"], "Model/runtime profile drift."
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    events = []

    def emit(event, **fields):
        row = {"sequence": len(events) + 1, "timestamp_utc": utc(), "event": event, **fields}
        events.append(row)
        with (output / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("Pragya Apurva | DATA260 HW7 Part6 | COMBINED GENUINE RUN |", utc(), flush=True)
    print(
        "Model-driven integration; deterministic string-only gate matrix; blocked strings NEVER executed.",
        flush=True,
    )
    with RuntimeLease(
        runtime,
        owner="HW7-Part6-file-demo",
        purpose="one bounded real-model discovery demonstration",
    ):
        with tempfile.TemporaryDirectory(prefix="data260-hw7-course-", dir=output) as temporary:
            with FileTools(temporary) as tools:
                fixtures = frozen["cases"]["discovery"]
                for name, content in fixtures["files"].items():
                    result = tools.write_file(name, content)
                    assert result["success"]
                    emit("fixture_write", path=name, result=result)
                assert (
                    len(fixtures["files"]) == 3
                    and sum("DEBUG" in t for t in fixtures["files"].values()) == 1
                )
                print("ONE INITIAL USER INSTRUCTION:", fixtures["instruction"], flush=True)
                settings = MODEL_OPTIONS
                model = build_ollama_client(
                    settings["model"],
                    "http://127.0.0.1:11434",
                    settings["temperature"],
                    settings["request_timeout"],
                    reasoning=False,
                    context_window=settings["context_window"],
                    output_limit=settings["output_limit"],
                    seed=settings["seed"],
                )

                def agent_event(row):
                    with (output / "model-trace.jsonl").open("a") as stream:
                        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    emit("agent", observation=row)
                    if row["event"] in {"tool_request", "tool_result", "raw_final", "terminal"}:
                        print("Pragya Apurva |", json.dumps(row, ensure_ascii=False), flush=True)

                integration = run_file_agent(
                    fixtures["instruction"], tools, model=model, event_callback=agent_event
                )
                save(output / "integration.json", integration)
                extras = []
                for name, args in [
                    (
                        "write_file",
                        {
                            "path": "notes.txt",
                            "content": "DEBUG outside Python filter\nline two\nline three\n",
                        },
                    ),
                    ("edit_file", {"path": "notes.txt", "old": "line two", "new": "line TWO"}),
                    ("read_file", {"path": "notes.txt", "max_lines": 1}),
                    ("search_in_files", {"query": "DEBUG", "file_pattern": "*.py"}),
                ]:
                    result = getattr(tools, name)(**args)
                    extras.append({"name": name, "inputs": args, "result": result})
                    emit("file_exercise", **extras[-1])
                    print("Pragya Apurva | FILE_EXERCISE", json.dumps(extras[-1]), flush=True)
                assert all(e["result"]["success"] for e in extras)
                assert (
                    "-line two" in extras[1]["result"]["data"]["diff"]
                    and "+line TWO" in extras[1]["result"]["data"]["diff"]
                )
                assert extras[2]["result"]["data"]["truncated"]
                assert all(
                    m["path"].endswith(".py") for m in extras[3]["result"]["data"]["matches"]
                )
                save(output / "file-exercises.json", extras)
                safety = []
                for case in frozen["cases"]["safety"]["cases"]:
                    decision = confirm_bash(case["command"], auto_approve=True)
                    observed = "allow" if decision["allowed"] else "block"
                    entry = {
                        **case,
                        "decision": decision,
                        "observed": observed,
                        "matched": observed == case["expected"],
                        "false_allow": observed == "allow" and case["expected"] == "block",
                        "executed": False,
                    }
                    if case["expected"] == "allow" and decision["allowed"]:
                        execution = tools.bash(case["command"], auto_approve=True)
                        entry.update(executed=execution["data"]["executed"], execution=execution)
                        assert execution["success"] and execution["data"]["returncode"] == 0
                    safety.append(entry)
                    emit("gate_case", **entry)
                    print(
                        f"Pragya Apurva | {case['command']} => {observed.upper()} | {decision['reason']} | executed={entry['executed']}",
                        flush=True,
                    )
                save(output / "safety-gate.json", safety)
                for filename in fixtures["files"]:
                    content = tools.read_file(filename, max_lines=1000)["data"]["content"]
                    assert content == fixtures["files"][filename]
                summary = {
                    "student": "Pragya Apurva",
                    "started_at": events[0]["timestamp_utc"],
                    "finished_at": utc(),
                    "source_commit": git("rev-parse", "HEAD"),
                    "source_dirty": not clean_source(),
                    "freeze_sha256": sha(path.read_bytes()),
                    "configuration": MODEL_OPTIONS,
                    "integration_passed": integration["verification"]["passed"],
                    "integration_stop_reason": integration["stop_reason"],
                    "allowed": sum(e["observed"] == "allow" for e in safety),
                    "blocked": sum(e["observed"] == "block" for e in safety),
                    "false_allows": sum(e["false_allow"] for e in safety),
                    "matrix_matches": sum(e["matched"] for e in safety),
                    "blocked_commands_executed": sum(
                        e["executed"] for e in safety if e["expected"] == "block"
                    ),
                    "file_exercises_passed": True,
                    "fixture_bytes_unchanged": True,
                    "course_sandbox_removed_after_run": True,
                    "private_sandbox_root": temporary,
                    "models_only_for_discovery": True,
                }
                save(output / "summary.json", summary)
                print(
                    "Pragya Apurva | FINAL",
                    json.dumps({k: v for k, v in summary.items() if k != "private_sandbox_root"}),
                    flush=True,
                )
    assert not Path(temporary).exists()
    assert (
        summary["integration_passed"]
        and summary["matrix_matches"] == 10
        and summary["false_allows"] == 0
    )
    print(
        "Pragya Apurva | COMBINED_RUN_PASS | 5 ALLOW / 5 BLOCK | sandbox removed |",
        utc(),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--runtime-dir", type=Path)
    args = parser.parse_args()
    if args.run:
        if not args.output or not args.runtime_dir or args.output.resolve().is_relative_to(ROOT):
            parser.error("Run needs external output and shared runtime directory.")
        if args.worker:
            run(args.freeze, args.output, args.runtime_dir)
        else:
            args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--freeze",
                str(args.freeze.resolve()),
                "--run",
                "--worker",
                "--output",
                str((args.output / "run").resolve()),
                "--runtime-dir",
                str(args.runtime_dir.resolve()),
            ]
            supervised = run_child(command, args.output, timeout=260)
            save(args.output / "supervisor.json", {**supervised, "finished_at": utc()})
            print((args.output / "worker.log").read_text(), end="", flush=True)
            if supervised["returncode"] != 0 or supervised["timed_out"]:
                raise SystemExit("Combined demonstration failed; preserve its original output.")
    else:
        freeze(args.freeze)


if __name__ == "__main__":
    main()
