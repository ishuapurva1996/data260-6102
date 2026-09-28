"""Serving plumbing checks use a tiny fixture build; no real UI or DB claim."""
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from web_application.main import create_app


ROUTES = ["/", "/login", "/create", "/update?id=17", "/delete?id=17"]


@pytest.fixture
def fixture_build(tmp_path):
    dist = tmp_path / "frontend-dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<!doctype html><html><div id="root">Fixture React entry</div></html>')
    (dist / "assets" / "fixture.js").write_text('console.log("fixture asset");')
    return dist


@pytest.mark.parametrize("route", ROUTES)
def test_missing_build_has_explicit_503_development_message(tmp_path, route):
    with TestClient(create_app(frontend_dist=tmp_path / "missing"), base_url="https://testserver") as client:
        response = client.get(route)
        assert response.status_code == 503
        assert "React build is missing" in response.text
        assert "npm run build" in response.text
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("route", ROUTES)
def test_fixture_build_supports_direct_frontend_navigation(fixture_build, route):
    with TestClient(create_app(frontend_dist=fixture_build), base_url="https://testserver") as client:
        response = client.get(route)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.text == (fixture_build / "index.html").read_text()
        assert response.headers["cache-control"] == "no-store"


def test_fixture_assets_docs_api_and_legacy_redirect(fixture_build):
    with TestClient(create_app(frontend_dist=fixture_build), base_url="https://testserver") as client:
        asset = client.get("/assets/fixture.js")
        assert asset.status_code == 200 and "fixture asset" in asset.text
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/api/health").json() == {"status": "ok", "service": "Rental Housing Listings"}
        unknown = client.get("/api/definitely-not-a-real-route")
        assert unknown.status_code == 404
        assert unknown.headers["content-type"].startswith("application/json")
        assert "Fixture React entry" not in unknown.text
        assert unknown.json() == {"detail": "Not Found"}
        redirect = client.get("/dashboard", follow_redirects=False)
        assert redirect.status_code == 303 and redirect.headers["location"] == "/"
        assert client.get("/logout").status_code == 404
        assert client.post("/login", data={"username": "admin", "password": "password"}).status_code == 405


def test_missing_build_does_not_break_api_docs_or_unknown_asset(tmp_path):
    with TestClient(create_app(frontend_dist=tmp_path / "missing"), base_url="https://testserver") as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/assets/missing.js").status_code == 404
        response = client.get("/api/unknown")
        assert response.status_code == 404 and response.json() == {"detail": "Not Found"}


def test_arbitrary_main_module_import_and_other_working_directory(monkeypatch, tmp_path, fixture_build):
    source = Path(__file__).resolve().parents[1] / "code/web_application/main.py"
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("arbitrary_hw4_application_import", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TestClient(module.create_app(frontend_dist=fixture_build), base_url="https://testserver") as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_idle_timeout_is_rejected(timeout):
    with pytest.raises(ValueError, match="idle timeout"):
        create_app(idle_timeout=timeout)


def test_malformed_login_errors_do_not_echo_password(tmp_path):
    sentinel = "sensitive-password-never-echo-6102"
    with TestClient(create_app(frontend_dist=tmp_path), base_url="https://testserver") as client:
        response = client.post("/api/auth/login", json={"email": "invalid", "password": sentinel})
        assert response.status_code == 422
        assert sentinel not in response.text
        assert isinstance(response.json()["detail"], list)
        for error in response.json()["detail"]:
            assert "input" not in error
            assert "ctx" not in error
