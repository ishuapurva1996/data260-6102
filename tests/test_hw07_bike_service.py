"""Offline service lifecycle checks; no model, network, or database calls."""

import json
import threading
import time
from pathlib import Path

import pytest

from src.bikeshare import service as module
from src.bikeshare.service import BikeService, ServiceBusy
from tests.test_hw07_bike_agent import csv_input

PRICING_URL = "https://capitalbikeshare.com/pricing"
BUSY_ERROR = "The shared model runtime is busy. Try again after the active run finishes."


def completed(directory, request):
    return {
        "run_id": request["run_id"],
        "user_id": request["user_id"],
        "decision": None,
        "verification": {"passed": False},
        "metrics": {"stop_reason": "human_review"},
    }


def terminal_state(service, run_id, *, require_result=False):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = service.get(11, run_id)
        if state["status"] in {"completed", "failed"} and (
            not require_result or state["result"] is not None
        ):
            return state
        time.sleep(0.005)
    pytest.fail("Controlled service did not reach a terminal state.")


def test_worker_busy_failure_keeps_specific_reason_and_terminal_metrics(tmp_path, monkeypatch):
    def busy_worker(command, directory, **kwargs):
        module.write_json(directory / "state.json", {"status": "failed", "error": BUSY_ERROR})
        return {"timed_out": False, "returncode": 2, "latency_ms": 17.2}

    monkeypatch.setattr(module, "run_child", busy_worker)
    service = BikeService(tmp_path, runtime_dir=tmp_path / "controlled-lease")
    try:
        submitted = service.submit(11, csv_input(), PRICING_URL)
        state = terminal_state(service, submitted["run_id"], require_result=True)
        assert state["status"] == "failed"
        assert state["error"] == BUSY_ERROR
        assert state["result"]["error"] == BUSY_ERROR
        assert state["result"]["verification"] == {
            "passed": False,
            "failures": ["runtime.busy"],
        }
        assert state["result"]["decision"] is None
        assert state["result"]["metrics"]["stop_reason"] == "human_review"
        assert state["result"]["metrics"]["model_requests"] == 0
        assert state["result"]["metrics"]["latency_ms"] == 17.2
    finally:
        service.close()


def test_only_one_job_is_admitted_until_the_active_run_finishes(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def blocked(directory, request):
        entered.set()
        assert release.wait(timeout=2)
        return completed(directory, request)

    service = BikeService(tmp_path, runner=blocked)
    try:
        run = service.submit(11, csv_input(), PRICING_URL)
        assert entered.wait(timeout=1)
        with pytest.raises(ServiceBusy, match="One run is already active or pending"):
            service.submit(12, csv_input(), PRICING_URL)
        assert len(list(tmp_path.glob("*/*/request.json"))) == 1
        release.set()
        terminal_state(service, run["run_id"])
    finally:
        release.set()
        service.close()


def test_shutdown_drains_an_admitted_pending_run_to_failed_state(tmp_path, monkeypatch):
    occupied, release, shutting_down = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    called = []

    def occupy_executor():
        occupied.set()
        assert release.wait(timeout=2)

    def runner(directory, request):
        called.append(request["run_id"])
        return completed(directory, request)

    service = BikeService(tmp_path, runner=runner)
    original_shutdown = service.pool.shutdown

    def observed_shutdown(**kwargs):
        shutting_down.set()
        return original_shutdown(**kwargs)

    monkeypatch.setattr(service.pool, "shutdown", observed_shutdown)
    service.pool.submit(occupy_executor)
    assert occupied.wait(timeout=1)
    run = service.submit(11, csv_input(), PRICING_URL)
    closer = threading.Thread(target=service.close)
    try:
        closer.start()
        assert shutting_down.wait(timeout=1)
        release.set()
        closer.join(timeout=2)
        assert not closer.is_alive()
        state = service.get(11, run["run_id"])
        assert state["status"] == "failed"
        assert "stopped before this queued run began" in state["error"]
        assert not called
        with pytest.raises(ServiceBusy, match="stopped"):
            service.submit(11, csv_input(), PRICING_URL)
    finally:
        release.set()
        closer.join(timeout=2)
        service.close()


@pytest.mark.parametrize("failure_point", ["mkdir", "write_json", "executor_submit"])
def test_initialization_errors_release_admission_capacity(tmp_path, monkeypatch, failure_point):
    release = threading.Event()

    def blocked(directory, request):
        assert release.wait(timeout=2)
        return completed(directory, request)

    def disk_error(*args, **kwargs):
        raise OSError("Controlled initialization failure")

    service = BikeService(tmp_path, runner=blocked)
    try:
        with monkeypatch.context() as patch:
            if failure_point == "mkdir":
                original_mkdir = Path.mkdir

                def mkdir(path, *args, **kwargs):
                    if path == tmp_path / "11":
                        disk_error()
                    return original_mkdir(path, *args, **kwargs)

                patch.setattr(Path, "mkdir", mkdir)
            elif failure_point == "write_json":
                patch.setattr(module, "write_json", disk_error)
            else:
                patch.setattr(service.pool, "submit", disk_error)
            for _ in range(2):
                with pytest.raises(OSError, match="Controlled initialization failure"):
                    service.submit(11, csv_input(), PRICING_URL)
        run = service.submit(11, csv_input(), PRICING_URL)
        with pytest.raises(ServiceBusy):
            service.submit(12, csv_input(), PRICING_URL)
        release.set()
        terminal_state(service, run["run_id"])
    finally:
        release.set()
        service.close()


def test_failed_worker_result_still_charges_unreported_model_reservation(tmp_path):
    trace = {
        "event": "model_request",
        "reservation": {"total_tokens": 123},
    }
    (tmp_path / "trace.jsonl").write_text(json.dumps(trace) + "\n")
    result = module.interrupted_result(
        tmp_path, {"run_id": "a" * 32, "user_id": 11}, timed_out=False, latency_ms=19.5
    )
    assert result["metrics"]["budget"]["charged_tokens"] == 123
    assert result["metrics"]["budget"]["unknown_usage_calls"] == 1
    assert result["metrics"]["total_tokens"] is None
    assert result["metrics"]["latency_ms"] == 19.5
