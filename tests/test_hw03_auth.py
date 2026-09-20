"""HW3 Part 1 auth behavior, including deliberately replayed signed cookies."""

import base64
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner


APP_PATH = Path(__file__).resolve().parents[1] / "code/web_application/main.py"
spec = importlib.util.spec_from_file_location("hw03_auth_application", APP_PATH)
web_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_app)
TEST_SECRET = "test-only-hw03-signing-key"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def app(clock):
    return web_app.create_app(secret_key=TEST_SECRET, idle_timeout=300, clock=clock)


@pytest.fixture
def client(app):
    with TestClient(app, base_url="https://testserver") as browser:
        yield browser


def login(client, username="admin", password="password"):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def payload_from_cookie(cookie):
    return json.loads(base64.b64decode(cookie.split(".")[0]))


def signed_cookie(payload):
    data = base64.b64encode(json.dumps(payload).encode())
    return TimestampSigner(TEST_SECRET).sign(data).decode()


def replay(app, cookie, path="/dashboard"):
    """Use a new client so its cookie jar cannot hide a server revocation bug."""
    with TestClient(app, base_url="https://testserver") as attacker:
        return attacker.get(path, headers={"Cookie": f"session={cookie}"}, follow_redirects=False)


def assert_denied(response):
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert response.headers["cache-control"] == "no-store"


def test_anonymous_home_retains_rental_controls_and_login(client):
    home = client.get("/")
    assert home.status_code == 200
    assert home.headers["cache-control"] == "no-store"
    assert 'href="/login"' in home.text
    assert "/static/styles.css" in home.text
    assert "/static/app.js" in home.text
    assert 'id="rentalForm"' in home.text
    assert 'href="/dashboard"' not in home.text
    assert_denied(client.get("/dashboard", follow_redirects=False))


def test_valid_login_cookie_attributes_and_authenticated_navigation(client):
    response = login(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert response.headers["cache-control"] == "no-store"
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "; secure" in header
    assert "samesite=lax" in header
    assert "max-age=3600" in header
    payload = payload_from_cookie(client.cookies["session"])
    assert set(payload) == {"user", "sid"}
    assert payload["user"] == "admin"
    assert len(payload["sid"]) >= 32
    assert "password" not in payload
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "admin" in dashboard.text
    assert dashboard.headers["cache-control"] == "no-store"
    home = client.get("/")
    assert 'href="/dashboard"' in home.text
    assert 'href="/logout"' in home.text


@pytest.mark.parametrize("method,path,authenticated,data,status,media_type", [
    ("post", "/login", False, {"username": "admin", "password": "password"}, 303, ""),
    ("post", "/login", False, {"username": "admin", "password": "wrong"}, 401, "text/html"),
    ("get", "/dashboard", False, None, 303, ""),
    ("get", "/dashboard", True, None, 200, "text/html"),
    ("get", "/logout", True, None, 303, ""),
])
def test_auth_openapi_matches_actual_status_and_content_type(
    client, app, method, path, authenticated, data, status, media_type,
):
    if authenticated:
        login(client)
    response = client.request(method, path, data=data, follow_redirects=False)
    assert response.status_code == status
    assert response.headers.get("content-type", "").split(";")[0] == media_type
    documented = app.openapi()["paths"][path][method]["responses"]
    assert str(response.status_code) in documented
    assert set(documented[str(status)].get("content", {})) == ({media_type} if media_type else set())
    if path in {"/login", "/logout"}:
        assert "200" not in documented


@pytest.mark.parametrize("username,password", [("admin", "wrong"), ("other", "password"), ("", "")])
def test_invalid_login_shows_alert_without_authentication(client, username, password):
    response = login(client, username, password)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert "alert" in response.text
    assert "Invalid username or password" in response.text
    assert_denied(client.get("/dashboard", follow_redirects=False))


def test_invalid_login_revokes_existing_session(client, app):
    login(client)
    old_cookie = client.cookies["session"]
    assert login(client, password="wrong").status_code == 401
    assert_denied(replay(app, old_cookie))


def test_logout_redirects_home_and_replay_of_copied_cookie_is_denied(client, app):
    login(client)
    copied_cookie = client.cookies["session"]
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert response.headers["cache-control"] == "no-store"
    assert 'href="/login"' in client.get("/").text
    assert_denied(replay(app, copied_cookie))


def test_expired_cookie_replay_is_denied_before_cookie_lifetime(client, app, clock):
    login(client)
    copied_cookie = client.cookies["session"]
    clock.advance(301)
    assert_denied(replay(app, copied_cookie))
    assert len(app.state.session_store) == 0


def test_exact_idle_boundary_is_rejected_before_refresh(client, clock):
    login(client)
    clock.advance(300)
    assert_denied(client.get("/dashboard", follow_redirects=False))


def test_activity_just_before_boundary_renews_session(client, clock):
    login(client)
    clock.advance(299.999)
    assert client.get("/dashboard").status_code == 200
    clock.advance(299.999)
    assert client.get("/dashboard").status_code == 200
    clock.advance(300)
    assert_denied(client.get("/dashboard", follow_redirects=False))


@pytest.mark.parametrize("path", ["/", "/login", "/dashboard"])
def test_authenticated_auth_page_access_refreshes_idle_time(client, clock, path):
    login(client)
    clock.advance(250)
    assert client.get(path).status_code == 200
    clock.advance(250)
    assert client.get("/dashboard").status_code == 200


@pytest.mark.parametrize("path", ["/api/rentals", "/static/app.js", "/static/styles.css"])
def test_background_api_and_static_requests_do_not_refresh_idle_time(client, clock, path):
    login(client)
    clock.advance(299)
    assert client.get(path).status_code == 200
    clock.advance(1)
    assert_denied(client.get("/dashboard", follow_redirects=False))


def test_login_rotates_identifier_and_revokes_replaced_cookie(client, app):
    login(client)
    first = client.cookies["session"]
    assert login(client).status_code == 303
    second = client.cookies["session"]
    assert payload_from_cookie(first)["sid"] != payload_from_cookie(second)["sid"]
    assert_denied(replay(app, first))
    assert replay(app, second).status_code == 200
    assert len(app.state.session_store) == 1


@pytest.mark.parametrize("payload", [
    {"user": "admin", "sid": "unknown-session-id"},
    {"user": "admin"}, {"sid": "missing-user"},
    {"user": "admin", "sid": []}, {"user": [], "sid": "some-id"},
    [], None, "not-a-session-map", 7,
])
def test_signed_unknown_or_malformed_session_data_never_authenticates(app, payload):
    assert_denied(replay(app, signed_cookie(payload)))


def test_registry_username_must_match_signed_username(client, app):
    login(client)
    payload = payload_from_cookie(client.cookies["session"])
    payload["user"] = "another-user"
    assert_denied(replay(app, signed_cookie(payload)))


@pytest.mark.parametrize("cookie", ["garbage", "not.valid.signature", "", "e30=.invalid.invalid"])
def test_malformed_cookie_never_authenticates(app, cookie):
    assert_denied(replay(app, cookie))


def test_tampered_signature_never_authenticates(client, app):
    login(client)
    original = client.cookies["session"]
    encoded, timestamp, signature = original.rsplit(".", 2)
    changed = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert_denied(replay(app, f"{encoded}.{timestamp}.{changed}"))


def test_new_app_instances_and_restart_do_not_accept_old_sessions(client, clock):
    login(client)
    cookie = client.cookies["session"]
    restarted_instance = web_app.create_app(secret_key=TEST_SECRET, clock=clock)
    assert_denied(replay(restarted_instance, cookie))


def test_auth_access_cleans_up_other_expired_sessions(app, clock):
    with TestClient(app, base_url="https://testserver") as first:
        login(first)
    clock.advance(150)
    with TestClient(app, base_url="https://testserver") as second:
        login(second)
        assert len(app.state.session_store) == 2
        clock.advance(150)
        assert second.get("/").status_code == 200
        assert len(app.state.session_store) == 1
    clock.advance(300)
    with TestClient(app, base_url="https://testserver") as anonymous:
        assert anonymous.get("/login").status_code == 200
    assert len(app.state.session_store) == 0


def test_routes_and_templates_work_with_arbitrary_import_and_other_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    other_spec = importlib.util.spec_from_file_location("arbitrary_auth_import", APP_PATH)
    other_module = importlib.util.module_from_spec(other_spec)
    other_spec.loader.exec_module(other_module)
    with TestClient(other_module.create_app(), base_url="https://testserver") as client:
        assert client.get("/").status_code == 200
        assert client.get("/login").status_code == 200
        assert login(client).status_code == 303
        assert client.get("/dashboard").status_code == 200
        assert client.get("/static/app.js").status_code == 200


def test_environment_timeout_and_signing_secret(monkeypatch, clock):
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("IDLE_TIMEOUT_SECONDS", "7")
    configured_app = web_app.create_app(clock=clock)
    with TestClient(configured_app, base_url="https://testserver") as client:
        login(client)
        payload = TimestampSigner(TEST_SECRET).unsign(client.cookies["session"])
        assert json.loads(base64.b64decode(payload))["user"] == "admin"
        clock.advance(7)
        assert_denied(client.get("/dashboard", follow_redirects=False))


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_timeout_must_be_positive_and_finite(timeout):
    with pytest.raises(ValueError, match="idle timeout"):
        web_app.create_app(idle_timeout=timeout)


def load_verifier():
    verifier_path = APP_PATH.parents[2] / "scripts/verify_hw03_part1.py"
    spec = importlib.util.spec_from_file_location("part1_verifier", verifier_path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    return verifier


def test_verifier_does_not_trust_overall_browser_pass_with_failed_check(tmp_path):
    verifier = load_verifier()
    checks = verifier.evidence_checks(tmp_path, {
        "status": "pass", "checks": [{"name": "logout replay", "status": "fail"}],
    })
    assert next(c for c in checks if c["name"] == "browser_individual_checks_passed")["passed"] is False


def test_verifier_reports_missing_screenshot(tmp_path):
    verifier = load_verifier()
    checks = verifier.evidence_checks(tmp_path, {
        "status": "pass", "checks": [{"name": "desktop", "status": "pass"}],
        "screenshots": [{"file": "missing.png"}],
    })
    assert next(c for c in checks if c["name"] == "screenshot_exists:missing.png")["passed"] is False


def test_verifier_exits_nonzero_when_auth_tests_fail(monkeypatch, tmp_path):
    from types import SimpleNamespace
    verifier = load_verifier()
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    auth = tmp_path / "code/web_application/routers/auth.py"
    auth.parent.mkdir(parents=True)
    auth.write_text("# test fixture\n")
    monkeypatch.setattr(verifier.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=1, stdout="FAILED auth replay check", stderr=""))
    monkeypatch.setattr(verifier.subprocess, "check_output", lambda *a, **kw: "test-revision")
    output = tmp_path / "verification.json"
    assert verifier.main(["--output", str(output)]) == 1
    result = json.loads(output.read_text())
    assert result["status"] == "fail"
    assert next(c for c in result["checks"] if c["name"] == "pytest_exit_status")["passed"] is False
    assert next(c for c in result["checks"] if c["name"] == "browser_evidence_readable")["passed"] is False


def test_verifier_uses_actual_replay_evidence_not_display_label(tmp_path):
    verifier = load_verifier()
    details = {"fresh_browser_context": True, "copied_cookie_actually_sent": True,
               "dashboard_response": {"status": 303, "headers": [{"name": "location", "value": "/login"}]}}
    evidence = {"status": "pass", "checks": [
        {"name": name, "status": "pass", "details": details}
        for name in ["desktop copied cookie after logout", "mobile copied cookie after logout", "copied cookie after idle time"]
    ]}
    checks = verifier.evidence_checks(tmp_path, evidence)
    assert next(c for c in checks if c["name"] == "browser_covers_replay")["passed"] is True
    details["copied_cookie_actually_sent"] = False
    checks = verifier.evidence_checks(tmp_path, evidence)
    assert next(c for c in checks if c["name"] == "browser_covers_replay")["passed"] is False
