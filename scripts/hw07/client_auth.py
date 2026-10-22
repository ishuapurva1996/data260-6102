"""Authenticate HTTPX/TestClient clients using the shared HW7 bearer contract."""

from time import monotonic

import httpx


class RenewableBearer(httpx.Auth):
    """Renew before sending a request; never replay an ambiguous application write."""

    requires_response_body = True

    def __init__(self, login_url, username, password, payload):
        self.login_url = login_url
        self.credentials = {"username": username, "password": password}
        self._update(payload)

    def _update(self, payload):
        self.token = payload["access_token"]
        ttl = int(payload["expires_in"])
        margin = min(30, max(1, ttl / 10))
        self.deadline = monotonic() + max(0, ttl - margin)

    def auth_flow(self, request):
        def origin(url):
            return url.scheme, url.host, url.port

        if origin(request.url) != origin(self.login_url) or "Authorization" in request.headers:
            yield request
            return
        if monotonic() >= self.deadline:
            renewal = httpx.Request(
                "POST", self.login_url, json=self.credentials, extensions=dict(request.extensions)
            )
            response = yield renewal
            response.raise_for_status()
            self._update(response.json())
        request.headers["Authorization"] = "Bearer " + self.token
        yield request


def authenticate(client, username, password):
    response = client.post(
        "/auth/login", json={"username": username, "password": password}, auth=None
    )
    response.raise_for_status()
    client.headers.pop("Authorization", None)
    client.auth = RenewableBearer(response.request.url, username, password, response.json())
    identity = client.get("/auth/me")
    identity.raise_for_status()
    return identity.json()["user"]
