"""Offline transport boundary checks; real source captures are recorded separately."""

import hashlib
import io
import json
import time

import pytest

from src.bikeshare import policies


class Response(io.BytesIO):
    def __init__(self, body=b"", code=200, headers=None):
        super().__init__(body)
        self.code, self.headers = code, headers or {}


def test_redirect_to_nonofficial_host_is_rejected_before_request(monkeypatch, tmp_path):
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            return Response(code=302, headers={"location": "https://example.com/private"})

    monkeypatch.setattr(policies, "build_opener", lambda *args: Opener())
    cache = policies.PolicyCache(tmp_path, deadline=time.monotonic() + 60)
    with pytest.raises(ValueError, match="capture failed"):
        cache(policies.MEMBERSHIP_URL)
    assert requests == [policies.MEMBERSHIP_URL]
    assert len(list(tmp_path.glob("*-failure.json"))) == 1


def test_exact_captured_bytes_are_hashed_and_run_cache_avoids_second_fetch(monkeypatch, tmp_path):
    requests = []
    body = b"<html><h1>Policy</h1><script>untrusted script</script><p>$25 per account</p></html>"

    class Opener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            return Response(body)

    monkeypatch.setattr(policies, "build_opener", lambda *args: Opener())
    cache = policies.PolicyCache(tmp_path, deadline=time.monotonic() + 60)
    snapshot = cache(policies.MEMBERSHIP_URL)
    assert cache(policies.MEMBERSHIP_URL) == snapshot
    assert len(requests) == 1
    assert snapshot["text"] == "Policy\n$25 per account\n"
    assert (
        snapshot["sha256"]
        == hashlib.sha256((tmp_path / snapshot["text_file"]).read_bytes()).hexdigest()
    )
    assert snapshot["html_sha256"] == hashlib.sha256(body).hexdigest()
    metadata = json.loads((tmp_path / snapshot["text_file"]).with_suffix(".json").read_text())
    assert metadata["captured_at"] == snapshot["captured_at"]


def test_failed_http_body_is_retained_but_never_retrieved(monkeypatch, tmp_path):
    class Opener:
        def open(self, request, timeout):
            return Response(b"upstream unavailable", code=503)

    monkeypatch.setattr(policies, "build_opener", lambda *args: Opener())
    cache = policies.PolicyCache(tmp_path, deadline=time.monotonic() + 60)
    with pytest.raises(ValueError):
        cache(policies.MEMBERSHIP_URL)
    assert not cache.snapshots
    assert next(tmp_path.glob("*.html")).read_bytes() == b"upstream unavailable"
