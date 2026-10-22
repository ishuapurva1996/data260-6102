"""Reproducible local-model pilot, freeze, paired measurement and demonstrations."""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "code")]

from scripts.hw06.runtime_lease import RuntimeLease
from scripts.hw07.agent_cases import freeze
from src.hw06_shared.models import QwenTokenCounter
from src.model_client import build_ollama_client
from src.rental_tools.executor import execute_tool
from src.rental_tools.reader import MySQLRentalReader
from src.rental_tools.service import RentalService
from src.tool_agent.budget import Budget
from src.tool_agent.loop import current_revision, run_agent, tool_schemas
from src.tool_agent.reflexion import run_reflexion
from src.tool_agent.verification import verify_missing_id

DEFAULT_CASES = ROOT / "reports/hw07/cases/agent_tasks.json"
DEFAULT_FREEZE = ROOT / "reports/hw07/cases/experiment.json"
TOKENIZER = Path(
    "/Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime/qwen2.5-tokenizer.json"
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()


def source_dirty():
    return bool(
        subprocess.check_output(
            [
                "git",
                "status",
                "--porcelain",
                "--",
                "src",
                "code",
                "scripts",
                "tests",
                "frontend",
                "requirements*.txt",
                "pyproject.toml",
                ".pre-commit-config.yaml",
            ],
            cwd=ROOT,
            text=True,
        ).strip()
    )


def code_hashes():
    paths = [
        *sorted((ROOT / "src/tool_agent").glob("*.py")),
        ROOT / "src/model_client.py",
        *sorted((ROOT / "src/rental_tools").glob("*.py")),
        *sorted((ROOT / "scripts/hw07").glob("agent_*.py")),
    ]
    return {str(path.relative_to(ROOT)): sha(path) for path in paths}


def schema_hash():
    return hashlib.sha256(json.dumps(tool_schemas(), sort_keys=True).encode()).hexdigest()


def configuration(context_window=8192):
    return {
        "model_name": "qwen2.5:7b",
        "base_url": "http://127.0.0.1:11434",
        "temperature": 0.0,
        "timeout": 90.0,
        "context_window": context_window,
        "output_limit": 512,
        "seed": 6102,
        "max_steps": 8,
        "max_tools": 8,
        "task_token_budget": 24000,
        "task_tool_budget": 24,
        "max_retries": 2,
    }


def model_digest(config):
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.get(config["base_url"] + "/api/tags")
        response.raise_for_status()
    return next(
        row["digest"] for row in response.json()["models"] if row["name"] == config["model_name"]
    )


def prepare_freeze(args, cases):
    if args.freeze.exists():
        raise RuntimeError("Freeze already exists; do not replace measured rules.")
    config = configuration(args.context_window)
    data = {
        "frozen_at": now(),
        "sid4": 6102,
        "verify_seed": 266102,
        "configuration": config,
        "model_digest": model_digest(config),
        "cases_sha256": sha(args.cases),
        "tokenizer_sha256": sha(args.tokenizer),
        "code_sha256": code_hashes(),
        "dependency_lock_sha256": sha(ROOT / "requirements-hw07.lock.txt"),
        "tool_schemas_sha256": schema_hash(),
        "schedule": [
            {
                "task_id": task["id"],
                "repetition": repetition,
                "mode_order": ["original", "reflexion"]
                if repetition % 2
                else ["reflexion", "original"],
            }
            for repetition in range(1, 8)
            for task in cases["tasks"]
        ],
        "scoring": {
            "success": "strict structured public facts AND actual required successful tool chain",
            "validity_denominator": "original native operation proposals; repaired proposals do not enlarge it",
            "first_pass": "valid original proposals / original proposals",
            "post_repair": "originally valid or successfully corrected original proposals / same denominator",
            "failure_categories": [
                "malformed arguments",
                "unknown tool",
                "text when a tool was required",
                "lost multi-step chain",
            ],
            "failure_counts": "cases containing each label; labels may overlap",
            "failure_definitions": {
                "malformed arguments": "malformed/schema-invalid proposals or malformed native protocol",
                "unknown tool": "proposal names outside the three-tool allowlist",
                "text when a tool was required": "an answer was emitted while the required trace was incomplete",
                "lost multi-step chain": "required trace assertions failed after observations or without a final answer",
                "factual_or_format_failures": "separate answer assertions and unsupported-claim audit; never relabeled as an incomplete chain",
            },
            "unsupported_claims": "unsupported final factual fields; rejected non-JSON answers also require independent audit",
            "retry_rate": "cases entering at least one whole-task Reflexion retry / 21; tool repairs separate",
            "costs": "all actual executor calls, model input/output tokens and wall latency including retries",
            "false_rejections": "independent trace/fixture review of rejected answers, saved separately",
            "budgets": "single ledger across retries; reserve conservative prompt/output before each request; unknown usage is charged in full, never treated as zero",
            "reflection": "deterministic, concise evidence-linked diagnostics; no extra model call; isolated by user and root run",
        },
        "missing_id_prompt": f"Get rental {cases['missing_id']} using get_rental. Return only one JSON object with keys rental_id and found: use the requested integer rental_id and found false if the tool reports it was not found. Do not invent any rental fields or add other keys.",
        "controlled_fault": "Separate unscored B demonstration changes only its first final count by +1 after real generation; all retries use the unmodified live model.",
    }
    args.freeze.parent.mkdir(parents=True, exist_ok=True)
    with args.freeze.open("x") as stream:
        stream.write(json.dumps(data, indent=2) + "\n")
    print("Pragya Apurva | FROZEN |", args.freeze, "| cases", data["cases_sha256"])


class ControlledCountFault:
    """Explicitly artificial final-answer corruption, never used in scored runs."""

    def __init__(self, model):
        self.model = model
        self.injected = None

    def complete(self, messages, tools=None):
        response = self.model.complete(messages, tools=tools)
        if self.injected is None and not response.raw_response.tool_calls:
            try:
                parsed = json.loads(response.content)
                original = parsed["count"]
                if type(original) is int:
                    parsed["count"] = original + 1
                    content = json.dumps(parsed)
                    self.injected = {
                        "kind": "controlled_fault_not_scored",
                        "original_answer": response.content,
                        "altered_answer": content,
                        "fault": "first final count incremented by one",
                    }
                    return replace(
                        response,
                        content=content,
                        raw_response=response.raw_response.model_copy(update={"content": content}),
                    )
            except (ValueError, TypeError, KeyError):
                pass
        return response


def proposal_rows(events):
    originals = {
        row["proposal_id"]: {**row, "final_valid": row["initial_valid"], "repair_used": False}
        for row in events
        if row["event"] == "proposal"
    }
    for row in events:
        if row["event"] == "repair":
            originals[row["proposal_id"]].update(
                final_valid=row["final_valid"],
                repair_used=True,
                repair_call_id=row.get("call_id"),
                repaired_inputs=row.get("inputs"),
            )
    return list(originals.values())


def run_case(
    task,
    mode,
    config,
    service,
    *,
    code_revision,
    reflection_path=None,
    controlled_fault=False,
    tokenizer_path=TOKENIZER,
):
    began, timer = now(), time.perf_counter()
    counter = QwenTokenCounter(tokenizer_path, expected_sha256=sha(tokenizer_path))
    budget = Budget(
        max_tokens=config["task_token_budget"],
        max_tools=config["task_tool_budget"] if mode == "reflexion" else config["max_tools"],
        context_window=config["context_window"],
        output_limit=config["output_limit"],
        token_counter=counter,
    )
    options = {
        key: config[key]
        for key in (
            "model_name",
            "base_url",
            "temperature",
            "timeout",
            "context_window",
            "output_limit",
            "seed",
            "max_steps",
            "max_tools",
        )
    }
    model = build_ollama_client(
        config["model_name"],
        config["base_url"],
        config["temperature"],
        config["timeout"],
        reasoning=False,
        context_window=config["context_window"],
        output_limit=config["output_limit"],
        seed=config["seed"],
    )
    fault = ControlledCountFault(model) if controlled_fault else None
    stream = io.StringIO()

    def execute(name, inputs):
        return execute_tool(name, inputs, service=service)

    if mode == "reflexion":
        result = run_reflexion(
            task["prompt"],
            task=task,
            user_id="s6102-study",
            max_retries=config["max_retries"],
            budget=budget,
            model=fault or model,
            executor=execute,
            log_stream=stream,
            reflection_path=reflection_path,
            code_revision=code_revision,
            **options,
        )
    else:
        result = run_agent(
            task["prompt"],
            task=task,
            budget=budget,
            model=model,
            executor=execute,
            log_stream=stream,
            code_revision=code_revision,
            **options,
        )
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    verdict = result.verification if mode == "reflexion" else events[-1]["verification"]
    retries = result.retries if mode == "reflexion" else 0
    elapsed = (time.perf_counter() - timer) * 1000
    proposals = proposal_rows(events)
    categories = sorted(
        {
            category
            for row in events
            if row["event"] == "terminal"
            for category in row["failure_categories"]
        }
    )
    row = {
        "run_id": result.run_id,
        "task_id": task["id"],
        "mode": mode,
        "started_at": began,
        "finished_at": now(),
        "source_commit": code_revision,
        "source_dirty": source_dirty(),
        "evidence_kind": "real Ollama and MySQL; no mocked responses",
        "controlled_fault": bool(controlled_fault),
        "success": result.stop_reason == "success",
        "stop_reason": (
            result.stop_reason
            if result.stop_reason in {"success", "budget_exhausted", "human_review"}
            else "budget_exhausted"
            if result.stop_reason == "max_steps"
            else "human_review"
        ),
        "internal_stop_reason": result.stop_reason,
        "answer": result.answer,
        "verification": verdict,
        "retries": retries,
        "tool_calls": budget.tools,
        "latency_ms": elapsed,
        "budget": budget.snapshot(),
        "proposal_count": len(proposals),
        "initial_valid": sum(p["initial_valid"] for p in proposals),
        "final_valid": sum(p["final_valid"] for p in proposals),
        "repair_operations": sum(p["repair_used"] for p in proposals),
        "failure_categories": categories,
    }
    if fault is not None:
        row["fault_evidence"] = fault.injected
    return row, events, proposals


def emit_run(output, row, events, proposals):
    append(output / "attempts.jsonl", row)
    for event in events:
        if event["event"] in {
            "proposal",
            "repair",
            "proposal_rejected",
            "tool_request",
            "tool_result",
            "reflection",
        }:
            print(json.dumps(event, ensure_ascii=False), flush=True)
        append(
            output / "traces.jsonl",
            {
                "study_case_run_id": row["run_id"],
                "task_id": row["task_id"],
                "mode": row["mode"],
                "source_commit": row["source_commit"],
                **event,
            },
        )
    for proposal in proposals:
        append(
            output / "proposals.jsonl",
            {
                "study_case_run_id": row["run_id"],
                "task_id": row["task_id"],
                "mode": row["mode"],
                **proposal,
            },
        )
    print(
        "Pragya Apurva |",
        row["mode"],
        "|",
        row["task_id"],
        "| rep",
        row.get("repetition", "demo"),
        "|",
        row["stop_reason"],
        "| tools",
        row["tool_calls"],
        "| tokens",
        row["budget"]["total_tokens"],
        "| ms",
        round(row["latency_ms"], 1),
        flush=True,
    )
    print("FINAL", row["answer"], flush=True)
    if not row["verification"]["passed"]:
        print("ASSERTIONS", json.dumps(row["verification"]["failures"]), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=["pilot", "freeze", "scored", "recovery", "controlled-fault"]
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--context-window", type=int, default=8192)
    parser.add_argument("--tokenizer", type=Path, default=TOKENIZER)
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    cases = json.loads(args.cases.read_text())
    engine = create_engine(os.environ["HW4_DATABASE_URL"], hide_parameters=True)
    with RuntimeLease(args.runtime_dir, owner="HW7-agent-study", purpose=args.stage):
        try:
            freeze(engine, args.cases)
        finally:
            engine.dispose()
        if args.stage == "freeze":
            prepare_freeze(args, cases)
            return
        if args.output is None:
            parser.error("Supply a fresh output directory; exploratory runs must be external.")
        args.output.mkdir(parents=True, exist_ok=False)
        if args.stage == "pilot":
            config, frozen = configuration(args.context_window), None
        else:
            frozen = json.loads(args.freeze.read_text())
            config = frozen["configuration"]
            if (
                sha(args.cases) != frozen["cases_sha256"]
                or code_hashes() != frozen["code_sha256"]
                or sha(args.tokenizer) != frozen["tokenizer_sha256"]
                or model_digest(config) != frozen["model_digest"]
                or sha(ROOT / "requirements-hw07.lock.txt") != frozen["dependency_lock_sha256"]
                or schema_hash() != frozen["tool_schemas_sha256"]
            ):
                raise RuntimeError("Frozen inputs, source, tokenizer or model changed.")
            if source_dirty():
                raise RuntimeError(
                    "Commit application source before final live evidence collection."
                )
        manifest = {
            "student": "Pragya Apurva",
            "started_at": now(),
            "stage": args.stage,
            "source_commit": current_revision(),
            "source_dirty": source_dirty(),
            "configuration": config,
            "model_digest": model_digest(config),
            "cases_sha256": sha(args.cases),
            "code_sha256": code_hashes(),
            "tokenizer_sha256": sha(args.tokenizer),
            "dependency_lock_sha256": sha(ROOT / "requirements-hw07.lock.txt"),
            "tool_schemas_sha256": schema_hash(),
            "freeze_sha256": sha(args.freeze) if frozen is not None else None,
            "scored": args.stage == "scored",
        }
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        reader = MySQLRentalReader(os.environ["HW4_DATABASE_URL"])
        service = RentalService(reader)
        try:
            if args.stage == "recovery":
                stream = io.StringIO()
                result = run_agent(
                    frozen["missing_id_prompt"],
                    executor=lambda name, inputs: execute_tool(name, inputs, service=service),
                    log_stream=stream,
                    code_revision=current_revision(),
                    **{
                        key: value
                        for key, value in config.items()
                        if key not in ("task_token_budget", "task_tool_budget", "max_retries")
                    },
                )
                (args.output / "traces.jsonl").write_text(stream.getvalue())
                events = [json.loads(line) for line in stream.getvalue().splitlines()]
                actual = [e for e in events if e["event"] == "tool_result"]
                verdict = verify_missing_id(cases["missing_id"], result.answer, actual)
                passed = result.stop_reason == "completed" and verdict["passed"]
                data = {
                    "student": "Pragya Apurva",
                    "passed": bool(passed),
                    "source_commit": current_revision(),
                    "result": asdict(result),
                    "verification": verdict,
                    "started_at": manifest["started_at"],
                    "finished_at": now(),
                }
                (args.output / "result.json").write_text(json.dumps(data, indent=2) + "\n")
                print("Pragya Apurva | missing-ID recovery |", data["passed"], "|", result.answer)
                for event in actual:
                    print(json.dumps(event, ensure_ascii=False), flush=True)
                if not passed:
                    raise RuntimeError("Recovery acceptance failed; real output retained.")
                return
            if args.stage == "pilot":
                schedule = [
                    {"task_id": t["id"], "repetition": 0, "mode_order": ["original"]}
                    for t in cases["tasks"]
                ]
            elif args.stage == "controlled-fault":
                schedule = [{"task_id": "B", "repetition": 0, "mode_order": ["reflexion"]}]
            else:
                schedule = frozen["schedule"]
            for pair in schedule:
                task = next(t for t in cases["tasks"] if t["id"] == pair["task_id"])
                for mode in pair["mode_order"]:
                    folder = args.output / mode
                    row, events, proposals = run_case(
                        task,
                        mode,
                        config,
                        service,
                        code_revision=current_revision(),
                        reflection_path=folder / "reflections.jsonl",
                        controlled_fault=args.stage == "controlled-fault",
                        tokenizer_path=args.tokenizer,
                    )
                    row["repetition"] = pair["repetition"]
                    emit_run(folder, row, events, proposals)
            manifest["finished_at"] = now()
            (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        finally:
            reader.close()


if __name__ == "__main__":
    main()
