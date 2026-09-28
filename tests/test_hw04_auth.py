"""Persistent cookie/session behavior on real MySQL with a controlled UTC clock."""
import base64
from datetime import timedelta
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
import pytest
from sqlalchemy import select

from web_application.main import create_app
from web_application.models import Rental, SessionToken
from web_application.session_store import COOKIE_NAME


RENTAL_OPERATIONS = [
    ("get", "/api/rentals", None),
    ("get", "/api/rentals/1", None),
    ("post", "/api/rentals", "create"),
    ("put", "/api/rentals/1", "update"),
    ("delete", "/api/rentals/1", None),
    ("delete", "/api/rentals/highest", None),
]


def login(client, user, **changes):
    return client.post("/api/auth/login", json={
        "email": user["email"], "password": user["password"], **changes})


def replay(app, token, cookie_name=COOKIE_NAME, path="/api/auth/me"):
    """A fresh cookie jar proves server revocation rather than local deletion."""
    with TestClient(app, base_url="https://testserver") as other:
        return other.get(path, headers={"Cookie": f"{cookie_name}={token}"})


def assert_denied(response):
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert isinstance(response.json()["detail"], str)
    assert "location" not in response.headers


def test_login_normalizes_email_and_returns_only_public_user(hw4_client, hw4_user, hw4_session_factory, hw4_clock):
    response = login(hw4_client, hw4_user, email=f'  {hw4_user["email"].upper()}  ')
    expected = {key: hw4_user[key] for key in ("id", "name", "email")}
    assert response.status_code == 200
    assert response.json() == {"user": expected}
    token = hw4_client.cookies[COOKIE_NAME]
    assert len(token) >= 32
    assert token not in response.text
    assert hw4_user["password"] not in response.text
    assert hw4_user["email"] not in token
    cookie = response.headers["set-cookie"].lower()
    for attribute in ("httponly", "; secure", "samesite=lax", "path=/", "max-age=3600"):
        assert attribute in cookie
    with hw4_session_factory() as db:
        stored = db.get(SessionToken, token)
        assert stored is not None and stored.user_id == hw4_user["id"]
        assert stored.created_at == stored.last_activity_at == hw4_clock()
        assert stored.expires_at == hw4_clock() + timedelta(seconds=3600)
    assert hw4_client.get("/api/auth/me").json() == {"user": expected}


@pytest.mark.parametrize("kind", ["wrong_password", "unknown_email"])
def test_invalid_credentials_create_no_session(hw4_client, hw4_user, hw4_session_factory, kind):
    changes = {"password": "incorrect"} if kind == "wrong_password" else {"email": f"missing-{uuid4().hex}@example.com"}
    response = login(hw4_client, hw4_user, **changes)
    assert_denied(response)
    assert COOKIE_NAME not in hw4_client.cookies
    with hw4_session_factory() as db:
        assert db.scalar(select(SessionToken.id).where(SessionToken.user_id == hw4_user["id"])) is None


@pytest.mark.parametrize("payload", [
    {"email": "bad-email", "password": "x"},
    {"email": "valid@example.com", "password": ""},
    {"email": "valid@example.com", "password": "x", "id": 1},
])
def test_invalid_login_schema_returns_422(hw4_client, payload):
    response = hw4_client.post("/api/auth/login", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize("state", ["missing", "expired"])
@pytest.mark.parametrize("method,path,body", RENTAL_OPERATIONS)
def test_every_rental_operation_rejects_missing_and_expired_login(
    hw4_client, hw4_user, hw4_clock, hw4_session_factory, rental_payload, state, method, path, body,
):
    with hw4_session_factory() as db:
        before = list(db.scalars(select(Rental.id).order_by(Rental.id)))
    if state == "expired":
        assert login(hw4_client, hw4_user).status_code == 200
        hw4_clock.advance(300)
    payload = rental_payload if body == "create" else {
        "listingTitle": "Denied update", "propertyAddress": "42 New Street"}
    response = hw4_client.request(method, path, **({"json": payload} if body else {}))
    assert_denied(response)
    with hw4_session_factory() as db:
        assert list(db.scalars(select(Rental.id).order_by(Rental.id))) == before


def test_logout_revokes_copied_cookie_in_fresh_client(hw4_logged_in, hw4_app, hw4_session_factory):
    token = hw4_logged_in.cookies[COOKIE_NAME]
    response = hw4_logged_in.post("/api/auth/logout")
    assert response.status_code == 204 and response.content == b""
    assert COOKIE_NAME not in hw4_logged_in.cookies
    assert "max-age=0" in response.headers["set-cookie"].lower()
    with hw4_session_factory() as db:
        assert db.get(SessionToken, token) is None
    assert_denied(replay(hw4_app, token))
    assert hw4_logged_in.post("/api/auth/logout").status_code == 204


def test_login_rotation_revokes_previous_cookie(hw4_logged_in, hw4_user, hw4_app, hw4_session_factory):
    first = hw4_logged_in.cookies[COOKIE_NAME]
    assert login(hw4_logged_in, hw4_user).status_code == 200
    second = hw4_logged_in.cookies[COOKIE_NAME]
    assert first != second
    assert_denied(replay(hw4_app, first))
    assert replay(hw4_app, second).status_code == 200
    with hw4_session_factory() as db:
        assert list(db.scalars(select(SessionToken.id).where(SessionToken.user_id == hw4_user["id"]))) == [second]


def test_failed_relogin_revokes_previous_session(hw4_logged_in, hw4_user, hw4_app):
    first = hw4_logged_in.cookies[COOKIE_NAME]
    assert_denied(login(hw4_logged_in, hw4_user, password="incorrect"))
    assert_denied(replay(hw4_app, first))


def test_idle_activity_at_299_999_seconds_is_accepted_and_recorded(hw4_logged_in, hw4_clock, hw4_session_factory):
    token = hw4_logged_in.cookies[COOKIE_NAME]
    original_expiry = hw4_clock() + timedelta(seconds=3600)
    hw4_clock.advance(299.999)
    assert hw4_logged_in.get("/api/rentals").status_code == 200
    with hw4_session_factory() as db:
        stored = db.get(SessionToken, token)
        assert stored.last_activity_at == hw4_clock()
        assert stored.expires_at == original_expiry
    hw4_clock.advance(299.999)
    assert hw4_logged_in.get("/api/auth/me").status_code == 200
    hw4_clock.advance(300)
    assert_denied(hw4_logged_in.get("/api/auth/me"))


def test_exact_idle_boundary_rejects_and_removes_session(hw4_logged_in, hw4_clock, hw4_session_factory, hw4_app):
    token = hw4_logged_in.cookies[COOKIE_NAME]
    hw4_clock.advance(300)
    assert_denied(replay(hw4_app, token))
    with hw4_session_factory() as db:
        assert db.get(SessionToken, token) is None


def test_activity_cannot_extend_absolute_lifetime(hw4_logged_in, hw4_clock, hw4_session_factory):
    token = hw4_logged_in.cookies[COOKIE_NAME]
    initial = hw4_clock()
    for _ in range(12):
        hw4_clock.advance(299)
        assert hw4_logged_in.get("/api/auth/me").status_code == 200
    hw4_clock.advance(11.999)
    assert hw4_clock() == initial + timedelta(seconds=3599.999)
    assert hw4_logged_in.get("/api/auth/me").status_code == 200
    with hw4_session_factory() as db:
        assert db.get(SessionToken, token).expires_at == initial + timedelta(seconds=3600)
    hw4_clock.advance(0.001)
    assert_denied(hw4_logged_in.get("/api/auth/me"))


def test_session_and_rental_survive_a_new_application_instance(
    hw4_logged_in, hw4_session_factory, hw4_clock, hw4_user, rental_payload, tmp_path,
):
    response = hw4_logged_in.post("/api/rentals", json=rental_payload)
    assert response.status_code == 201
    row = response.json()
    token = hw4_logged_in.cookies[COOKIE_NAME]
    restarted = create_app(session_factory=hw4_session_factory, clock=hw4_clock,
                           frontend_dist=tmp_path / "other-missing-dist")
    assert replay(restarted, token).json()["user"]["id"] == hw4_user["id"]
    assert replay(restarted, token, path=f'/api/rentals/{row["id"]}').json() == row


@pytest.mark.parametrize("token", ["garbage", "not.valid.signature", "", "e30=.invalid.invalid"])
def test_forged_cookie_never_authenticates(hw4_app, token):
    assert_denied(replay(hw4_app, token))


@pytest.mark.parametrize("cookie_name", ["session", COOKIE_NAME])
def test_old_hw3_signed_cookie_is_never_accepted(hw4_app, cookie_name):
    payload = base64.b64encode(json.dumps({"user": "admin", "sid": "old-session-id"}).encode())
    old_cookie = TimestampSigner("test-only-old-hw3-secret").sign(payload).decode()
    assert_denied(replay(hw4_app, old_cookie, cookie_name=cookie_name))
