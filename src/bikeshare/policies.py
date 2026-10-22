import hashlib
import json
import ssl
import threading
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import certifi

SINGLE_TRIP_URL = "https://capitalbikeshare.com/pricing/single-trip"
MEMBERSHIP_URL = (
    "https://help.capitalbikeshare.com/hc/en-us/articles/360039401111-30-Day-Membership"
)
ROUNDING_URL = "https://help.capitalbikeshare.com/hc/en-us/articles/360039003352-How-long-can-I-keep-a-bike-out"
OFFICIAL_HOSTS = {"capitalbikeshare.com", "help.capitalbikeshare.com", "www.capitalbikeshare.com"}


def official_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Use an official Capital Bikeshare HTTPS pricing URL.")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in OFFICIAL_HOSTS
            and parsed.port in (None, 443)
        )
    except ValueError:
        valid = False
    if not valid or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            "Use an official Capital Bikeshare HTTPS URL without credentials or query parameters."
        )
    return value


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "br", "tr", "section", "article"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def text(self):
        return (
            "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())
            + "\n"
        )


class PolicyCache:
    """Each run owns its captures, including failed fetch metadata and exact bytes."""

    def __init__(self, directory, *, deadline, fetcher=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.deadline = deadline
        self.fetcher = fetcher
        self.snapshots = {}
        self.lock = threading.RLock()

    def __call__(self, url):
        official_url(url)
        with self.lock:
            if url in self.snapshots:
                return self.snapshots[url]
            if len(self.snapshots) >= 6:
                raise ValueError("This run permits six distinct official policy captures.")
            stem = hashlib.sha256(url.encode()).hexdigest()[:20]
            try:
                snapshot = dict(self.fetcher(url)) if self.fetcher else self._download(url, stem)
                official_url(snapshot["url"])
                encoded = snapshot["text"].encode("utf-8")
                if (
                    len(encoded) > 100_000
                    or hashlib.sha256(encoded).hexdigest() != snapshot["sha256"]
                ):
                    raise ValueError(
                        "Policy text is oversized or does not match its recorded SHA-256."
                    )
                snapshot["text_file"] = stem + ".txt"
                (self.directory / snapshot["text_file"]).write_bytes(encoded)
                (self.directory / (stem + ".json")).write_text(
                    json.dumps({k: v for k, v in snapshot.items() if k != "text"}, indent=2) + "\n"
                )
                self.snapshots[url] = snapshot
                return snapshot
            except Exception as exc:
                (self.directory / (stem + "-failure.json")).write_text(
                    json.dumps(
                        {
                            "url": url,
                            "captured_at": datetime.now(timezone.utc).isoformat(),
                            "error": type(exc).__name__,
                        },
                        indent=2,
                    )
                    + "\n"
                )
                raise ValueError(
                    "Official policy capture failed; its failure record was retained."
                ) from None

    def _download(self, url, stem):
        original = url

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = build_opener(
            NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where()))
        )
        for _ in range(4):
            official_url(url)
            if time.monotonic() + 10 >= self.deadline:
                raise TimeoutError("Policy capture cannot fit the run deadline.")
            request = Request(
                url,
                headers={
                    "User-Agent": "DATA260-HW7-Academic-Public-Source-Capture/1.0",
                    "Accept": "text/html,application/zip;q=0.9,*/*;q=0.8",
                },
            )
            try:
                response = opener.open(request, timeout=10)
            except HTTPError as exc:
                response = exc
            with response:
                if response.code in {301, 302, 303, 307, 308}:
                    url = urljoin(url, response.headers["location"])
                    continue
                chunks, size = [], 0
                while chunk := response.read(65536):
                    if time.monotonic() >= self.deadline or size + len(chunk) > 2_000_000:
                        raise ValueError("Policy capture exceeded its time or byte bound.")
                    chunks.append(chunk)
                    size += len(chunk)
                body = b"".join(chunks)
                (self.directory / (stem + ".html")).write_bytes(body)
                if response.code != 200:
                    raise ValueError(f"Official source returned HTTP {response.code}.")
                parser = PageText()
                parser.feed(body.decode("utf-8", errors="replace"))
                text = parser.text()
                return {
                    "url": url,
                    "original_url": original,
                    "text": text,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "html_sha256": hashlib.sha256(body).hexdigest(),
                    "html_file": stem + ".html",
                    "http_status": response.code,
                    "text_extraction": "UTF-8 HTMLParser; script/style omitted; stripped nonempty lines",
                }
        raise ValueError("Official policy redirect limit exceeded.")
