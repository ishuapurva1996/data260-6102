"""HTTP ownership checks use injected identity; live JWT acceptance is separate."""

import time
from types import SimpleNamespace

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from web_application.main import create_app
from web_application.routers.auth import require_user

from src.bikeshare.service import BikeService, run_child
from tests.test_hw07_bike_agent import csv_input


def identity(authorization: str = Header()):
    return SimpleNamespace(id=int(authorization.removeprefix("Bearer ")))


def completed(directory, request):
    return {
        "run_id": request["run_id"],
        "user_id": request["user_id"],
        "decision": "Pay Per Ride/Minute",
        "verification": {"passed": True},
        "metrics": {"stop_reason": "success"},
    }


@pytest.fixture
def client(tmp_path):
    service = BikeService(tmp_path, runner=completed)
    app = create_app(bike_service=service)
    app.dependency_overrides[require_user] = identity
    with TestClient(app) as client:
        yield client


def test_uploaded_runs_are_accessible_only_to_authenticated_owner(client):
    response = client.post(
        "/api/bikeshare/runs",
        headers={"Authorization": "Bearer 11"},
        files={"file": ("source.csv", csv_input(), "text/csv")},
        data={"pricing_url": "https://capitalbikeshare.com/pricing"},
    )
    assert response.status_code == 202
    path = "/api/bikeshare/runs/" + response.json()["run_id"]
    for _ in range(100):
        own = client.get(path, headers={"Authorization": "Bearer 11"})
        if own.json()["status"] in {"completed", "failed"}:
            break
        time.sleep(0.005)
    assert own.json()["result"]["user_id"] == 11
    assert client.get(path, headers={"Authorization": "Bearer 12"}).status_code == 404
    assert (
        client.get(
            "/api/bikeshare/runs/../../request.json", headers={"Authorization": "Bearer 11"}
        ).status_code
        == 404
    )


def test_invalid_policy_host_and_undeclared_accounts_do_not_create_run(client):
    files = {"file": ("source.csv", csv_input(), "text/csv")}
    response = client.post(
        "/api/bikeshare/runs",
        headers={"Authorization": "Bearer 11"},
        files=files,
        data={"pricing_url": "http://127.0.0.1/private"},
    )
    assert response.status_code == 422
    response = client.post(
        "/api/bikeshare/runs",
        headers={"Authorization": "Bearer 11"},
        files={"file": ("bad.csv", b"ride_id\na\n", "text/csv")},
        data={"pricing_url": "https://capitalbikeshare.com/pricing"},
    )
    assert response.status_code == 422


def test_missing_bearer_is_401_without_reading_uploaded_contents(tmp_path):
    with TestClient(create_app(bike_service=BikeService(tmp_path, runner=completed))) as client:
        assert client.get("/api/bikeshare/runs/" + "a" * 32).status_code == 401
        assert client.post("/api/bikeshare/runs").status_code == 401


def test_process_wall_deadline_stops_a_real_child(tmp_path):
    import sys

    began = time.monotonic()
    result = run_child(
        [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, timeout=0.15
    )
    assert result["timed_out"]
    assert time.monotonic() - began < 3


def test_unauthenticated_upload_is_denied_before_multipart_parsing(tmp_path, monkeypatch):
    from starlette.formparsers import MultiPartParser

    async def forbidden_parse(self):
        raise AssertionError("Unauthenticated body reached multipart parsing")

    monkeypatch.setattr(MultiPartParser, "parse", forbidden_parse)
    with TestClient(create_app(bike_service=BikeService(tmp_path, runner=completed))) as c:
        response = c.post(
            "/api/bikeshare/runs",
            headers={"Content-Type": "multipart/form-data; boundary=part"},
            content=b"--part--\r\n",
        )
    assert response.status_code == 401


def test_authenticated_chunked_multipart_is_bounded_before_spooling(client):
    def body():
        yield b'--part\r\nContent-Disposition: form-data; name="pricing_url"\r\n\r\n'
        for _ in range(90):
            yield b"x" * 65536
        yield b"\r\n--part--\r\n"

    response = client.post(
        "/api/bikeshare/runs",
        headers={
            "Authorization": "Bearer 11",
            "Content-Type": "multipart/form-data; boundary=part",
        },
        content=body(),
    )
    assert response.status_code == 413


def test_failed_run_initialization_does_not_reduce_queue_capacity(tmp_path, monkeypatch):
    import threading

    from src.bikeshare import service as module

    gate = threading.Event()

    def delayed(directory, request):
        gate.wait(timeout=2)
        return completed(directory, request)

    service = BikeService(tmp_path, runner=delayed)
    original = module.write_json

    def broken(path, value):
        raise OSError("controlled disk write failure")

    try:
        monkeypatch.setattr(module, "write_json", broken)
        with pytest.raises(OSError):
            service.submit(11, csv_input(), "https://capitalbikeshare.com/pricing")
        monkeypatch.setattr(module, "write_json", original)
        service.submit(11, csv_input(), "https://capitalbikeshare.com/pricing")
    finally:
        gate.set()
        service.close()
