# HW4 shared contract for three parallel sessions

Created: 2026-09-27. Contract version: 1.

This file is the common implementation agreement for Parts 1, 2, and 3. Read it with the assigned part plan. The assignment controls required behavior; this document settles coordination and implementation choices. If a real incompatibility requires a contract change, record it in the shared handoff and notify the other sessions before depending on the change.

## Baseline and scope

Continue repository `data260-6102` from the peeled `hw3` tag at commit `5742b2aadbafee5ba208311723ea470c09811dc5`. The tag is annotated: compare its commit, not the tag object's hash. At planning time the checkout named `data260-6102` is on an older HW2-era branch, with a pre-existing `.gitignore` modification. Do not implement from that checkout's HEAD or reset its changes. The HW3 integration worktree contains the correct baseline.

Source of requirements: `DATA260_HW4.pdf` in the supplied `Homework4_export` folder, pages 1–6 and the evidence instructions on page 7. Absolute source locations are in the execution prompts. The extracted `DATA236_demo4` is a teaching reference, not the application to submit. It uses user-ID login and incomplete endpoint protection; those shortcuts do not meet HW4.

| Configuration | Value |
| --- | --- |
| SID4 | 6102 |
| PORT_BASE | 8702 |
| PREFIX | s6102 |
| SEED | 6102 |
| VERIFY_SEED | 266102 |
| DOMAIN_ID / domain | 6 / Rental Housing Listings |
| MySQL database | s6102_rel |

Create temporary Git worktrees for parallel development, then integrate into one shared application. Do not create a second application under a homework-specific folder. These three plans cover Parts 1–3 only. Part 4, the complete report PDF, final collaborator checks, final tagged-commit verification and the `hw4` submission tag remain a later submission step.

## Parallel ownership

| Owner | Branch | Main files and responsibility |
| --- | --- | --- |
| Part 1 | `codex/hw4-part1-react` | `frontend/`, `tests/browser_hw04_part1.cjs`, Part 1 evidence |
| Part 2 | `codex/hw4-part2-backend` | Existing `code/web_application/` core, shared models and migrations, authentication, Python dependencies, launcher, serving built React, root documentation, final Parts 1–3 integration |
| Part 3 | `codex/hw4-part3-performance` | `code/web_application/routers/performance.py`, `code/web_application/query_metrics.py`, `scripts/hw04/part3/`, `tests/test_hw04_part3.py`, index migration `003_*`, Part 3 evidence |

Part 3 may make the small performance-router registration change in `main.py` after the foundation is published. Part 2 owns all other shared application wiring. Part 3 must not independently redefine models, authentication, connection setup or the base migration. Part 1 uses a nested `frontend/package.json` and lockfile; Part 2 owns any changes to the existing root package manifest. Each session writes only its own report fragments until integration.

All development branches start from the same verified HW3 commit. Part 2 publishes an early foundation commit B and a foundation handoff. Parts 1 and 3 merge B into their own branches once available; merging preserves shared ancestry. Do not cherry-pick duplicate copies of B. Part 2 later merges the two completed branches into its integration branch. Do not push, publish, change old tags or create `hw4` as part of these prompts.

The foundation includes configuration, import strategy, shared schema and migrations (including the related table), session dependency, ordinary CRUD, the HW4 HTTPS launcher, minimal React asset/deep-link serving with a clear missing-build response, and a real-MySQL smoke check. Implement the serving plumbing without requiring a completed React build or performance module. This lets Part 1 import B, build its own frontend and test real port-8702 page loads without waiting for a later backend checkpoint. Part 2 may continue evidence and integration preparation afterward. Additions after B must preserve this contract or be announced before dependent work.

## Domain and database contract

Keep the current six-field create contract; HW4's two required domain fields are a minimum, not an instruction to discard earlier fields.

| API field | Rule |
| --- | --- |
| `id` | Server/database assigned positive integer; never supplied on create |
| `listingTitle` | Required nonempty trimmed text; bounded at 255 characters for MySQL |
| `propertyAddress` | Required nonempty trimmed text; bounded at 255 characters |
| `submitterEmail` | Required valid email; keep the existing Landlord Email label |
| `description` | Required text; retain the existing minimum of 26 characters |
| `propertyType` | `apartment`, `house`, `condo`, or `townhouse` |
| `termsAccepted` | Required Boolean true |

Create sends all six editable fields; update sends only `listingTitle` and `propertyAddress`. Preserve the other stored values on update. Reject unexpected fields consistently. The frontend must explain validation errors and preserve entered values after failed requests.

Part 2 owns these SQLAlchemy models in the existing backend: `Rental`, `User`, `SessionToken`, `PropertyManager`. Use table names `rentals`, `users`, `sessions`, `property_managers`. Database column names may use snake_case, while API names remain as above. Preserve the existing safe module-loading approach or introduce one clearly documented package import strategy; the top-level directory `code` conflicts with Python's standard library name.

`users` contains id, name, unique normalized email and password_hash. `sessions` contains id (opaque token), user_id, created_at and expires_at; add last_activity_at to retain the existing 300-second idle timeout alongside a 3,600-second absolute lifetime. Set expires_at from created_at plus the absolute lifetime; update last_activity_at on authenticated activity without extending expires_at. Authentication must reject both expiry conditions. Store sessions in MySQL, not in a process-local registry. Use UTC consistently.

`property_managers` contains id and name. `rentals.manager_id` is a nullable foreign key. Ordinary creation leaves it null; no manager UI or manager CRUD is needed in HW4. Part 3 generates 200 managers and associates all 5,000 benchmark rentals with them. Managers are distinct from authentication users.

The exact required database connection variable is `db_session_basede26`: assign the configured SQLAlchemy Engine to that module-level name in `database.py`, and bind the request session factory to it. Distinguish a database session (a unit of database work) from an authentication session (a login record).

Use reproducible versioned schema creation/migration scripts. Creating or seeding a database must not happen destructively on every server start. Preserve existing stored rows. Do not infer that live in-memory HW3 rows have been migrated unless they were actually exported and imported. The old two demonstration rows can be an explicit initial seed for an empty development database.

## HTTP API contract

All paths below belong to the existing FastAPI service. Return JSON for API errors, not HTML redirects. Use the same authorization dependency on every rental endpoint, including old convenience routes and Part 3 routes.

| Method and path | Input | Successful response |
| --- | --- | --- |
| `GET /api/health` | None | 200 with service status; no sensitive configuration |
| `POST /api/auth/login` | JSON email and password | 200 with `user` containing id, name and email; sets session cookie |
| `GET /api/auth/me` | Session cookie | 200 with the same `user` shape |
| `POST /api/auth/logout` | Session cookie when present | 204; revoke token and clear cookie; safe when already logged out |
| `GET /api/rentals` | Optional existing `q` title/address search | 200 array of Rental objects, ordered by id |
| `GET /api/rentals/{id}` | Positive id | 200 Rental object |
| `POST /api/rentals` | Six create fields above | 201 Rental object with database ID |
| `PUT /api/rentals/{id}` | Two update fields above | 200 updated Rental object |
| `DELETE /api/rentals/{id}` | Positive id | 204, empty body |
| `DELETE /api/rentals/highest` | No body | 204; preserve existing convenience behavior under auth |
| `GET /api/rentals/naive?page_size=N&offset=0` | N is 10, 50 or 200 for evidence | 200 array of Rental objects plus `manager` |
| `GET /api/rentals/fixed?page_size=N&offset=0` | Same pagination | Identical payload to naive version |

The ordinary Rental response contains id and the six stored fields. The performance response adds `manager: {id, name}` or null. Register literal paths (`highest`, `naive`, `fixed`) before dynamic id paths so they are not interpreted as IDs. Keep `/docs` available for inspection.

Invalid credentials or missing/expired/revoked sessions return 401. A missing record returns 404. Invalid input returns FastAPI/Pydantic-style 422 detail. Frontend error handling must accommodate both a string detail and validation-error detail arrays. No token, password or password hash belongs in response JSON, report logs or URLs.

Use an opaque random cookie named `s6102_session` with HttpOnly, Secure, SameSite=Lax and Path=/. Its value carries no encoded user data. Preserve logout revocation and idle-expiry behavior while moving storage to MySQL. Passwords are checked using a maintained password-hashing library; create a local teaching account through an explicit seed command with configuration supplied outside tracked source. No registration feature is required. Do not copy the demo's user-ID login.

## Browser routes and serving

Part 1 owns `/`, `/login`, `/create`, `/update?id=<id>`, and `/delete?id=<id>` using React Router. Use `Home.jsx`, `Login.jsx`, `CreateRecord.jsx`, `UpdateRecord.jsx` and `DeleteRecord.jsx` with exact capitalization. Query parameters select the record while retaining the assignment's exact `/update` and `/delete` paths. Missing or invalid IDs show a helpful selection/error state.

Use a common frontend API module with relative `/api/...` URLs and credentialed requests. Recheck `/api/auth/me` on app startup; never store the session token in React state or browser storage. A 401 clears stale authenticated UI and returns the user to login. Pass mutation callbacks as props to the required Create/Update/Delete components; use state/effects for inputs, loading and API synchronization.

For final demonstrations the existing FastAPI service serves the built React app at HTTPS port 8702, including direct navigation to every frontend route. Part 2 replaces the active Jinja homepage/login routing so it cannot claim the same paths first. Retire the old public CRUD and signed-cookie acceptance paths; an old HW3 cookie must not authenticate HW4. Historical HW3 reports remain untouched. A compatibility `/dashboard` redirect to the new protected home is sufficient; keep no separate legacy authentication system.

Part 1 produces `frontend/dist`. Part 2 serves assets and frontend entry routes only after API/docs routes are registered. Unknown `/api/...` paths must remain API 404s, never HTML. A missing frontend build should have an explicit development message, not a pretend functional UI.

Optional frontend development can use Vite on an auxiliary HTTPS port with an `/api` proxy to the backend, using the existing local certificate workflow. Do not use a Secure cookie over plain HTTP and mistake the missing cookie for a login bug. Final evidence must show the app on port 8702. Do not deploy the application.

## Database, port and measurement coordination

Git worktrees isolate files, not databases, processes or ports. Use separate development MySQL instances/containers with separate volumes and host ports if running database tests concurrently; each final evidence instance still contains database `s6102_rel`. Credentials remain in ignored configuration. Do not stop unrelated services or reset a shared database.

During independent tests auxiliary backend ports are allowed and must be labeled development-only. Part 2 coordinates exclusive use of port 8702 for each branch's acceptance evidence: first foundation/auth, then Part 1's browser flows, then Part 3's benchmarks. These evidence slots use each part's branch with foundation B and occur before the final combined merge; a session never needs the final merge to publish its completed handoff. Part 2 performs the combined integration checks after receiving those handoffs. Each session records its PID, port, database instance and running work in its handoff. Check ownership before stopping a process. Do not run the final 180-request experiment alongside database writes, browser stress tests, model inference or other heavy test workloads.

Fresh sessions can discover handoffs from sibling local Git branches or the external shared coordination folder specified in the prompts. Each writes only `part1.md`, `part2.md` or `part3.md` there. A handoff records task ID if available, branch, worktree path, completed commit hashes, foundation hash in use, passed checks, real blockers, and whether a process is still running. No credentials or cookie values. Shared handoff files do not grant permission to alter a sibling worktree. Read sibling code through committed revisions; do not merge another session's uncommitted changes.

If a dependency is still being built, finish independent units and publish the precise remaining dependency. Use task coordination tools when accessible; do not busy-poll or invent a readiness signal. A resumed session should import the published commit and continue. Part 2 integration can run the saved acceptance scripts once all branches arrive; it need not require a fourth implementation session.

## Part 3 measurement agreement

Use a many-to-one Rental → PropertyManager relationship. The naive path must execute one actual related-row SELECT per rental; `Session.get` or ordinary lazy loading may reuse an ORM identity-map object and hide the intended N queries. The fixed path uses one left join/eager-loaded data query while preserving ordering, pagination and response content.

Measure actual SQL at execution time, attributed to each request. Report total statements including authentication and session-activity writes; optionally provide a data-only count for explanation. Include queries triggered during serialization. Never derive the reported counter from page size. Expected data-query counts are N+1 versus 1; total counts are execution results, not promised numbers.

For each page size 10, 50, 200, collect 30 serial HTTP requests per implementation: exactly 180 measured requests in the selected successful run. Login, health checks and warmups are separate. Validate equal payloads and row counts first. Record end-to-end HTTP latency, a documented percentile method, deterministic seed, engine/runtime versions, code revision and run configuration. Use one worker without reload, alternate naive/fixed in a documented order, and preserve failed attempts separately.

Keep the N+1 experiment at one index state. Afterward, demonstrate a new named index on `rentals.listing_title` using the same selective equality query before and after. Do not use an already indexed foreign key or primary key as the new-index example. Save index inventory and EXPLAIN output; explain the observed plan honestly, including if MySQL chooses a scan.

## Evidence and integration

Each part owns `reports/hw04/partN/REPORT_SECTION.md`, `RUN_LOG.txt`, `AI_USE.md`, `HANDOFF.md`, and its own `reports/hw04/raw/partN/` and `reports/hw04/screenshots/partN/` directories. Pair relevant code excerpts with real output evidence for each sub-question. AI_USE answers all four assignment questions using that session's actual work and checks.

Part 2 combines fragments into shared `reports/hw04/RUN_LOG.txt`, `METRICS.md`, `AI_USE.md`, a clearly partial Parts 1–3 write-up, and `verification.parts123.json`. Include original timestamps/source labels when combining logs. The verifier reports each check individually, fails objectively, and never modifies application source. Write `verification.json` for the final tagged whole-homework run later; do not claim that a partial file proves the complete homework.

Required Postman screenshots are real Postman UI evidence: Part 2's five CRUD operations and Part 3's six size/version combinations. A collection/Newman/curl result supports testing but does not replace the requested screenshot. If UI access is unavailable, complete everything else and provide exact manual capture steps, marking those screenshots pending. No fabricated output, timing or images.

Part 2 completes local integration after both part handoffs: merge their completed branches, resolve ordinary conflicts, build React, run current HW4 API/browser/performance smoke checks, and verify fresh deep links plus API 404 handling. Rerun final measurements if integration changes executed query, auth, schema or serialization behavior. Record the exact measured revision separately from later evidence-only commits. Preserve older homework report artifacts and verify that unrelated agent/retrieval code was not changed.

## Source anchors

Existing code: `code/web_application/main.py`, `routers/auth.py`, `session_store.py`, `README.md`, `DOMAIN_SCHEMA.md`, `tests/test_api.py`, `tests/test_hw03_auth.py`, `scripts/run_hw03_web.py` and `reports/hw03/report.md` at the HW3 baseline. Existing tests assert some intentionally superseded behaviors (public API, process-memory reset, Jinja DOM, signed cookies); adapt current tests deliberately and leave historical evidence intact.

Official references supporting the design: [React JSX](https://react.dev/learn/writing-markup-with-jsx), [SQLAlchemy relationship loading](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html), [MySQL EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/using-explain.html), [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie), and [Vite server proxy](https://vite.dev/config/server-options#server-proxy). Confirm package compatibility during implementation; reuse the starter's React 18 / React Router 6 approach without blindly copying its installed dependencies or virtual environments.
