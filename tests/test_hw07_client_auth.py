"""Client lifecycle tests use MockTransport and a controlled clock, not live auth."""

import httpx
import pytest

from scripts.hw07 import client_auth


def test_renews_before_expiry_and_sends_original_write_once(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(client_auth, "monotonic", lambda: clock[0], raising=False)
    calls = []
    logins = []

    def handler(request):
        calls.append((request.method, request.url.path, request.headers.get("Authorization")))
        if request.url.path == "/auth/login":
            logins.append(1)
            return httpx.Response(
                200, json={"access_token": f"token-{len(logins)}", "expires_in": 15}
            )
        if request.url.path == "/auth/me":
            return httpx.Response(200, json={"user": {"id": 1, "role": "writer"}})
        assert request.headers["Authorization"] == "Bearer token-2"
        return httpx.Response(201, json={"id": 7})

    with httpx.Client(
        base_url="https://testserver", transport=httpx.MockTransport(handler)
    ) as client:
        assert client_auth.authenticate(client, "test_writer", "test-only")["id"] == 1
        clock[0] = 14
        response = client.post("/api/rentals", json={"listingTitle": "Owned"})
    assert response.status_code == 201
    assert len(logins) == 2
    assert [c for c in calls if c[1] == "/api/rentals"] == [
        ("POST", "/api/rentals", "Bearer token-2")
    ]


def test_credentials_are_scoped_to_the_api_origin():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "scoped-token", "expires_in": 900})
        if request.url.path == "/auth/me":
            return httpx.Response(200, json={"user": {"id": 1}})
        return httpx.Response(200, json={})

    with httpx.Client(
        base_url="https://testserver", transport=httpx.MockTransport(handler)
    ) as client:
        client_auth.authenticate(client, "test_reader", "test-only")
        client.get("https://another.invalid/public")
    assert "Authorization" not in requests[-1].headers


def test_failed_renewal_never_sends_the_original_mutation(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(client_auth, "monotonic", lambda: clock[0], raising=False)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/auth/login":
            return (
                httpx.Response(401, json={"detail": "Invalid credentials"})
                if clock[0]
                else httpx.Response(200, json={"access_token": "initial", "expires_in": 15})
            )
        return httpx.Response(200, json={"user": {"id": 1}})

    with httpx.Client(
        base_url="https://testserver", transport=httpx.MockTransport(handler)
    ) as client:
        client_auth.authenticate(client, "test_writer", "test-only")
        clock[0] = 20
        with pytest.raises(httpx.HTTPStatusError):
            client.post("/api/chat", json={"message": "Do not replay"})
    assert "/api/chat" not in calls
