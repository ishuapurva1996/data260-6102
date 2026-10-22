import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from .config import BikeConfig
from .policies import official_url
from .trips import parse_trips

RUNTIME_BUSY_ERROR = "The shared model runtime is busy. Try again after the active run finishes."


class ServiceBusy(Exception):
    pass


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".pending.json")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def run_child(command, directory, *, timeout, on_start=None, on_end=None):
    """Kill the entire owned process group on deadline; no abandoned model thread."""
    directory = Path(directory)
    began = time.monotonic()
    allowed = {
        "PATH",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    }
    environment = {k: v for k, v in os.environ.items() if k in allowed}
    environment.update(
        PYTHONUNBUFFERED="1", LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false"
    )
    with (directory / "worker.log").open("w") as stream:
        process = subprocess.Popen(
            command,
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if on_start:
            on_start(process)
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
            except ProcessLookupError:
                process.wait(timeout=2)
        finally:
            if on_end:
                on_end(process)
    return {
        "timed_out": timed_out,
        "returncode": process.returncode,
        "latency_ms": round((time.monotonic() - began) * 1000, 1),
    }


def read_trace(directory):
    path = Path(directory) / "trace.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            break
    return rows


def interrupted_result(directory, request, *, timed_out, latency_ms):
    trace = read_trace(directory)
    snapshots = [e["budget"] for e in trace if e["event"] == "usage"]
    budget = (
        dict(snapshots[-1])
        if snapshots
        else {
            "tools": 0,
            "charged_tokens": 0,
            "reported_input_tokens": 0,
            "reported_output_tokens": 0,
            "total_tokens": 0,
            "unknown_usage_calls": 0,
        }
    )
    pending = [e for e in trace if e["event"] == "model_request"]
    responses = [e for e in trace if e["event"] == "model_response"]
    if len(pending) > len(responses):
        budget["charged_tokens"] += pending[-1]["reservation"]["total_tokens"]
        budget["total_tokens"] = None
        budget["unknown_usage_calls"] += 1
    return {
        "run_id": request["run_id"],
        "user_id": request["user_id"],
        "decision": None,
        "verification": {
            "passed": False,
            "failures": ["runtime.wall_limit" if timed_out else "runtime.worker_failed"],
        },
        "metrics": {
            "steps": sum(e["event"] == "graph_step" for e in trace),
            "model_requests": len(pending),
            "tool_calls": sum(e["event"] == "tool_request" for e in trace),
            "input_tokens": budget["reported_input_tokens"],
            "output_tokens": budget["reported_output_tokens"],
            "total_tokens": budget["total_tokens"],
            "budget": budget,
            "latency_ms": latency_ms,
            "stop_reason": "budget_exhausted" if timed_out else "human_review",
        },
        "error": "Worker reached its hard wall deadline."
        if timed_out
        else "Framework worker failed; the private run log is retained.",
        "trace": trace,
    }


class BikeService:
    def __init__(self, root, *, config=None, runtime_dir=None, runner=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.config = config or BikeConfig()
        self.runtime_dir = runtime_dir or os.environ.get("HW7_SHARED_RUNTIME_DIR")
        self.runner = runner
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bike-run")
        self.slots = threading.BoundedSemaphore(1)
        self.processes = set()
        self.lock = threading.Lock()
        self.closed = False

    def submit(self, user_id, csv_bytes, pricing_url):
        parse_trips(csv_bytes)
        official_url(pricing_url)
        with self.lock:
            if self.closed:
                raise ServiceBusy("The bike service has stopped. Try again after server restart.")
            if not self.slots.acquire(blocking=False):
                raise ServiceBusy("One run is already active or pending. Wait for it to finish.")
            try:
                if self.runner is None and not self.runtime_dir:
                    raise ServiceBusy("The server needs its shared model runtime lease configured.")
                run_id = uuid4().hex
                parent = self.root / str(int(user_id))
                parent.mkdir(exist_ok=True, mode=0o700)
                directory = parent / run_id
                directory.mkdir(mode=0o700)
                request = {
                    "run_id": run_id,
                    "user_id": int(user_id),
                    "pricing_url": pricing_url,
                    "configuration": asdict(self.config),
                    "runtime_dir": str(self.runtime_dir) if self.runtime_dir else None,
                }
                (directory / "input.csv").write_bytes(csv_bytes)
                (directory / "input.csv").chmod(0o600)
                write_json(directory / "request.json", request)
                write_json(directory / "state.json", {"status": "queued", "error": None})
                self.pool.submit(self._perform, directory, request)
            except BaseException:
                self.slots.release()
                raise
        return {"run_id": run_id, "status": "queued"}

    def _perform(self, directory, request):
        try:
            final_status = "completed"
            if self.closed:
                write_json(
                    directory / "state.json",
                    {"status": "failed", "error": "Server stopped before this queued run began."},
                )
                return
            write_json(directory / "state.json", {"status": "running", "error": None})
            if self.runner:
                result = self.runner(directory, request)
            else:

                def started(process):
                    with self.lock:
                        self.processes.add(process)
                        if self.closed and process.poll() is None:
                            try:
                                os.killpg(process.pid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass

                def ended(process):
                    with self.lock:
                        self.processes.discard(process)

                execution = run_child(
                    [
                        sys.executable,
                        "scripts/hw07/bike_worker.py",
                        "--request",
                        str(directory / "request.json"),
                    ],
                    directory,
                    timeout=self.config.max_seconds,
                    on_start=started,
                    on_end=ended,
                )
                if (
                    execution["timed_out"]
                    or execution["returncode"] != 0
                    or not (directory / "result.json").exists()
                ):
                    result = interrupted_result(
                        directory,
                        request,
                        timed_out=execution["timed_out"],
                        latency_ms=execution["latency_ms"],
                    )
                    worker_state = json.loads((directory / "state.json").read_text())
                    if (
                        not execution["timed_out"]
                        and execution["returncode"] == 2
                        and worker_state.get("status") == "failed"
                        and worker_state.get("error") == RUNTIME_BUSY_ERROR
                    ):
                        final_status = "failed"
                        result["error"] = RUNTIME_BUSY_ERROR
                        result["verification"]["failures"] = ["runtime.busy"]
                else:
                    result = json.loads((directory / "result.json").read_text())
            write_json(directory / "result.json", result)
            write_json(
                directory / "state.json", {"status": final_status, "error": result.get("error")}
            )
        except Exception:
            write_json(
                directory / "state.json",
                {
                    "status": "failed",
                    "error": "Run failed; uploaded data and the private trace remain isolated to this account.",
                },
            )
        finally:
            self.slots.release()

    def get(self, user_id, run_id):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise FileNotFoundError()
        directory = self.root / str(int(user_id)) / run_id
        if not (directory / "request.json").is_file():
            raise FileNotFoundError()
        state = json.loads((directory / "state.json").read_text())
        result = None
        if state["status"] in {"completed", "failed"} and (directory / "result.json").is_file():
            result = json.loads((directory / "result.json").read_text())
            result.pop("trace", None)
        events = [
            e
            for e in read_trace(directory)
            if e["event"] in {"tool_request", "tool_result", "tool_rejected"}
        ]
        return {"run_id": run_id, **state, "events": events, "result": result}

    def close(self):
        with self.lock:
            self.closed = True
            for process in list(self.processes):
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
        self.pool.shutdown(wait=True, cancel_futures=False)
