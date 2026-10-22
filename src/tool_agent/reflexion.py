import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from .budget import Budget
from .logging import AgentLogError, RunLogger
from .loop import run_agent


@dataclass(frozen=True)
class ReflexionResult:
    run_id: str
    answer: str | None
    stop_reason: str
    retries: int
    tool_calls: int
    latency_ms: float
    budget: dict
    verification: dict
    attempts: list[dict]


class _AttemptLog:
    def __init__(self, destination):
        self.destination = destination
        self.events = []

    def write(self, line):
        written = self.destination.write(line)
        if written != len(line):
            raise AgentLogError("Agent log could not be written.")
        self.events.append(json.loads(line))
        return written

    def flush(self):
        self.destination.flush()


def run_reflexion(
    user_input,
    *,
    task,
    user_id,
    max_retries=2,
    budget=None,
    log_stream=None,
    log_path=None,
    reflection_path=None,
    **options,
):
    """Retry only this task, with one ledger and at most two concise reflections.

    No reflection is ever loaded from disk. Stored entries are evidence, not
    instructions or shared memory. Reflection generation is deterministic and
    therefore makes no additional model call or unaccounted token expenditure.
    """
    if type(max_retries) is not int or not 0 <= max_retries <= 2:
        raise ValueError("max_retries must be an integer from 0 through 2.")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id must be nonempty text.")
    budget = (
        budget
        if budget is not None
        else Budget(
            context_window=options.get("context_window", 8192),
            output_limit=options.get("output_limit", 512),
        )
    )
    root_id = uuid4().hex
    logger = RunLogger(root_id, stream=log_stream, path=log_path)
    started = time.monotonic()
    attempts = []
    reflection = None
    last_answer = None
    verification = {"passed": False, "failures": ["attempt.not_started"], "unsupported_claims": []}

    def finish(reason):
        result = ReflexionResult(
            root_id,
            last_answer,
            reason,
            max(0, len(attempts) - 1),
            budget.tools,
            (time.monotonic() - started) * 1000,
            budget.snapshot(),
            verification,
            attempts,
        )
        logger.emit(
            "reflexion_terminal",
            **{key: value for key, value in asdict(result).items() if key != "run_id"},
        )
        return result

    try:
        logger.emit(
            "reflexion_start",
            user_id=user_id,
            task_id=task["id"],
            max_retries=max_retries,
            budget=budget.snapshot(),
            reflection_generation="deterministic, no model call",
        )
        for retry_index in range(max_retries + 1):
            if budget.tools >= budget.max_tools:
                return finish("budget_exhausted")
            captured = _AttemptLog(logger.stream)
            result = run_agent(
                user_input,
                task=task,
                budget=budget,
                reflection=reflection,
                context={
                    "user_id": user_id,
                    "parent_run_id": root_id,
                    "task_id": task["id"],
                    "retry_index": retry_index,
                },
                log_stream=captured,
                **options,
            )
            terminal = captured.events[-1]
            verification = terminal["verification"]
            last_answer = result.answer
            attempts.append(
                {
                    "run_id": result.run_id,
                    "retry_index": retry_index,
                    "stop_reason": result.stop_reason,
                    "verification": verification,
                    "tool_calls": result.tool_calls,
                    "steps": result.steps,
                }
            )
            if result.stop_reason == "success":
                return finish("success")
            if result.stop_reason == "budget_exhausted" or budget.tools >= budget.max_tools:
                return finish("budget_exhausted")
            if retry_index == max_retries or result.stop_reason in {
                "safety_block",
                "model_error",
                "tool_error",
                "malformed_response",
            }:
                return finish("human_review")
            observations = [
                {key: event[key] for key in ("call_id", "name", "inputs", "result")}
                for event in captured.events
                if event["event"] == "tool_result"
            ]
            reflection = {
                "user_id": user_id,
                "run_id": root_id,
                "task_id": task["id"],
                "retry_index": retry_index + 1,
                "failed_attempt_id": result.run_id,
                "failed_assertions": verification["failures"],
                "evidence": observations[-3:],
                "failed_answer": result.answer,
                "explanation": "The previous attempt failed the recorded objective task checks.",
                "strategy": "Repeat the required chain from the original instruction. Use the first "
                "search IDs, copy the observed public fields and manager count exactly, and "
                "return only the requested JSON. Do not change tools, permissions or budgets.",
                "generation": "deterministic",
                "generation_tokens": 0,
            }
            logger.emit(
                "reflection", **{key: value for key, value in reflection.items() if key != "run_id"}
            )
            if reflection_path is not None:
                destination = Path(reflection_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("a") as stream:
                    stream.write(json.dumps(reflection, ensure_ascii=False, allow_nan=False) + "\n")
                    stream.flush()
        return finish("human_review")
    finally:
        logger.close()
