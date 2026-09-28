# Part 2 completed manual captures and repeat procedure

**Status: all Part 2 captures are complete.** The five Postman CRUD responses, user-provided database image, and two Finder project views are saved. All six Part 3 Postman images are also complete. Final Parts 1–3 verification passes **46/46 checks**, with automated and overall status **pass**, exit **0**, and no false checks. The manual manifest records **13/13** completed evidence items. See the [capture manifest](../raw/part2/postman/manifest.json), [manual manifest](../manual-captures.json), and [final verification run](../raw/part2/postman/verification-run.json).

**Completed run: ID 16 is historical and deleted.** Its marker was `591325c9-5c03-4baa-bef3-a06eea2b2714`, and the application source was `7350d9c98e8b56fcab4979fd94e0b39246f2b6d3`. The row was created and updated against `data260-hw4-mysql`, host port **3362**, database `s6102_rel`, then captured in the database image before deletion. A fresh ownership GET passed, DELETE returned 204, a plain literal-ID GET returned 404, and logout returned 204. Local credentials and this run’s stored variables were cleared. The [postflight](../raw/part2/postman/postflight.json) passed 11/11 checks and confirmed original IDs 1 and 2, their fields/hash, and schema metadata were preserved. The [owned server is stopped](../raw/part2/postman/server-shutdown.json) and **8702 is released**.

The instructions below are for a future authorized capture run. Use that run’s newly returned ID and marker, never historical ID 16.

The earlier [availability recheck](../raw/part2/capture-recheck/availability.json) records that Postman was unavailable at `2026-09-28T01:29:38.647410+00:00`. That historical blocker is resolved. Native Terminal and Codex app control were denied by the computer-use tool; the available Codex terminal reader is read-only. The agent has not bypassed those restrictions. **A MySQL GUI is not required.** The user supplied the actual screenshot from the working MySQL CLI inside the existing container. No additional database-client installation is needed. The other MySQL instances on ports 3363 and 33363 are not this capture’s database.

Save actual images under `reports/hw04/screenshots/part2/`. Do not create placeholder images. Keep each relevant code excerpt directly above its resulting screenshot in the final report.

## Prepare an exclusive capture session for a future run

No recapture is required for the completed evidence. If a future run is needed, establish a new ownership record and use its returned ID throughout.

1. Read `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4_coordination/part2.md` and the sibling coordination notes. Reserve a free **8702** slot after the current owner releases it. Do not stop an unrelated process or write to a database during Part 3's measured run.
2. Use the final integrated branch when available and record its commit, capture time, MySQL instance, and port. Start the existing launcher with the private environment file: `python scripts/run_hw04_web.py --env-file /path/to/private/app.env`. The account and database must already be configured; do not reset the evidence database.
3. Open Postman and import `reports/hw04/part2/postman_collection.json`. Set local environment variables `baseUrl=https://127.0.0.1:8702`, `email`, and `password` using the configured teaching account. Credential defaults in the collection are blank. Keep values local; do not sync or export the populated environment.
4. Trust the launcher's local certificate in this test context, or configure Postman to accept this local self-signed certificate for the capture. Keep the request URL on HTTPS and port 8702.
5. Send **Login**. Its test requires **200** and public user fields. Postman's cookie jar should receive `s6102_session`. Do not capture the login request body, cookie values, or authentication headers. Send the remaining requests in order so the collection uses its own created `rentalId`.

## Own one capture rental

Use a fresh local copy of the prepared collection and send requests individually; a collection-runner pass would delete the row before the database capture. Leave credentials local and avoid syncing a populated environment. Do not override `rentalId` in environment, global, or data variables.

The Create script generates one GUID (a random identifier) in `captureRunId`, puts it in the description and `capture+<GUID>@example.com` email, and saves the intended body in `captureIntent` before sending. These fields remain unchanged by the two-field update. On a 201 response it stores the actual returned ID and object in `rentalId` and `createdRental`. A second Create is refused while any run state remains. The [offline script checks](../raw/part2/capture-recheck/collection-offline-check.json) remain separate from the actual Postman UI evidence now saved for ID 16.

Record the marker, returned ID, source commit, capture time, and `127.0.0.1:3362/s6102_rel` in a local non-secret capture note. Before PUT and again before DELETE, send a fresh GET for the literal returned ID and compare its `submitterEmail` and `description` with `captureIntent`. Stop on any mismatch or uncertainty. Collection guards check saved ownership and conflicting ID variables, but this manual current-row comparison is still required. Never use the largest ID, a title substring, or an unrelated existing row for cleanup.

If a request is interrupted or its response is uncertain, keep the run variables. First inspect that exact returned ID. If no ID was received, use the database client to find the **exact** unique email and description from `captureIntent`; proceed only if exactly one row matches, then record its ID. Do not send another Create or clear the intent until the previous row is confirmed absent. This collection has no automatic cleanup after a closed/crashed Postman process.

The prepared scripts use Postman's documented [dynamic-variable API](https://learning.postman.com/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-variables) and [pre-request skipping API](https://learning.postman.com/latest-v-12/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-execution). The captured POST, list GET, ID GET, PUT, and DELETE test views record 12 passing assertions in Postman (3 + 2 + 2 + 3 + 2). This is a per-request total, not a Collection Runner result; supplemental requests are separate. The offline stub remains preparation evidence; it cannot verify Postman’s cookie jar, certificate handling, or UI behavior.

After the database screenshot and DELETE, use a separate plain GET request to the same literal ID to record the actual 404. The normal "Read created rental" request expects 200 and is not the post-delete check. Confirm absence before clearing only `captureRunId`, `captureIntent`, `rentalId`, and `createdRental` for a future run. Logout last. Preserve unrelated rows and keep the capture notes without credentials, cookie values, or password hashes.

## Five required Postman CRUD screenshots

Each image should show the request method, full URL with port 8702, status, and readable response. For POST and PUT, also show the domain request body when it fits. Expand the returned object or array so its fields can be read.

Inspect the resolved domain body in Postman before capturing: `{{createPayload}}` or `{{updatePayload}}` alone is not readable request evidence. Keep the response status and actual ID visible. Do not include a console or authentication/header pane that could expose the session cookie.

| File | Status | Historical observed result |
| --- | --- | --- |
| [01-post-create.png](../screenshots/part2/01-post-create.png) | Captured | POST `/api/rentals`; 201; returned ID 16 and all six fields; three assertions passed. |
| [02-get-list.png](../screenshots/part2/02-get-list.png) | Captured | Unfiltered GET `/api/rentals`; 200; IDs 1, 2, and 16; two assertions passed. |
| [03-get-by-id.png](../screenshots/part2/03-get-by-id.png) | Captured | GET `/api/rentals/16`; 200; initial values and UUID markers match POST; two assertions passed. |
| [04-put-update.png](../screenshots/part2/04-put-update.png) | Captured | PUT `/api/rentals/16`; 200; changed title/address, other four fields preserved; three assertions passed. |
| [05-delete.png](../screenshots/part2/05-delete.png) | Captured | DELETE `/api/rentals/16`; 204 with an empty body; two assertions passed. A separate plain GET confirmed 404. |

Capture the database image below while the created/updated row still exists, before sending Delete. After Delete, a GET of the saved ID should return 404. Send **Logout** last; it must return 204. Collection assertions supplement the screenshots and do not replace them.

## Completed database image and future capture query

The [actual database image](../screenshots/part2/06-database.png) shows `s6102_rel`, its five tables, and updated rental ID **16**, title **HW4 Postman capture 591325c9-5c03-4baa-bef3-a06eea2b2714 updated**, and address **261 Capture Lane, San Jose, CA**. The user’s original bytes are preserved unchanged. Its capture time was not supplied; ingestion at `2026-09-28T03:50:51.701131+00:00` is recorded separately in [image provenance](../raw/part2/postman/database-image.json).

For a future run, capture the user’s actual MySQL terminal or an existing database client connected to this same evidence instance. A GUI result grid is not required. Use the new run’s returned ID in this read-only query after confirming its exact ownership marker:

```sql
SELECT DATABASE() AS database_name;
SHOW TABLES;
SELECT id, listing_title, property_address
FROM rentals
WHERE id = <new run's returned integer ID>;
```

The placeholder must be replaced before execution. Run through the configured MySQL CLI inside `data260-hw4-mysql`, or connect to host port **3362**, matching the API’s private configuration. Show `rentals`, `users`, `sessions`, `property_managers`, and `schema_migrations`; show the owned row’s ID, title, and address before deletion. Keep private credentials out of the screenshot.

Do not select raw session rows, password hashes, or connection secrets. Do not remove unrelated rows for the screenshot. After saving the image, make another fresh ownership GET before deleting only that run’s exact ID, then confirm 404. If the same computer-use restrictions apply, the terminal reader cannot type commands or capture the screen; the user must provide the actual image.

## Project-folder screenshot

Save `07-project-structure.png` from the actual integrated worktree in an editor or file browser. Expand `code/web_application/` to show `database.py`, `models.py`, `schemas.py`, `session_store.py`, `routers/`, and `migrations/`. Also show `frontend/src/`, `scripts/hw04/`, and `reports/hw04/`. Hide generated environments, `node_modules`, private runtime configuration, and unrelated personal directories. The image must show the shared application layout, not the teaching demo directory.

For any future capture run, verify all required files exist and are readable, add actual dates and tested revision to its run log, and place the images beneath their corresponding code excerpts. Mark only the screenshots that were actually captured complete. The final whole-homework report and Part 4 remain separate work.

Captured project evidence: [root](../screenshots/part2/07-project-structure.png) and [backend](../screenshots/part2/07-project-backend.png). Their capture time and revision are recorded in [the manifest](../manual-captures.json). These are genuine Finder captures, not generated diagrams.
