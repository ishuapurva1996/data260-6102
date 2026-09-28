# Part 2 manual captures still required

**Status: six Part 2 screenshots pending: five Postman CRUD captures and one database capture.** Postman was not available in the inspected local application inventory, and native Terminal capture was denied by the computer-use tool. Two actual Finder screenshots now show the integrated project root and expanded backend. HTTPX JSON responses, pytest output, and the folder inventory support verification but do not satisfy the assignment's screenshot requirement.

Save actual images under `reports/hw04/screenshots/part2/`. Do not create placeholder images. Keep each relevant code excerpt directly above its resulting screenshot in the final report.

## Prepare an exclusive capture session

1. Read `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4_coordination/part2.md` and the sibling coordination notes. Reserve a free **8702** slot after the current owner releases it. Do not stop an unrelated process or write to a database during Part 3's measured run.
2. Use the final integrated branch when available and record its commit, capture time, MySQL instance, and port. Start the existing launcher with the private environment file: `python scripts/run_hw04_web.py --env-file /path/to/private/app.env`. The account and database must already be configured; do not reset the evidence database.
3. Open Postman and import `reports/hw04/part2/postman_collection.json`. Set local environment variables `baseUrl=https://127.0.0.1:8702`, `email`, and `password` using the configured teaching account. Credential defaults in the collection are blank. Keep values local; do not sync or export the populated environment.
4. Trust the launcher's local certificate in this test context, or configure Postman to accept this local self-signed certificate for the capture. Keep the request URL on HTTPS and port 8702.
5. Send **Login**. Its test requires **200** and public user fields. Postman's cookie jar should receive `s6102_session`. Do not capture the login request body, cookie values, or authentication headers. Send the remaining requests in order so the collection uses its own created `rentalId`.

## Five required Postman CRUD screenshots

Each image should show the request method, full URL with port 8702, status, and readable response. For POST and PUT, also show the domain request body when it fits. Expand the returned object or array so its fields can be read.

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
