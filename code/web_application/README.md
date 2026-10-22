# Rental Housing Listings backend

Current implementation: HW7 JWT bearer authentication with MySQL users, rental
role permissions, and the integrated HW6 MongoDB document/memory routes. See
`docs/HW7_PART1.md` for setup and `scripts/run_hw06_web.py` for the HTTPS launcher.

Package name: `web_application` with `code/` on sys.path; do not import the Python
stdlib-conflicting name `code.web_application`. SQLAlchemy engine variable is
`db_session_basede26`; SQLAlchemy sessions are database units of work.
Schema is applied explicitly, including `scripts/hw07/db_setup.py`; startup never seeds
or resets data. Legacy templates/static files remain historical assets but are
not mounted and cannot bypass API authentication.

The launcher runs one HTTPS worker on 8702 and serves `frontend/dist` after a
frontend build. API/docs routes have priority; unknown API paths remain 404 JSON.
All rental routes use `routers.auth.require_user`; create/update additionally
require writer/moderator and delete requires moderator. No cookie authenticates
a current route. Historical session rows remain stored but are not consulted.
