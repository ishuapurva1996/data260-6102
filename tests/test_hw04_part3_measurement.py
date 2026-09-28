"""Unit fixtures validate the harness; they are not performance evidence."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/hw04/part3"


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = load_module("benchmark")
summarize = load_module("summarize")


def payload(size):
    return [{"id": i, "listingTitle": f"Rental {i}",
             "propertyAddress": f"{i} Example Street", "submitterEmail": "unit@example.com",
             "description": "A description longer than twenty-six characters.",
             "propertyType": "apartment", "termsAccepted": True,
             "manager": {"id": i, "name": f"Manager {i}"}} for i in range(1, size + 1)]


def fixture_rows():
    rows = []
    for size in (10, 50, 200):
        for iteration in range(1, 31):
            for version in ("naive", "fixed"):
                rows.append({"run_id": "unit-fixture", "timestamp": "2026-09-28T00:00:00Z",
                             "code_revision": "a" * 40, "dirty": False,
                             "config_sha256": "b" * 64, "page_size": size,
                             "version": version, "iteration": iteration, "phase": "measured", "http_status": 200,
                             "returned_count": size, "elapsed_ms": iteration * (2 if version == "naive" else 1),
                             "total_sql": size + 4 if version == "naive" else 4,
                             "data_sql": size + 1 if version == "naive" else 1,
                             "payload_sha256": str(size).zfill(64), "valid": True, "error": None})
    return rows


def test_linear_percentiles_and_speedups_from_known_fixture():
    result = summarize.summarize_rows(fixture_rows())
    fixed = next(row for row in result["groups"] if row["page_size"] == 10 and row["version"] == "fixed")
    assert fixed["samples"] == 30
    assert fixed["p50_ms"] == 15.5
    assert fixed["p95_ms"] == pytest.approx(28.55)
    assert fixed["p99_ms"] == pytest.approx(29.71)
    assert fixed["total_sql_min"] == fixed["total_sql_max"] == 4
    assert result["speedups"][0]["p50_ratio"] == 2
    assert result["speedups"][0]["p95_ratio"] == 2
    assert result["speedups"][0]["p99_ratio"] == 2


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(),
    lambda rows: rows[0].update(http_status=401),
    lambda rows: rows[0].update(returned_count=9),
    lambda rows: rows[0].update(payload_sha256="c" * 64),
    lambda rows: rows[0].update(total_sql=None),
    lambda rows: rows[0].update(elapsed_ms=float("nan")),
    lambda rows: rows[0].update(iteration=2),
    lambda rows: rows[0].update(run_id="another-attempt"),
    lambda rows: rows[0].update(valid=False),
    lambda rows: rows[0].update(data_sql=1),
    lambda rows: rows[0].update(phase="warmup"),
])
def test_summary_rejects_invalid_or_incomplete_evidence(mutation):
    rows = fixture_rows()
    mutation(rows)
    with pytest.raises(ValueError):
        summarize.summarize_rows(rows)


def mock_client(failure=None, fail_after=None):
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.path == "/api/auth/login":
            assert json.loads(request.content) == {"email": "unit@example.com", "password": "test-only"}
            if failure == "login":
                return httpx.Response(401, json={"detail": "Invalid credentials"})
            return httpx.Response(200, json={"user": {"id": 1}},
                                  headers={"Set-Cookie": "s6102_session=test-only; Secure; HttpOnly; Path=/"})
        assert "s6102_session=test-only" in request.headers["cookie"]
        size = int(request.url.params["page_size"])
        version = request.url.path.rsplit("/", 1)[1]
        headers = {"X-SQL-Statements": str(size + 4 if version == "naive" else 4),
                   "X-Data-SQL-Statements": str(size + 1 if version == "naive" else 1)}
        body = payload(size)
        status = 200
        if failure and (fail_after is None or len(calls) > fail_after):
            if failure == "unauthorized":
                status = 401
            elif failure == "status":
                status = 500
            elif failure == "count":
                body.pop()
            elif failure == "mismatch" and version == "fixed":
                body[0]["manager"]["name"] = "Changed manager"
            elif failure == "header":
                headers.pop("X-SQL-Statements")
        return httpx.Response(status, json=body, headers=headers)

    return httpx.Client(base_url="https://localhost:8702", transport=httpx.MockTransport(respond)), calls


def run(client, tmp_path):
    return benchmark.run_benchmark(client, tmp_path, email="unit@example.com", password="test-only",
                                   metadata={"code_revision": "a" * 40, "dirty": False, "config": {}}, warmups=1)


def test_runner_excludes_login_preflight_and_warmups_and_alternates(tmp_path):
    client, calls = mock_client()
    with client:
        directory = run(client, tmp_path)
    rows = [json.loads(line) for line in (directory / "requests.jsonl").read_text().splitlines()]
    assert len(rows) == 180
    assert len(calls) == 1 + 6 + 6 + 180
    assert [row["version"] for row in rows] == ["naive", "fixed"] * 90
    assert summarize.summarize_rows(rows)["request_count"] == 180
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["status"] == "success"
    assert manifest["measured_requests"] == 180
    assert len((directory / "preflight.jsonl").read_text().splitlines()) == 6
    assert len((directory / "warmups.jsonl").read_text().splitlines()) == 6
    assert "test-only" not in "".join(p.read_text() for p in directory.iterdir())


@pytest.mark.parametrize("failure", ["login", "unauthorized", "status", "count", "mismatch", "header"])
def test_runner_preserves_failed_preflight_separately(tmp_path, failure):
    client, _ = mock_client(failure)
    with client, pytest.raises(benchmark.BenchmarkError) as error:
        run(client, tmp_path)
    directory = error.value.attempt_path
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["measured_requests"] == 0
    assert (directory / "requests.jsonl").read_text() == ""


def test_runner_preserves_partial_attempt_and_never_overwrites(tmp_path):
    client, _ = mock_client("status", fail_after=15)
    with client, pytest.raises(benchmark.BenchmarkError) as error:
        run(client, tmp_path)
    failed = error.value.attempt_path
    before = (failed / "requests.jsonl").read_text()
    assert len(before.splitlines()) == 3
    assert json.loads(before.splitlines()[-1])["valid"] is False
    client, _ = mock_client()
    with client:
        succeeded = run(client, tmp_path)
    assert succeeded != failed
    assert (failed / "requests.jsonl").read_text() == before


def test_config_rejects_secrets_and_base_url_rejects_non_https():
    with pytest.raises(ValueError):
        benchmark.validate_config({"database": "s6102_rel", "password": "must-not-record"})
    with pytest.raises(ValueError):
        benchmark.validate_base_url("http://localhost:8702")
    with pytest.raises(ValueError):
        benchmark.validate_base_url("https://user:password@localhost:8702")
