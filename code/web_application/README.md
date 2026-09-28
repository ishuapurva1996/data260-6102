# Rental Housing Listings backend

Current implementation: MySQL-backed HW4. Start using `scripts/run_hw04_web.py`
from the repository root; see the root README and `docs/HW4_DATABASE.md`.

Package name: `web_application` with `code/` on sys.path; do not import the Python
stdlib-conflicting name `code.web_application`. SQLAlchemy engine variable is
`db_session_basede26`, while request sessions and login records are distinct.
Schema is applied explicitly with `scripts/hw04/db_setup.py`; startup never seeds
or resets data. Legacy templates/static files remain historical assets but are
not mounted and cannot bypass API authentication.

The launcher runs one HTTPS worker on 8702 and serves `frontend/dist` after a
frontend build. API/docs routes have priority; unknown API paths remain 404 JSON.
All rental routes use `routers.auth.require_user`. See
`reports/hw04/part2/FOUNDATION.md` for exported dependencies and the early commit.
