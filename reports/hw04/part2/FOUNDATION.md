# HW4 foundation B

This commit is the early shared backend foundation. Find its exact commit with `git log -1 --format=%H -- reports/hw04/part2/FOUNDATION.md` or the external Part 2 coordination note. Merge B into each sibling branch; do not cherry-pick it. Baseline: `5742b2aadbafee5ba208311723ea470c09811dc5`.

## Proven checks

Real MySQL **8.4.11**, database **s6102_rel**, isolated container **data260-hw4-mysql**, host **127.0.0.1:3362**. The schema migration created all four shared tables plus its migration journal. Repeated migration and demo seed preserved the two existing rentals. HTTPS port8702 acceptance passed **23 checks**, including five CRUD operations, correct cookie attributes, denied anonymous/bad login, logout/copied-cookie rejection, idle/absolute expiry, and rental plus login persistence across an actual server-process restart. `raw/part2/api-acceptance.json` contains sanitized responses. It truthfully records the pre-commit dirty tree used for the foundation gate; a committed-revision run follows separately. A first harness attempt failed due to restart readiness; retained as `api-acceptance-attempt1.json`, not selected evidence.

## Imports and extension points

Put repository `code/` on Python's import path; import **web_application**, never `code.web_application` (stdlib collision). Launcher already does this with Uvicorn `--app-dir code`. Within routers use relative imports.

- `web_application.database.db_session_basede26`: configured SQLAlchemy Engine.
- `database.SessionLocal`: `sessionmaker(expire_on_commit=False)`.
- `database.get_db(request)`: request dependency sharing one Session, rollback on exception, always close; mutation handlers commit explicitly.
- `models.Base`, `Rental`, `User`, `SessionToken`, `PropertyManager`.
- `Rental` snake_case fields: `id`, `listing_title`, `property_address`, `submitter_email`, `description`, `property_type`, `terms_accepted`, nullable `manager_id`; relationship **manager**.
- `routers.auth.require_user`: same auth dependency for every rental route. One joined session/user lookup and activity commit on accepted requests. No process-local auth.
- `schemas.rental_json(row)`: seven ordinary camelCase API fields; performance may append `manager`.
- `main.create_app(session_factory=None, clock=utc_now, idle_timeout=300, frontend_dist=None)`: configurable test seams; production uses fixed300s idle/3600s absolute. MySQL DATETIME values are UTC-naive.

Part3: register your literal performance router immediately before `app.include_router(rentals.router)` at the marked insertion point in main.py. Follow the same dependency; include actual auth/activity statements in SQL metrics. Part3 owns index003. Ordinary create leaves manager_id null.

## Reproduce locally

Use Python3.12 and `pip install -r requirements.txt`. Put private variables from `.env.hw04.example` in an ignored `.env` or load them from an external file. Set HW4_DATABASE_URL to mysql+pymysql and database s6102_rel; account vars are HW4_SEED_NAME, HW4_SEED_EMAIL, HW4_SEED_PASSWORD. Never commit or print credential values.

```sh
python scripts/hw04/db_setup.py --migrate --seed-demo --seed-account
python scripts/run_hw04_web.py --env-file /path/to/private/app.env
python scripts/hw04/part2/acceptance.py --env-file /path/to/private/app.env --manage-server
```

The DB setup CLI reads exported environment variables (load dotenv before invoking it). `--create-database` is optional for a fresh instance; Docker already created this database. Migration defaults through001, so it does not silently apply the Part3 index. There is no schema/seed operation on server startup. Demo rows are explicit recreated examples, **not** a migration of live HW3 memory.

Part1 may read the external private app.env path listed in coordination using dotenv; never copy its contents into logs. Build `frontend/dist` before starting the server. Explicit React routes `/`, `/login`, `/create`, `/update`, `/delete` serve index.html, `/assets` serves the build assets, `/dashboard` redirects to `/`. Missing build returns503 with instructions. Unknown `/api/...` remains JSON404, and `/docs` is retained. No Jinja routes or old signed-cookie acceptance remain active.

## Evidence slots and remaining scope

Check external `HW4_coordination/part2.md` for port ownership. Foundation check releases its own server after completion; Part1 gets8702 next, followed by Part3, then combined integration. Do not reset shared MySQL data or stop unrelated servers. Part3 uses its own33363 database.

Foundation is not final integration. Full current tests, frontend real-build checks, sibling merges, final query measurements and aggregate partial verification follow. Postman UI screenshots are not replaced by HTTPX outputs. Parts4/finalPDF/collaborators/hw4 tag/tagged verification remain outside this run.
