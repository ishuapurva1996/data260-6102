# Part 2 manual captures still required

**Status: six Part 2 screenshots pending: five Postman CRUD captures and one database capture.** Postman was not available in the inspected local application inventory, and native Terminal capture was denied by the computer-use tool. Two actual Finder screenshots now show the integrated project root and expanded backend. HTTPX JSON responses, pytest output, and the folder inventory support verification but do not satisfy the assignment's screenshot requirement.

The follow-up availability check on 2026-09-28 found the same blockers. `cua.getApp("Postman")` returned `Invalid app: Postman`. Terminal returned `Computer Use is not allowed to use the app 'com.apple.Terminal' for safety reasons.` No Postman or commonly named dedicated MySQL GUI was found in `/Applications`, `~/Applications`, or `/System/Applications`. No capture rental or server was started. [Recheck evidence](../raw/part2/capture-recheck/availability.json) records the scope of this inspection.

**Access needed:** make Postman and an allowed database client available to computer use. A user-approved installation of Postman and a MySQL GUI is one option; an existing client opened by the user is another. The agent has not installed software or bypassed the Terminal denial. The database client must connect to the Part 2 instance at `127.0.0.1:3362`, database `s6102_rel`, using the private local configuration. The other instances on 3363 and 33363 are not this capture's database.

Save actual images under `reports/hw04/screenshots/part2/`. Do not create placeholder images. Keep each relevant code excerpt directly above its resulting screenshot in the final report.

## Prepare an exclusive capture session

1. Read `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4_coordination/part2.md` and the sibling coordination notes. Reserve a free **8702** slot after the current owner releases it. Do not stop an unrelated process or write to a database during Part 3's measured run.
2. Use the final integrated branch when available and record its commit, capture time, MySQL instance, and port. Start the existing launcher with the private environment file: `python scripts/run_hw04_web.py --env-file /path/to/private/app.env`. The account and database must already be configured; do not reset the evidence database.
3. Open Postman and import `reports/hw04/part2/postman_collection.json`. Set local environment variables `baseUrl=https://127.0.0.1:8702`, `email`, and `password` using the configured teaching account. Credential defaults in the collection are blank. Keep values local; do not sync or export the populated environment.
4. Trust the launcher's local certificate in this test context, or configure Postman to accept this local self-signed certificate for the capture. Keep the request URL on HTTPS and port 8702.
5. Send **Login**. Its test requires **200** and public user fields. Postman's cookie jar should receive `s6102_session`. Do not capture the login request body, cookie values, or authentication headers. Send the remaining requests in order so the collection uses its own created `rentalId`.

## Own one capture rental

Use a fresh local copy of the prepared collection and send requests individually; a collection-runner pass would delete the row before the database capture. Leave credentials local and avoid syncing a populated environment. Do not override `rentalId` in environment, global, or data variables.

The Create script generates one GUID (a random identifier) in `captureRunId`, puts it in the description and `capture+<GUID>@example.com` email, and saves the intended body in `captureIntent` before sending. These fields remain unchanged by the two-field update. On a 201 response it stores the actual returned ID and object in `rentalId` and `createdRental`. A second Create is refused while any run state remains. This preparation is not a claim that Postman has run; [offline script checks](../raw/part2/capture-recheck/collection-offline-check.json) are labeled separately from actual UI evidence.

Record the marker, returned ID, source commit, capture time, and `127.0.0.1:3362/s6102_rel` in a local non-secret capture note. Before PUT and again before DELETE, send a fresh GET for the literal returned ID and compare its `submitterEmail` and `description` with `captureIntent`. Stop on any mismatch or uncertainty. Collection guards check saved ownership and conflicting ID variables, but this manual current-row comparison is still required. Never use the largest ID, a title substring, or an unrelated existing row for cleanup.

If a request is interrupted or its response is uncertain, keep the run variables. First inspect that exact returned ID. If no ID was received, use the database client to find the **exact** unique email and description from `captureIntent`; proceed only if exactly one row matches, then record its ID. Do not send another Create or clear the intent until the previous row is confirmed absent. This collection has no automatic cleanup after a closed/crashed Postman process.

The prepared scripts use Postman's documented [dynamic-variable API](https://learning.postman.com/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-variables) and [pre-request skipping API](https://learning.postman.com/latest-v-12/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-execution). Verify these scripts in the actual installed Postman UI when access is available; the offline stub cannot verify Postman's cookie jar, certificate handling, or UI behavior.

After the database screenshot and DELETE, use a separate plain GET request to the same literal ID to record the actual 404. The normal "Read created rental" request expects 200 and is not the post-delete check. Confirm absence before clearing only `captureRunId`, `captureIntent`, `rentalId`, and `createdRental` for a future run. Logout last. Preserve unrelated rows and keep the capture notes without credentials, cookie values, or password hashes.

## Five required Postman CRUD screenshots

Each image should show the request method, full URL with port 8702, status, and readable response. For POST and PUT, also show the domain request body when it fits. Expand the returned object or array so its fields can be read.

Inspect the resolved domain body in Postman before capturing: `{{createPayload}}` or `{{updatePayload}}` alone is not readable request evidence. Keep the response status and actual ID visible. Do not include a console or authentication/header pane that could expose the session cookie.

| File to capture | Collection request | Expected observed result |
| --- | --- | --- |
| `01-post-create.png` | Create rental | POST `/api/rentals`; 201; generated positive ID and all six fields. Record this run's returned ID. |
| `02-get-list.png` | List rentals | GET `/api/rentals`; 200 array containing that new ID. Do not add a filter for this required list capture. |
| `03-get-by-id.png` | Read created rental | GET `/api/rentals/{{rentalId}}`; 200; same ID and initial values. |
| `04-put-update.png` | Update created rental | PUT `/api/rentals/{{rentalId}}`; 200; changed title/address with landlord email, description, type, and accepted terms preserved. |
| `05-delete.png` | Delete created rental | DELETE `/api/rentals/{{rentalId}}`; 204; empty body. Use only the row created by this collection. |

Capture the database image below while the created/updated row still exists, before sending Delete. After Delete, a GET of the saved ID should return 404. Send **Logout** last; it must return 204. Collection assertions supplement the screenshots and do not replace them.

## Database screenshot

Save `06-database.png` from an actual database client connected to the evidence instance. Show the `s6102_rel` database, its `rentals`, `users`, `sessions`, and `property_managers` tables, and the created/updated rental in a result grid. Show the rental ID, title, and address. If the layout permits, also show the rental structure with its auto-increment primary key.

Verify this client is connected to host port **3362**, matching the API's private `app.env`, and compare the row's exact ID and marker with the Postman response. Capture this view before DELETE. Do not open users' password hashes or raw session rows to demonstrate persistence.

Safe example queries, using the ID just created in Postman:

```sql
SELECT DATABASE();
SHOW TABLES;
SELECT id, listing_title, property_address, submitter_email,
       description, property_type, terms_accepted, manager_id
FROM rentals
WHERE id = <ID returned by this capture's POST>;
SHOW COLUMNS FROM rentals;
```

Do not select or display raw `sessions.id`, connection passwords, or `users.password_hash`. To show authentication storage without exposing reusable secrets, use counts and non-secret metadata:

```sql
SELECT COUNT(*) AS stored_session_count FROM sessions;
SELECT id, name, email, password_hash IS NOT NULL AS has_password_hash
FROM users;
```

These are capture instructions, not claimed query output. The selected test account email is personal configuration; keep it out of the screenshot if unnecessary. Do not delete unrelated rows to make the grid shorter.

## Project-folder screenshot

Save `07-project-structure.png` from the actual integrated worktree in an editor or file browser. Expand `code/web_application/` to show `database.py`, `models.py`, `schemas.py`, `session_store.py`, `routers/`, and `migrations/`. Also show `frontend/src/`, `scripts/hw04/`, and `reports/hw04/`. Hide generated environments, `node_modules`, private runtime configuration, and unrelated personal directories. The image must show the shared application layout, not the teaching demo directory.

After the remaining captures, verify all required files exist and are readable, add their actual dates and tested revision to the run log, and place the images beneath their corresponding code excerpts. Mark only the screenshots that were actually captured complete. The final whole-homework report and Part 4 remain separate work.

Captured project evidence: [root](../screenshots/part2/07-project-structure.png) and [backend](../screenshots/part2/07-project-backend.png). Their capture time and revision are recorded in [the manifest](../manual-captures.json). These are genuine Finder captures, not generated diagrams.
