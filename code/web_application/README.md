# Rental Housing Listings — HW2 Parts 1 and 2

The shared app combines the responsive Part 1 form/list with the Part 2 FastAPI backend at **http://127.0.0.1:8702/**. The original HW1 submission remains available at the `hw1` Git tag.

## Start locally

Use Python 3.12. First-time setup, from the repository root:

```bash
cd "/Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102"
python3.12 -m venv .venv-web
source .venv-web/bin/activate
python -m pip install -r requirements.txt
python code/web_application/main.py
```

For later sessions, run the same `cd`, activate `.venv-web`, and run `python code/web_application/main.py`; do not recreate the environment. Open [the application](http://127.0.0.1:8702/) or [interactive API documentation](http://127.0.0.1:8702/docs). Keep Terminal running; press `Control-C` to stop. Use FastAPI: a static `http.server` cannot provide these API endpoints.

The web app uses its own `.venv-web` and root `requirements.txt`. Follow the separate setup instructions in the root README for agent workflows; do not replace their environment or dependencies with the web requirements.

### In-memory behavior

- Each server start seeds ID 1, **Sunny Downtown Apartment**, and ID 2, **Spacious Garden House**.
- Reloading or opening another browser tab retains the current server records.
- Restarting the process resets the store to those seeds. There is no database or disk persistence.
- Use one worker/process. Only one server or container can bind local port 8702 at a time.
- New IDs equal the current maximum plus one, or 1 when the store is empty. A deleted highest ID can therefore be reused.

## Use the app

1. **Create:** complete Listing Title, Address, Landlord Email, Description, Property Type, and the terms checkbox. Click **Create Rental Listing**. Success navigates home and displays the server-assigned ID.
2. **Update:** fill **New Listing Title** and **New Address** under **Update Listing ID 1**. Email, description, type, and accepted terms remain unchanged. The button is unavailable if ID 1 does not exist.
3. **Delete highest:** click **Delete highest-ID listing (N)** and confirm. The backend selects the maximum from the entire store, including records hidden by search. The count and button refer to the full collection.
4. **Delete a selected listing:** click its **Delete** button and confirm. This is an additional convenience action.
5. **Search:** enter a title or address fragment and click **Search**. Matching is case-insensitive, trims surrounding whitespace, and uses title **or** address. **Clear**, or a blank search, restores all records.

Successful create/update/delete requests return JSON or an empty response to JavaScript, which navigates to `/`. The mutation endpoints do not themselves issue HTTP 303 redirects. Search refreshes the displayed list without navigating away. Mutations disable controls and show progress; errors preserve form input. Empty storage and a search with no matches have different messages. Long text wraps at a 375px viewport.

## API contract

| Method and path | Success | Behavior |
|---|---|---|
| `GET /` | 200 HTML | Home page |
| `GET /api/rentals?q=...` | 200 JSON array | List all or match title/address; `Cache-Control: no-store` |
| `POST /api/rentals` | 201 JSON record | Create from all six fields; assign the ID on the server |
| `PUT /api/rentals/{rental_id}` | 200 JSON record | Update title/address; the required UI targets ID 1 |
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
.venv-web/bin/python -m pytest tests/test_api.py
```

For browser checks, install Node.js 20 or newer and then run:

```bash
npm install
npm exec playwright install chromium
npm run test:browser
```

The suite starts and stops its own FastAPI server on an available local port with a separate in-memory store. It does not clear the app running on 8702. It defaults to `.venv-web/bin/python`; set `PYTHON` if using another interpreter with the same web dependencies.

To retain diagnostic browser screenshots outside the submission repository:

```bash
PART2_SCREENSHOT_DIR="../HW2/agent_outputs/part2-browser-checks" npm run test:browser
```

Automated screenshots support verification; the manual guides explain how to capture the 375px toolbar, relevant code, and assignment evidence. The root README describes retained HW1 verification.

## Screenshot evidence

Manual guides remain outside Git at these locations, relative to the repository root:

- Part 1: `../HW2/agent_outputs/SCREENSHOT_EVIDENCE_PLAN.md`
- Part 2: `../HW2/agent_outputs/PART2_SCREENSHOT_EVIDENCE_PLAN.md`

Save final screenshots under `reports/hw02/raw/`. In the report, put each relevant code excerpt immediately above its corresponding output screenshot. The guides describe future collection, not completed student evidence.

Two controlled create-form modes support screenshots:

- [Loading demo](http://127.0.0.1:8702/?slowSave=true): waits eight seconds before the real POST. Capture the loading message and disabled controls during the delay. Success navigates to `/`, removing the parameter.
- [Error demo](http://127.0.0.1:8702/?simulateError=true): waits two seconds and produces an error before sending any create request. Data is unchanged and input preserved. Label this a controlled UI failure; it does not demonstrate an actual backend outage.

Ordinary create requests have no artificial delay.

## Run with Docker

Build from the repository root so Docker can copy the root requirements file:

```bash
docker build -f code/Dockerfile -t rental-housing-app .
docker run --rm -p 127.0.0.1:8702:8702 rental-housing-app
```

Stop the Python server first if it is using 8702. Open the same local app URL. The container uses one worker; stopping and recreating it restores seed records. This runs locally and does not deploy to a cloud service.
