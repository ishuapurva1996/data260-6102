# Part 2: MySQL persistence and server-side sessions

Part 2 moves the existing Rental Housing Listings service from process memory to MySQL. The backend now requires a valid login for every rental operation. The foundation passed 23 real HTTPS/MySQL acceptance checks, including persistence across a server-process restart. The selected backend suite passed 122 tests with no skips. Required Postman, database, and project-structure screenshots are still pending; the saved HTTP responses do not replace them.

| Configuration | Value |
| --- | --- |
| SID4 / PREFIX | 6102 / s6102 |
| PORT_BASE | 8702 |
| SEED / VERIFY_SEED | 6102 / 266102 |
| DOMAIN_ID / domain | 6 / Rental Housing Listings |
| Database / engine | s6102_rel / MySQL 8.4.11 |
| Required connection variable | db_session_basede26 |
| Shared foundation B | f29e7cc85baf52bea30bd4bb3209d1bd79b22051 |

The foundation acceptance ran at `2026-09-28T00:28:47.592877+00:00` over `https://127.0.0.1:8702`. Its artifact records the HW3 baseline revision `5742b2aadbafee5ba208311723ea470c09811dc5` with a dirty working tree, because the foundation code had not yet been committed. That record is evidence for the pre-commit foundation gate, not an assertion that HW3 already contained this implementation. Foundation B was then committed and shared with Parts 1 and 3. A combined committed-revision run remains a separate integration step.

## Database connection and schema

SQLAlchemy maps Python objects to MySQL rows. The required variable `db_session_basede26` is the SQLAlchemy engine, which manages database connections. A request-scoped SQLAlchemy `Session` groups database work and is closed after the request. This database session is different from a login session: a login session is a row in `sessions` that lets the server recognize an authenticated browser.

The connection configuration accepts `mysql+pymysql` and the exact database name `s6102_rel`. Credentials come from private environment configuration and are not included in these artifacts. Setup is explicit; importing or starting the app does not create tables or insert sample data.

Excerpt from [database.py](../../../code/web_application/database.py):

```python
db_session_basede26 = create_engine(
    get_database_url(),
    pool_pre_ping=True,
    pool_recycle=1800,
    hide_parameters=True,
    connect_args={"charset": "utf8mb4", "init_command": "SET time_zone = '+00:00'"},
)
SessionLocal = sessionmaker(bind=db_session_basede26, expire_on_commit=False)
```

Observed output in [schema-smoke.json](../raw/part2/schema-smoke.json):

```json
{
  "repeat_migration_applied": [],
  "repeat_seed_inserted": 0,
  "rows_preserved": true,
  "rental_count": 2
}
```

The schema contains `rentals`, `users`, `sessions`, and `property_managers`, plus the migration journal `schema_migrations`. The SQL migration is [001_initial.sql](../../../code/web_application/migrations/001_initial.sql). Repeating migration and demo seeding preserved the two existing demo rentals. These rows were explicitly seeded examples; no transfer of live HW3 in-memory data is claimed.

| Table | Stored data and constraints |
| --- | --- |
| `rentals` | Auto-increment integer ID; title, address, landlord email, description, property type, and accepted terms; nullable `manager_id` foreign key |
| `users` | Auto-increment ID, name, unique normalized email, and password hash |
| `sessions` | Opaque token ID, user foreign key, creation time, fixed expiry time, and last activity time |
| `property_managers` | Auto-increment ID and name; the related entity used by Part 3 |

Excerpt from [models.py](../../../code/web_application/models.py):

```python
id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
listing_title: Mapped[str] = mapped_column(String(255), nullable=False)
property_address: Mapped[str] = mapped_column(String(255), nullable=False)
```

The saved MySQL `SHOW CREATE TABLE` output confirms `AUTO_INCREMENT`, required columns, a unique email key, and the foreign keys. MySQL checks also reject empty titles/addresses, short descriptions, unsupported property types, and unaccepted terms. Application validation additionally checks email syntax, length limits, and unexpected fields. Real MySQL tests verify distinct IDs for concurrent inserts and rollback after a failed write. Deleting the highest rental does not reset the ID sequence.

**Required output screenshot:** `reports/hw04/screenshots/part2/06-database.png` is pending. The schema JSON above is supporting evidence, not a screenshot. [MANUAL_CAPTURES.md](MANUAL_CAPTURES.md) gives the exact capture steps.

## Email/password login and persistent sessions

Login compares the supplied password with the stored Argon2 hash. Successful login creates a random token and stores it in MySQL with the user ID. The browser receives only that token in the `s6102_session` cookie; the cookie contains no name, email, or other user fields. API responses expose only the public user fields `id`, `name`, and `email`.

Excerpt from [session_store.py](../../../code/web_application/session_store.py):

```python
token = SessionToken(
    id=secrets.token_urlsafe(32),
    user_id=user_id,
    created_at=now,
    expires_at=now + timedelta(seconds=ABSOLUTE_TIMEOUT_SECONDS),
    last_activity_at=now,
)
```

Observed cookie attributes in [api-acceptance.json](../raw/part2/api-acceptance.json):

```text
HttpOnly; Max-Age=3600; Path=/; SameSite=lax; Secure
```

`HttpOnly` prevents browser JavaScript from reading the cookie. `Secure` restricts it to HTTPS. `SameSite=lax` limits when browsers attach it to cross-site requests. Reusable token values are intentionally absent from saved output.

Authentication looks up the session and user in MySQL. It rejects sessions after 300 seconds of inactivity or 3,600 seconds from creation. Accepted activity updates `last_activity_at` without extending `expires_at`. Times are stored as UTC. Logout deletes the database session and clears the browser cookie. A copied token therefore cannot restore the revoked login. Old HW3 signed cookies and forged tokens are rejected.

Observed acceptance results:

| Check | Result |
| --- | --- |
| Anonymous rental access and bad credentials | Denied |
| Valid login and cookie attributes | Passed |
| Actual server-process restart retains login and rental | Passed |
| Logout and copied-token replay | 204 logout; 401 replay |
| Logout removes database token | Passed |
| Idle expiry and absolute expiry | Both denied |

Expiry checks moved the test token's stored timestamps past the relevant boundary. They did not wait an hour or change other users' sessions. The Python tests also cover boundary times, unknown emails, repeated login, failed login replacement, and every protected ordinary rental route.

## The five CRUD operations

The API keeps the existing six-field create body. An update accepts only `listingTitle` and `propertyAddress`, so editing these two fields preserves the landlord email, description, property type, and accepted terms. All rental routes share `Depends(require_user)`.

Excerpt from [routers/rentals.py](../../../code/web_application/routers/rentals.py):

```python
router = APIRouter(prefix="/api/rentals", tags=["rentals"], dependencies=[Depends(require_user)])
```

### Add a record: POST /api/rentals

The create handler constructs a `Rental`, commits it, and returns its database-generated ID.

```python
db.add(row)
db.commit()
return rental_json(row)
```

Actual response in the acceptance artifact: **201**, ID **4**, title **HW4 acceptance 20a5a6cf67**, address **260 Verification Lane, San Jose, CA**, landlord email **verification@example.com**, description **A real MySQL acceptance record for verified persistent CRUD.**, property type **apartment**, and accepted terms **true**. This ID is a historical result from that run; new captures must use the ID returned by their own POST.

**Required adjacent screenshot:** `01-post-create.png` is pending.

### View records: GET /api/rentals

```python
statement = select(Rental).order_by(Rental.id)
```

The endpoint returns a JSON array and supports the preserved optional title/address search. The actual acceptance request used `?q=HW4 acceptance 20a5a6cf67`; it returned **200** and one matching object with ID **4**, identical to the create response. The selected API tests also cover the unfiltered list.

**Required adjacent screenshot:** `02-get-list.png` is pending. Its collection request uses the unfiltered list required by the assignment.

### View one record: GET /api/rentals/{id}

```python
return rental_json(find_rental(db, rental_id))
```

The actual request `GET /api/rentals/4` returned **200** with the same object as the POST response. A missing positive ID returns **404**.

**Required adjacent screenshot:** `03-get-by-id.png` is pending.

### Update a record: PUT /api/rentals/{id}

```python
row = find_rental(db, rental_id)
row.listing_title, row.property_address = payload.listingTitle, payload.propertyAddress
db.commit()
return rental_json(row)
```

The actual request to `/api/rentals/4` returned **200**, title **HW4 acceptance 20a5a6cf67 updated**, and address **261 Verification Lane**. The other four fields matched their original values. A subsequent request with an empty title returned **422**.

**Required adjacent screenshot:** `04-put-update.png` is pending.

### Delete a record: DELETE /api/rentals/{id}

```python
db.delete(find_rental(db, rental_id))
db.commit()
return Response(status_code=204)
```

The actual deletion of `/api/rentals/4` returned **204** with no body. Reading that ID afterward returned **404**. The acceptance harness removed only the row it created.

**Required adjacent screenshot:** `05-delete.png` is pending.

All five sanitized responses are saved together in [api-acceptance.json](../raw/part2/api-acceptance.json). [postman_collection.json](postman_collection.json) supplies login, the five CRUD requests, and logout with status assertions. It has blank credential values and remembers the ID returned by its own POST.

## Transactions and serving the React build

If a request fails, the shared database dependency rolls back uncommitted changes and closes the database session. This prevents a failed write from leaving a partial rental record. Mutation handlers commit explicitly. Authentication activity is committed before endpoint work, so a valid request can count as activity even if later validation or domain work fails.

Excerpt from [database.py](../../../code/web_application/database.py):

```python
try:
    yield session
except Exception:
    session.rollback()
    raise
finally:
    session.close()
```

The passing MySQL tests include duplicate-email rejection, required-field and foreign-key rejection, a deliberately failing request after a flushed insert, and confirmation that the failed insert is absent afterward.

The same FastAPI service serves `frontend/dist` over HTTPS using [run_hw04_web.py](../../../scripts/run_hw04_web.py). Explicit routes `/`, `/login`, `/create`, `/update`, and `/delete` serve the built React entry page. `/assets` serves its assets, and `/dashboard` redirects to `/`. A missing build returns an explanatory **503**. Unknown `/api/...` routes retain a JSON **404**, and `/docs` stays available. Fixture-build serving tests passed; final integration must also check Part 1's real production build.

Python imports use `web_application` with the repository's `code/` on the import path. This avoids confusing the project folder with Python's standard-library `code` module. The foundation exports the engine, session factory, request dependency, models, authentication dependency, and rental serializer for Part 3.

**Required project-structure screenshot:** `07-project-structure.png` is pending. The actual path inventory was saved at `2026-09-28T00:33:10.848027+00:00` in [project-structure.json](../raw/part2/project-structure.json). Its empty `frontend` list reflects the independent backend branch at that time; it is not the final combined tree.

## Verification results and remaining work

| Evidence | Actual outcome |
| --- | --- |
| [api-acceptance.json](../raw/part2/api-acceptance.json) | 23/23 real HTTPS/MySQL checks passed |
| [schema-smoke.json](../raw/part2/schema-smoke.json) | Repeated migration applied nothing; repeated seed inserted nothing; two rows preserved |
| [pytest-backend.txt](../raw/part2/pytest-backend.txt) | 122 passed, 98 warnings in 4.31 seconds; no skips |
| [api-acceptance-attempt1.json](../raw/part2/api-acceptance-attempt1.json) | Failed with ConnectError during the restart harness sequence; retained as failed evidence |
| [pytest-backend-attempt1.txt](../raw/part2/pytest-backend-attempt1.txt) | 110 passed, 4 failed; expected exception class did not match PyMySQL's CHECK-violation mapping |

The successful Python run includes 114 current web tests and eight unchanged HW3 aggregate-verifier tests. The 98 warnings are dependency deprecations. The failed constraint tests were corrected to assert MySQL error numbers `1048` for NOT NULL and `3819` for CHECK violations, while still asserting rollback and unchanged rows. Database validation was not weakened.

The foundation acceptance used the dedicated `data260-hw4-mysql` container on host port **3362**. Part 2 then released HTTPS port **8702** and that evidence database to Part 1. Later backend tests used `data260-hw4-part2-tests` on **3363**. No shared database reset is part of this workflow.

This fragment records Part 2 before final sibling integration. The completed Part 1 and Part 3 commits, their foundation ancestry, the real React build, integrated API/browser/performance checks, and combined partial verification must be recorded by the integration owner. Seven Part 2 screenshots remain pending because Postman is unavailable and database/project UI captures have not been taken. Part 4, the whole-homework PDF, collaborator access checks, the `hw4` tag, and verification against that tag remain later work.

## Review follow-up

The expanded reviewed backend suite passed **130 tests**, with no skipped
database checks. The [output](../raw/part2/pytest-backend-reviewed.txt) has a
[provenance record](../raw/part2/pytest-backend-reviewed.metadata.json) naming the
real MySQL instance, command, revision, and output hash.

Review caught one preserved-behavior regression: MySQL LIKE did not match
`Straße` when searching for `STRASSE`. A real MySQL regression test failed first;
the ordinary listing route now uses the same Unicode casefold substring test
as HW3 after selecting rows in ID order. This loads all ordinary listings for
search, consistent with that route's unpaginated contract. It does not change
the two separately paginated performance endpoints.

The acceptance harness now attempts server shutdown and resource closure even
if database cleanup fails, and records cleanup failures without secret details.
HW4 fixture imports are lazy so they do not force the web stack into the
repository's separate retrieval environment. These changes have focused tests.
