"""JWT/role integration against real MySQL; each test rolls its rows back.

HTTP uses TestClient, not a listening server. Live HTTP/Mongo/model acceptance
is recorded separately by scripts/hw07/part1_acceptance.py.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from web_application.main import create_app
from web_application.models import User

SECRET = "test-only-hw7-key-6102-" + "x" * 32


@pytest.fixture
def accounts(hw4_session_factory, hw4_password_hash):
    result = {}
    with hw4_session_factory() as db:
        for role in ("reader", "writer", "moderator"):
            name = f"hw7_{role}_{uuid4().hex[:12]}"
            row = User(
                name="HW7 test",
                email=f"{name}@example.com",
                username=name,
                password_hash=hw4_password_hash,
                role=role,
            )
            db.add(row)
            db.flush()
            result[role] = {"id": row.id, "username": name, "password": "local-test-password-6102"}
        db.commit()
    return result


@pytest.fixture
def client(hw4_session_factory, monkeypatch):
    monkeypatch.setenv("HW7_JWT_SECRET", SECRET)
    with TestClient(create_app(session_factory=hw4_session_factory)) as value:
        yield value


def login(client, account):
    return client.post("/auth/login", json={k: account[k] for k in ("username", "password")})


def bearer(client, account):
    response = login(client, account)
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.mark.parametrize("role", ["reader", "writer", "moderator"])
def test_login_and_identity_are_public_and_no_cookie_is_issued(client, accounts, role):
    response = login(client, accounts[role])
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    assert body["access_token"].count(".") == 2
    assert "set-cookie" not in response.headers
    headers = {"Authorization": "Bearer " + body["access_token"]}
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["role"] == role
    assert me.json()["user"]["username"] == accounts[role]["username"]
    assert me.json()["user"]["id"] == accounts[role]["id"]
    assert "password" not in me.text and "password_hash" not in me.text
    assert me.headers["cache-control"] == "no-store"


def test_unknown_username_and_wrong_password_have_same_401(client, accounts):
    for payload in (
        {**accounts["reader"], "password": "wrong-password"},
        {**accounts["reader"], "username": "nonexistent_hw7_user"},
    ):
        response = login(client, payload)
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid username or password."}
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ["/auth/me", "/api/rentals", "/api/property-managers"])
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Cookie": "s6102_session=old-cookie"},
        {"Authorization": "Bearer corrupted.token.signature"},
        {"Authorization": "Basic abc"},
    ],
)
def test_missing_invalid_and_cookie_only_credentials_are_401(client, path, headers):
    response = client.get(path, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_live_probe_handles_an_empty_historical_session_table(client):
    from scripts.hw07.part1_acceptance import legacy_cookie_probe

    label, headers = legacy_cookie_probe(None)
    assert label == "synthetic legacy cookie alone "
    assert client.get("/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize(
    "changes,algorithm,key",
    [
        ({"exp": 1}, "HS256", SECRET),
        ({"sub": "not-an-id"}, "HS256", SECRET),
        ({"sub": "999999999"}, "HS256", SECRET),
        ({"exp": None}, "HS256", SECRET),
        ({"sub": None}, "HS256", SECRET),
        ({"aud": "other-app"}, "HS256", SECRET),
        ({}, "HS384", SECRET),
        ({}, "HS256", "wrong-key-" + "z" * 40),
    ],
)
def test_unusable_jwts_are_401(client, accounts, changes, algorithm, key):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(accounts["reader"]["id"]),
        "iat": now,
        "exp": now + timedelta(minutes=15),
        "iss": "s6102",
        "aud": "s6102-rentals",
    }
    claims.update(changes)
    token = jwt.encode(claims, key, algorithm=algorithm)
    assert client.get("/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


@pytest.mark.parametrize(
    "role,create_status,delete_status",
    [
        ("reader", 403, 403),
        ("writer", 201, 403),
        ("moderator", 201, 204),
    ],
)
def test_rental_permissions(client, accounts, rental_payload, role, create_status, delete_status):
    headers = bearer(client, accounts[role])
    moderator = bearer(client, accounts["moderator"])
    assert client.get("/api/rentals", headers=headers).status_code == 200
    created = client.post("/api/rentals", headers=headers, json=rental_payload)
    assert created.status_code == create_status
    if create_status == 403:
        created = client.post("/api/rentals", headers=moderator, json=rental_payload)
    path = f"/api/rentals/{created.json()['id']}"
    assert client.get(path, headers=headers).status_code == 200
    assert client.put(
        path,
        headers=headers,
        json={
            "listingTitle": "Changed title",
            "propertyAddress": rental_payload["propertyAddress"],
        },
    ).status_code == (403 if role == "reader" else 200)
    assert client.delete(path, headers=headers).status_code == delete_status
    if delete_status == 403:
        assert client.get(path, headers=moderator).status_code == 200
    if role != "moderator":
        assert client.delete("/api/rentals/highest", headers=headers).status_code == 403


def test_current_mysql_role_overrules_token_and_deleted_user_is_denied(
    client, accounts, hw4_session_factory, rental_payload
):
    headers = bearer(client, accounts["writer"])
    created = client.post("/api/rentals", headers=headers, json=rental_payload)
    assert created.status_code == 201
    path = f"/api/rentals/{created.json()['id']}"
    with hw4_session_factory() as db:
        row = db.get(User, accounts["writer"]["id"])
        row.role = "reader"
        db.commit()
    assert client.get("/auth/me", headers=headers).json()["user"]["role"] == "reader"
    assert client.post("/api/rentals", headers=headers, json=rental_payload).status_code == 403
    assert client.put(path, headers=headers, json=rental_payload).status_code == 403
    assert client.delete("/api/rentals/1", headers=headers).status_code == 403
    with hw4_session_factory() as db:
        db.delete(db.get(User, accounts["writer"]["id"]))
        db.commit()
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_unique_username_and_role_constraint_are_enforced(
    client, accounts, hw4_session_factory, hw4_password_hash
):
    with hw4_session_factory() as db:
        for username, role in [
            (accounts["reader"]["username"], "reader"),
            ("unique_" + uuid4().hex, "admin"),
        ]:
            db.add(
                User(
                    username=username,
                    role=role,
                    name="Rejected",
                    email=f"{uuid4().hex}@example.com",
                    password_hash=hw4_password_hash,
                )
            )
            with pytest.raises(DBAPIError):
                db.commit()
            db.rollback()
        row = db.scalar(select(User).where(User.id == accounts["reader"]["id"]))
        assert row.password_hash.startswith("$argon2id$")


def test_signing_key_is_required_and_legacy_auth_routes_are_absent(monkeypatch, client):
    for path in ("/api/auth/login", "/api/auth/me", "/api/auth/logout"):
        assert path not in client.get("/openapi.json").json()["paths"]
    monkeypatch.delenv("HW7_JWT_SECRET", raising=False)
    with pytest.raises(ValueError, match="HW7_JWT_SECRET"):
        create_app()


@pytest.mark.parametrize("seconds", [0, -1, 3601])
def test_token_lifetime_configuration_rejects_invalid_values(seconds):
    from web_application.jwt_security import JWTSettings

    with pytest.raises(ValueError, match="HW7_JWT_TTL_SECONDS"):
        JWTSettings(SECRET, ttl_seconds=seconds)
