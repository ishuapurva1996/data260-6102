# HW5 Part 1: rental housing application

The application extends the existing `Rental` and `PropertyManager` entities in
MySQL database `s6102_rel`. Property managers remain separate from login users.
Use MySQL 8.0.16 or later so database `CHECK` constraints are enforced. Use a
private Python environment with the pinned web requirements and this checkout's
frontend dependencies. Keep runtime configuration and HTTPS certificates outside
the checkout; never commit passwords, session cookies, or complete private DSNs.

## Database setup and upgrade

Set `HW4_DATABASE_URL` privately to your explicitly owned MySQL instance, using
driver `mysql+pymysql` and database `s6102_rel`. The HW5 CLI refuses the implicit
default connection. Worktrees share ports and database services: select a
dedicated instance and stop application writes during this maintenance upgrade.
Take your normal database backup before upgrading valuable data.

Run from the repository root:

```sh
python scripts/hw05/part1/db_setup.py --create-database --migrate
python scripts/hw05/part1/db_setup.py --seed-account
# Optional, on an empty owned demonstration database only:
python scripts/hw05/part1/db_setup.py --seed-demo
```

Omit `--create-database` when `s6102_rel` already exists. Account creation reads
`HW4_SEED_NAME`, `HW4_SEED_EMAIL`, and `HW4_SEED_PASSWORD`; it preserves an existing
account and its hash. The optional HW5 demo seed creates one clearly labeled
manager and apartment only when both domain tables are empty, otherwise doing
nothing. It never resets IDs or replaces rows. Do not run historical HW4
performance seeders against an upgraded or populated database.

Migration `004_hw5_related_entities` is implemented in
`scripts/hw05/part1/migration_004.py`. Its SHA-256 checksum is recorded in the
existing `schema_migrations` journal only after the upgrade is complete. Do not
edit a migration that has already been applied; use a new migration for later
schema changes. The historical `001` and `003` SQL files remain unchanged. A
fresh database receives `001` before `004`; an existing `003` listing-title index
is preserved, and the HW5 setup does not add that optional historical index if
it was absent.

The upgrade preserves every original rental/manager field, ID, relationship,
login user, password hash, authentication session, and index. It first adds
nullable columns, fills only missing new values, validates the result, then
enforces required columns, unique indexes, defaults, and constraints. It obtains
a database advisory lock against another HW5 upgrade. MySQL DDL commits
implicitly, so each durable step is followed by fresh schema inspection on a
rerun. An interruption can be resumed by repeating the same command; it does
not require resetting data. Keep application writes stopped until the command
finishes, particularly while replacing the manager foreign key.

| Entity | Added data and rules |
| --- | --- |
| Property manager | Required `company` and unique `email`, plus UTC `created_at` and `updated_at` |
| Rental | Required unique `listing_code`, nonnegative integer `available_units` defaulting to 1, and UTC timestamps |
| Relationship | Existing nullable `manager_id` remains nullable; deleting a referenced manager is restricted |

Legacy managers receive company `Legacy import` and synthetic email
`legacy-manager-<id>@example.com`. These addresses represent missing historical
contact information; they are not inferred real contacts. Legacy rentals receive
`S6102-R-<id>` and one available unit. The numeric field counts equivalent units
offered by the listing.

Historical creation/update times cannot be reconstructed. Both new timestamps
are set to the UTC upgrade start time recorded in `hw05_migration_progress`.
That time persists through interruptions; rerunning does not refresh it or
existing row timestamps. MySQL stores naive `DATETIME(6)` values representing UTC;
the API renders UTC timestamps. New records receive current UTC times, and the
application updates `updated_at` when a record changes.

New API manager requests must supply meaningful name/company/email values; the
legacy backfill does not satisfy missing request fields. Rental creation accepts
an explicit valid `S6102-R-<positive integer>` code or generates one from its new
database ID. Insertion uses a private unique temporary value and replaces it
within the same transaction, before commit. No half-initialized record is exposed.
MySQL enforces uniqueness and non-null codes; request validation enforces the
public code format. A collision, including an explicit code that occupies a
future generated value, returns HTTP 409 and rolls back the insertion.

## Migration verification

`tests/test_hw05_database.py` performs real DDL and therefore uses a separate,
explicitly disposable MySQL instance with an initially empty `s6102_rel` schema.
It refuses an occupied schema and never implicitly uses application test URLs.
Configure `HW5_MIGRATION_TEST_DATABASE_URL` privately and set
`HW5_ALLOW_DESTRUCTIVE_MIGRATION_TESTS=1` only for that disposable instance:

```sh
python -m pytest tests/test_hw05_database.py -q -p no:cacheprovider
```

The tests populate the original HW4 schema and prove exact preservation of old
fields/authentication rows/indexes, deterministic backfills, repeatability,
resume after committed DDL/backfill/journal steps, real database constraint
failures, fresh installation, and checksum protection. Teardown drops only the
tables the fixture created after verifying that its dedicated schema was empty.
Skipped tests indicate missing opt-in/infrastructure, not live verification.

## API and client

All domain routes require the existing Secure, HttpOnly session cookie. Login
uses `/api/auth/login`; managers are business records, never login accounts.

| Resource | Operations |
| --- | --- |
| `/api/rentals` | POST create; GET list/search |
| `/api/rentals/{id}` | GET detail; PUT update; DELETE |
| `/api/property-managers` | POST create; GET list |
| `/api/property-managers/{id}` | GET detail; PUT update; DELETE |
| `/api/property-managers/{id}/rentals` | GET related rentals |

All three lists return arrays, `X-Total-Count`, ascending IDs, `limit` from 1 to
100 (default 50), and nonnegative `offset` (default 0). Rental `q` preserves
literal Unicode casefold matching in titles/addresses. Create returns 201,
read/update 200, delete 204; missing resources return 404, invalid payloads or
manager references 422, and uniqueness or referenced-manager conflicts 409.
Writes roll back on database constraint failure. The old `/api/rentals/highest`
route remains available for compatibility; the paginated UI no longer derives
a global highest ID from its current page.

Old rental creation payloads remain valid: omitted code is generated, available
units defaults to 1, and omitted manager remains null. Title/address-only PUT
preserves every omitted field. HW5 forms require an explicit manager choice.

Install/build the client from `frontend/` with `npm ci` and `npm run build`.
Redux Toolkit owns rental list, detail and mutation results; Axios sends cookies
and cancellation signals. Authentication remains in AuthContext. Session
changes clear Redux state, and request IDs/session generations prevent old
responses from restoring records. Completed writes and subsequent list refresh
failures are separate outcomes, so a refresh failure does not invite a duplicate
creation. Form edits remain component-local.

Login and logout requests run in order because the browser applies their cookie
headers before JavaScript handles the responses. Logout clears visible rental
data and opens Login immediately; a new login waits for the earlier logout to
settle. Each new editor visit initializes from its own fresh detail response and
waits for an earlier visit's pending write. Refreshing the current editor keeps
its local edits and completed-save navigation intact.

Run the existing launcher with explicit external certificate/key files:

```sh
python scripts/run_hw04_web.py --port 8702 --env-file /absolute/private/app.env \
  --cert /absolute/private/cert.pem --key /absolute/private/key.pem
```

Both certificate files must already exist. This avoids the launcher's historical
in-repository certificate-generation path. Do not change Secure cookie behavior
or share private runtime files.

## Verification and captures

With the owned migrated test database configured, run:

```sh
python -m pip check
python -m pytest tests/test_hw05_api.py tests/test_api.py tests/test_hw04_auth.py \
  tests/test_hw04_search_regression.py tests/test_hw04_database.py \
  tests/test_hw04_serving.py -q -p no:cacheprovider
python scripts/hw05/part1/live_acceptance.py --output /absolute/evidence/api.json
HW5_RAW_DIR=/absolute/evidence/browser node tests/browser_hw05_part1.cjs --mock
HW5_RAW_DIR=/absolute/evidence/browser node tests/browser_hw05_part1.cjs --real
```

The live API runner requires private `HW4_SEED_EMAIL`, `HW4_SEED_PASSWORD`, and
`HW5_CA_CERT` (the trusted local certificate). It records response bodies/statuses,
never cookies/passwords, and deletes only records created by that run. Browser
runner configuration is documented at the top of its source. Use external paths
for exploratory output; select only final required evidence for `reports/hw05/`.

Import `reports/hw05/raw/part1/postman_collection.json` in Postman. Supply private
local environment variables `email` and `password`, enable its local cookie jar,
and configure the local CA certificate. Run requests in their numbered order.
The collection contains reproducible inputs and assertions; it is not evidence
that Postman was run. Capture request method/URL, relevant body, response status,
and response body for each of the eleven CRUD/relationship operations, plus
meaningful constraint failures. Never include login passwords or cookie headers.

Capture the database's two tables/relationship and the unique/FK/check constraints
in an actual database client. For terminal evidence, first print `Pragya Apurva`
in that terminal. Capture exactly four Redux feature frames, each with the actual
relevant source snippet beside or above the live corresponding Home, Create,
Update, or Delete result. A screenshot of API JSON or a reconstructed interface
is not a Postman capture. See the Part 1 evidence manifest for the actual captured
and outstanding evidence from this run.

The reproducible `scripts/hw05/part1/capture_features.cjs` helper displays exact
repository source excerpts above a live HTTPS app iframe in a temporary local
browser viewer on port 8703. It performs real UI CRUD, takes four single browser
screenshots, and deletes its one created rental. It does not combine images,
intercept responses, or reconstruct the app. Provide `HW5_TLS_KEY`, `HW5_CA_CERT`,
private login values, an explicit `HW5_FEATURE_DIR`, and
`HW5_FEATURE_MANIFEST`; use the running app on 8702. Its viewer closes on exit.
The manifest records source hashes and actual capture times. This helper covers
Redux frames only; genuine Postman and database-client captures remain separate.
