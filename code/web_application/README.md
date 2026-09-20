# Rental Housing Listings — shared web app with HW3 authentication

The shared app keeps the rental form/list and FastAPI CRUD API, and adds a login, protected dashboard, and logout. HW1 and HW2 report artifacts remain historical evidence. The authentication demonstration requires HTTPS because its session cookie is Secure.

## Start locally

Use Python 3.12. First-time setup, from the repository root:

```bash
cd /path/to/your/checkout
python3.12 -m venv .venv-web
source .venv-web/bin/activate
python -m pip install -r requirements.txt
python scripts/run_hw03_web.py
```

For later sessions, run the same `cd`, activate `.venv-web`, and run `python scripts/run_hw03_web.py`; do not recreate the environment. Open [the application](https://127.0.0.1:8702/) or [interactive API documentation](https://127.0.0.1:8702/docs). Keep Terminal running; press `Control-C` to stop. Use FastAPI: a static `http.server` cannot provide these API endpoints.

The web app uses its own `.venv-web` and root `requirements.txt`. Follow the separate setup instructions in the root README for agent workflows; do not replace their environment or dependencies with the web requirements.

### In-memory behavior

- Each server start seeds ID 1, **Sunny Downtown Apartment**, and ID 2, **Spacious Garden House**.
- Reloading or opening another browser tab retains the current server records.
- Restarting the process resets the store to those seeds. There is no database or disk persistence.
- Use one worker/process. Only one server can bind a given local address and port at a time. The recorded HW3 run uses IPv6 loopback `[::1]:8702` because the shared checkout already occupies `127.0.0.1:8702`; use `--host ::1` and open `https://[::1]:8702/` to reproduce that isolation.
- New IDs equal the current maximum plus one, or 1 when the store is empty. A deleted highest ID can therefore be reused.

## Authentication

Use the teaching account **admin / password**. These are public demo credentials, not a production account store. Invalid credentials show a Bootstrap alert. Successful login redirects to `/dashboard`, which displays the username. `/logout` revokes the server session and redirects to `/`.

A signed cookie carries only `user` and a random `sid`, never the password. It has `HttpOnly`, `Secure`, and `SameSite=lax`. The app also checks a process-local registry before accepting a cookie. Copied cookies cannot regain access after logout, replacement login, idle expiry, or server restart. The idle limit is 300 seconds; the cookie age limit is 3600 seconds. Visiting `/`, `/login`, or `/dashboard` renews an active session. Static assets and rental API traffic do not. The rental API stays public as required by this homework.

Set `SECRET_KEY` through your environment for a chosen signing key; otherwise the app uses a random per-process value. Use one worker because both rentals and sessions are in memory. This demonstration does not implement registration, a credential database, or multiworker persistence.

The HTTPS launcher creates a self-signed certificate with localhost, 127.0.0.1, and ::1 SANs under ignored `tmp/https/`. It does not install a trusted certificate or change system trust. A manual browser will display a development-certificate warning; automated tests explicitly accept that certificate only in dedicated test contexts. Never commit the private key.

Bootstrap 5.3.2 is vendored at `static/bootstrap.min.css` from the tutor's pinned jsDelivr URL; its MIT license notice is retained. The homepage is rendered once from `templates/index.html`; the obsolete static homepage was removed.

## Use the app

1. **Create:** complete Listing Title, Address, Landlord Email, Description, Property Type, and the terms checkbox. Click **Create Rental Listing**. Success navigates home and displays the server-assigned ID.
2. **Update:** click **Edit** on any listing. Its title and address appear in **Edit Listing ID N**. Change them and click **Save changes**, or **Cancel** to close the editor without saving. Email, description, type, and accepted terms remain unchanged. Use ID 1 for the assignment's required update evidence; other listings remain editable even if ID 1 is deleted.
3. **Delete highest:** click **Delete highest-ID listing (N)** and confirm. The backend selects the maximum from the entire store, including records hidden by search. The count and button refer to the full collection.
4. **Delete a selected listing:** click its **Delete** button and confirm. This is an additional convenience action.
5. **Search:** enter a title or address fragment and click **Search**. Matching is case-insensitive, trims surrounding whitespace, and uses title **or** address. **Clear**, or a blank search, restores all records.

Successful create/update/delete requests return JSON or an empty response to JavaScript, which navigates to `/`. The mutation endpoints do not themselves issue HTTP 303 redirects. Search refreshes the displayed list without navigating away. Mutations disable controls and show progress; errors preserve form input. Empty storage and a search with no matches have different messages. Long text wraps at a 375px viewport.

The editor opens only after choosing a listing. Selecting another listing asks before discarding an unsaved draft; choosing the same listing again preserves that draft. Searching does not change the selected target or its draft. If a refreshed collection shows the selected record has been removed, saving is disabled with an explanation; Cancel remains available.

## API contract

| Method and path | Success | Behavior |
|---|---|---|
| `GET /` | 200 HTML | Home page |
| `GET /api/rentals?q=...` | 200 JSON array | List all or match title/address; `Cache-Control: no-store` |
| `POST /api/rentals` | 201 JSON record | Create from all six fields; assign the ID on the server |
| `PUT /api/rentals/{rental_id}` | 200 JSON record | Update title/address for the selected existing ID |
| `DELETE /api/rentals/highest` | 204, empty body | Delete the current highest ID |
| `DELETE /api/rentals/{rental_id}` | 204, empty body | Delete the selected ID |

Unknown IDs and deleting the highest ID from an empty store return **404**. Invalid bodies return **422** without changing data. Text is trimmed; title/address must be nonempty, email must be valid, and description must have at least 26 characters after trimming. Type must be `apartment`, `house`, `condo`, or `townhouse`. `termsAccepted` must be the JSON boolean `true`, not the string `"true"` or number `1`. Extra request fields, including a client-provided ID, are rejected.

Example create body:

```json
{
  "listingTitle": "Downtown San Jose Studio",
  "propertyAddress": "999 Main Street, San Jose, CA",
  "submitterEmail": "sanjosedowntownrentalpropertymanagementoffice@example.com",
  "description": "Bright studio with covered parking and convenient light rail access.",
  "propertyType": "apartment",
  "termsAccepted": true
}
```

Example update body:

```json
{
  "listingTitle": "Updated Downtown Apartment",
  "propertyAddress": "900 Market Street, San Jose, CA"
}
```

## Verification

After installing the Python requirements, from the repository root:

```bash
.venv-web/bin/python -m pytest tests/test_api.py tests/test_hw03_auth.py
```

For browser checks, install Node.js 20 or newer and then run:

```bash
npm install
npm exec playwright install chromium
node tests/browser_part2.cjs
.venv-web/bin/python scripts/run_hw03_web.py --prepare-cert
node tests/browser_hw03_auth.cjs
```

The suite starts and stops its own FastAPI server on an available local port with a separate in-memory store. It does not clear the app running on 8702. It defaults to `.venv-web/bin/python`; set `PYTHON` if using another interpreter with the same web dependencies.

To retain diagnostic browser screenshots outside the submission repository:

```bash
PART2_SCREENSHOT_DIR="../HW2/agent_outputs/part2-browser-checks" npm run test:browser
```

Automated screenshots support verification; the manual guides explain how to capture the 375px toolbar, relevant code, and assignment evidence. The root README describes retained HW1 verification.

## Historical HW2 screenshot guides

Manual guides remain outside Git at these locations, relative to the repository root:

- Part 1: `../HW2/agent_outputs/SCREENSHOT_EVIDENCE_PLAN.md`
- Part 2: `../HW2/agent_outputs/PART2_SCREENSHOT_EVIDENCE_PLAN.md`

For HW3, save evidence only under `reports/hw03/screenshots/part1/` and `reports/hw03/raw/part1/`. Historical HW2 screenshots are unchanged. In the report, put each relevant code excerpt immediately above its corresponding output screenshot. The guides describe future collection, not completed student evidence.

Two controlled create-form modes support screenshots:

- [Loading demo](https://127.0.0.1:8702/?slowSave=true): waits eight seconds before the real POST. Capture the loading message and disabled controls during the delay. Success navigates to `/`, removing the parameter.
- [Error demo](https://127.0.0.1:8702/?simulateError=true): waits two seconds and produces an error before sending any create request. Data is unchanged and input preserved. Label this a controlled UI failure; it does not demonstrate an actual backend outage.

Ordinary create requests have no artificial delay.

## Run with Docker

Build from the repository root so Docker can copy the root requirements file:

```bash
docker build -f code/Dockerfile -t rental-housing-app .
python scripts/run_hw03_web.py --prepare-cert
docker run --rm -p 127.0.0.1:8702:8702 \
  -v "$PWD/tmp/https:/certs:ro" rental-housing-app \
  python -m uvicorn main:app --host 0.0.0.0 --port 8702 --workers 1 \
  --ssl-certfile /certs/cert.pem --ssl-keyfile /certs/key.pem
```

Stop the Python server first if it is using 8702. Open the same local app URL. The container uses one worker; stopping and recreating it restores seed records. This runs locally and does not deploy to a cloud service.

Part 1 evidence and self-check instructions: [reproducible run](../../reports/hw03/part1/REPRODUCIBLE_RUN_INSTRUCTIONS.md). The historical `scripts/verify_hw02.py` compares static homepage bytes and is intentionally not the HW3 verifier.
