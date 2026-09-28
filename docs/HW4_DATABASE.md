# HW4 MySQL setup and shared models

The application uses MySQL database `s6102_rel`. `code/web_application/database.py`
exports the exact required Engine name `db_session_basede26`, the bound
`SessionLocal` factory, and the request dependency `get_db`. Application startup
does not connect, create tables, reset IDs, or seed data. Request handlers commit
their own changes; the dependency rolls back on exceptions and always closes its
database session. Authentication sessions are separate rows in `sessions`.

Use MySQL 8.0.16 or later so MySQL enforces the schema's `CHECK` constraints.
Install the repository's pinned Python requirements in a separate environment.
Supply `HW4_DATABASE_URL` through the environment with driver `mysql+pymysql` and
database name `s6102_rel`; both are validated. For example, a dedicated local
instance with no root password could use the template in `.env.hw04.example`.
Set your own credentials in ignored local configuration; never commit credentials
or pass teaching passwords as command-line arguments. URL-encode reserved
characters in connection passwords. No env file is loaded implicitly.

From the repository root, after configuring the environment:

```sh
python scripts/hw04/db_setup.py --create-database --migrate
python scripts/hw04/db_setup.py --seed-demo
python scripts/hw04/db_setup.py --seed-account
```

`--create-database` requires permission to create the database and can be omitted
when it already exists. The account seed requires `HW4_SEED_NAME`,
`HW4_SEED_EMAIL`, and `HW4_SEED_PASSWORD`. It trims and normalizes the email,
hashes the password using Argon2, and preserves an existing account with the same
email, including its password. The optional demo seed inserts two HW3 example
rentals only if the rentals table is empty. This does **not** import any live HW3
process-memory rows. Seeds never delete data or reset auto-increment sequences.

Migration `001_initial.sql` creates `users`, `sessions`, `property_managers`, and
`rentals` with primary keys and foreign keys. `schema_migrations` records each
applied file's version and SHA-256 checksum. Repeated setup skips applied files;
editing an applied file fails instead of silently changing the schema. MySQL DDL
commits implicitly, so migrations use additive, repeatable statements to allow a
failed migration to be rerun. Run setup once at a time for a database. If a table
already existed with an incompatible shape, reconcile it with a new migration;
`CREATE TABLE IF NOT EXISTS` does not replace or upgrade an existing table.

The migration runner defaults to version `001`. It deliberately leaves Part 3's
new `listing_title` index absent until its before/after experiment. Once that
migration exists, `--migrate --through 3` opts in to it. The initial foreign-key
indexes are `ix_sessions_user_id` and `ix_rentals_manager_id`; no initial index is
created on `rentals.listing_title`.

`models.py` exports `Base`, `User`, `SessionToken`, `PropertyManager`, and `Rental`.
Rental attributes use snake case; API schema code maps them to the established
camelCase names. `Rental.manager_id` is nullable and ordinary creates leave it
null. `Rental.manager` is the many-to-one relationship used by Part 3. Managers
are independent from authentication users. Rental and user IDs are assigned by
MySQL auto-increment. Session token IDs are case-sensitive opaque ASCII strings.

All `created_at`, `expires_at`, and `last_activity_at` values are UTC stored as
naive MySQL `DATETIME(6)` values: a missing timezone means UTC, never local time.
`utc_now()` supplies that representation. MySQL connections also set their
session time zone to `+00:00`. Auth code must not compare aware Python datetimes
with these values without first normalizing to naive UTC.

Imports use the package name `web_application`, with the repository's `code/`
directory on `sys.path`. Sibling imports are relative. Do not import
`code.web_application`, which can collide with Python's standard-library `code`
module. The setup CLI and HW4 launcher establish the package path explicitly.

Worktrees share ports and MySQL data. Use isolated MySQL instances for concurrent
development. Before evidence runs on port 8702, coordinate the database instance,
process owner, and time slot through the shared handoff. Never reset a sibling's
database or stop an unrelated server.
