#!/usr/bin/env python3
"""Make real HTTPS requests for manually captured authentication evidence."""
import argparse
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / 'worktrees' / 'integration'
BASE = 'https://[::1]:8702'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

context = ssl.create_default_context(cafile=str(ROOT / 'tmp/https/cert.pem'))
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context))

def request(path, *, data=None, cookie=None):
    headers = {'Cookie': cookie} if cookie else {}
    encoded = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=encoded, headers=headers)
    try:
        response = opener.open(req, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read().decode('utf-8', errors='replace')
        status, response_headers = response.code, response.headers
    print(f'{req.get_method()} {path} -> HTTP {status}', flush=True)
    if response_headers.get('Location'):
        print('Location: ' + response_headers['Location'], flush=True)
    return status, response_headers, body

def login():
    status, headers, body = request('/login', data={'username': 'admin', 'password': 'password'})
    assert status == 303 and headers.get('Location') == '/dashboard', 'Login did not redirect to dashboard'
    raw = headers.get('Set-Cookie', '')
    parsed = SimpleCookie()
    parsed.load(raw)
    assert 'session' in parsed, 'No session cookie returned'
    return 'session=' + parsed['session'].value, raw

def denied(cookie):
    status, headers, _ = request('/dashboard', cookie=cookie)
    assert status == 303 and headers.get('Location') == '/login', 'Saved cookie was not denied'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('check', choices=['cookie', 'logout', 'idle'])
args = parser.parse_args()
print('Live authentication check: ' + args.check, flush=True)
print('UTC: ' + datetime.now(timezone.utc).isoformat(), flush=True)
print('Server: ' + BASE, flush=True)
print(flush=True)
cookie, raw_header = login()
try:
    if args.check == 'cookie':
        print('Set-Cookie: ' + re.sub(r'(session=)[^;]*', r'\1[REDACTED]', raw_header, flags=re.I), flush=True)
        flags = raw_header.lower()
        assert all(flag in flags for flag in ('httponly', 'samesite=lax', 'secure')), 'Required cookie flags missing'
        print('PASS: HttpOnly, SameSite=lax and Secure are present.', flush=True)
    elif args.check == 'logout':
        status, _, _ = request('/dashboard', cookie=cookie)
        assert status == 200, 'Logged-in dashboard was not accessible'
        saved_cookie = cookie
        status, headers, _ = request('/logout', cookie=cookie)
        assert status == 303 and headers.get('Location') == '/', 'Logout did not redirect home'
        print('Replaying the same saved cookie after logout:', flush=True)
        denied(saved_cookie)
        print('PASS: the logged-out cookie cannot reopen the dashboard.', flush=True)
    else:
        status, _, body = request('/dashboard', cookie=cookie)
        assert status == 200, 'Logged-in dashboard was not accessible'
        assert '300' in body, 'Expected the normal 300-second timeout on the dashboard'
        print('Waiting 301 seconds without sending any requests for this session...', flush=True)
        print('Wait started: ' + datetime.now(timezone.utc).isoformat(), flush=True)
        start = time.monotonic()
        time.sleep(301)
        print(f'Actual idle wait: {time.monotonic() - start:.1f} seconds', flush=True)
        print('Replaying the saved cookie after the idle timeout:', flush=True)
        denied(cookie)
        print('PASS: the expired cookie cannot reopen the dashboard.', flush=True)
finally:
    # Invalidate this demo session so no live credential is left in a capture.
    try:
        request('/logout', cookie=cookie)
    except Exception:
        pass
