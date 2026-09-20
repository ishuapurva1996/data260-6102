# Reproduce HW3 Part 1

Run these commands from this checkout's root, using Python 3.12 and Node.js 20 or later. Keep the web environment separate from retrieval and agent environments.

```bash
python3.12 -m venv .venv-web
.venv-web/bin/python -m pip install -r requirements.txt
npm install --package-lock=false
npx playwright install chromium
.venv-web/bin/python scripts/run_hw03_web.py --prepare-cert
```

The install intentionally does not create or change a root lockfile. The repository pins Playwright 1.62.1 in package.json. The certificate has localhost, 127.0.0.1 and ::1 SANs; its key and configuration stay in ignored tmp/https. Do not change the OS trust store.

## Start the app manually

```bash
.venv-web/bin/python scripts/run_hw03_web.py --host ::1 --port 8702
```

Open `https://[::1]:8702/`. A manual browser will warn that the local development certificate is self-signed. Login with public demo credentials `admin` / `password`, visit Dashboard, then Logout. The ordinary idle timeout is 300 seconds. `SECRET_KEY` may be supplied as an environment secret; if absent, a random process-local key is generated. Do not commit a key. Stop only the server you started with Ctrl-C before running the browser evidence suite on that address.

The recorded run used IPv6 because the existing shared checkout's server was already using 127.0.0.1:8702. You can instead use `--host 127.0.0.1` and `HW3_HOST=127.0.0.1` if that address is free. Do not stop someone else's process or clear their data.

## Tests and evidence

Commit the code before producing final evidence so the recorded source hashes correspond to an existing commit. In this execution session, only Part 1 owned code paths were committed.

```bash
.venv-web/bin/python -m pytest tests/test_api.py tests/test_hw03_auth.py -q
node tests/browser_part2.cjs
node tests/browser_hw03_auth.cjs
.venv-web/bin/python scripts/verify_hw03_part1.py
```

The existing browser_part2.cjs file is the **HW2 rental regression suite**. It creates an ephemeral HTTP server and its own data. The auth browser suite creates and stops its own HTTPS servers on `[::1]:8702`: first with 300-second idle time, then with a 2-second override for a short real idle-expiry demonstration. It runs at desktop (1280 px) and mobile (375 px) widths, saves actual screenshots, and replays copied cookies in fresh browser contexts. Dedicated contexts set ignoreHTTPSErrors for the self-signed certificate. Saved response headers redact the complete cookie value while retaining flags. No API keys or paid services are used.

Artifacts are written only to `reports/hw03/raw/part1/`, `reports/hw03/screenshots/part1/`, and `reports/hw03/part1/verification.json`. The verifier reruns Python tests, checks individual browser outcomes, verifies source hashes against both the recorded code commit and current files, checks required images/headers/report materials, and exits nonzero on failure. A failing test, missing screenshot, or stale source must not be reported as a pass.

After the run, visually inspect every delivered screenshot and retain the real command output with UTC timestamps in the Part 1 run log. The cookie-header and templates-directory screenshots render captured output/filesystem information in a clearly labeled evidence viewer; they are not screenshots of developer tools or a terminal.

## Runtime used for the recorded run

This machine supplied Python 3.12.14 and Node/Playwright through the Codex bundled runtime. The actual invocation paths are recorded in the run logs. If reproducing on this same machine without PATH entries, use:

```bash
export NODE_PATH='/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
'/Users/pragyaapurva/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node' tests/browser_hw03_auth.cjs
```

For the exact recorded transitive Python versions, install from `reports/hw03/raw/part1/python-freeze.txt` in the isolated web environment. The exact installed Python versions and hardware are in `../raw/part1/environment.json`; Chromium/Node versions and launch configuration are in browser-evidence.json. Dependency deprecation warnings from the preserved FastAPI/Starlette/HTTPX combination are retained in logs. They do not fail the tests. The application is a single-worker teaching demo, not a production authentication service.
