# Homework 7 Part 1 checkpoint

Pragya Apurva · [semester repository](https://github.com/ishuapurva1996/data260-6102)

Baseline setup and Part 1 are complete. This checkpoint contains authentication,
authorization, linting, and regression evidence. Parts 2–6, the final PDF,
tagged-commit verifier, and `hw7` submission tag remain for later sessions.

## Configuration and provenance

| Item | Verified value |
| --- | --- |
| SID4 / PORT_BASE / PREFIX | 6102 / 8702 / s6102 |
| SEED / VERIFY_SEED / DOMAIN_ID | 6102 / 266102 / 6, Rental Housing Listings |
| Hardware | Apple M4, 24 GiB RAM |
| Web runtime | Python 3.12.13; MySQL 8.4.11; existing MongoDB and Ollama |
| Local model | qwen2.5:7b; digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e` |
| Preserved HW6 regression settings | seed 6102, temperature 0, context 8192, output limit 1024, memory window 12 |
| Integrated HW6 baseline | `d232421f0e49d4f6a1cc425bb5e485ceffb90f2d` |
| Tested Part 1 application | `c0c8e8671657cf94a03ecaadcdfe0124c5be11f9` |
| Development branch | `codex/hw7-part1` |

The baseline matched the remote `codex/hw6-foundation` branch. Its checkout was
clean before work began. The same checkout and shared root application were
extended; the HW6 branch pointer and earlier reports were preserved. The later
evidence-only commit contains these checkpoint files without changing the tested
application. No submission tag has been created.

## Implemented behavior

Migration 005 adds unique usernames and reader/writer/moderator roles to MySQL
users. Existing IDs and Argon2 password hashes remain usable. Three private role
accounts were seeded idempotently. Passwords and the random signing secret stay
outside Git. See [setup and operation](../../docs/HW7_PART1.md).

`POST /auth/login` accepts JSON username/password and returns an HS256 JWT with
a 900-second lifetime. `GET /auth/me` returns the authenticated identity and
current MySQL role. Signature, algorithm, issuer, audience, required timestamps,
expiration and subject are validated. The database role is checked on each
request, so a demotion takes effect even for an existing token.

Both rental APIs and auxiliary manager writes enforce the role matrix. HW6
document, chat, memory, aggregate and configuration routes use the bearer
principal; memory ownership checks remain in place. The frontend sends bearer
headers, uses the exact `/auth/*` paths, and clears identity and rental state on
logout or a 401. Tokens stay in memory, so reloading requires login. The Vite
development proxy handles both `/auth` and `/api`.

Long-running HW6 clients renew before sending an application request. They do
not replay a write after an ambiguous response or failed renewal. Browser logout
clears local state; a copied JWT remains valid until expiry unless its account is
removed. Server-side token revocation was not added.

## Acceptance results

The [committed-source acceptance data](raw/part1/acceptance.json) records
`source_dirty: false`. The run took place on 2026-10-22 at 00:15:49–00:15:59 UTC
(October 21 in California). All **79 real HTTPS checks passed**, using MySQL,
MongoDB and Ollama without mocked services.

| Request | Reader | Writer | Moderator |
| --- | --- | --- | --- |
| Valid login and identity | 200 | 200 | 200 |
| Rental list and read | 200 | 200 | 200 |
| Create | 403 | 201 | 201 |
| Update | 403 | 200 | 200 |
| Delete | 403 | 403 | 204 |

Invalid login, missing/corrupted/expired tokens, and an actual legacy cookie
alone returned 401. Across the 79 checks, the observed status counts were 36×200,
5×201, 5×204, 12×401 and 21×403. Owned fixtures were cleaned up.

The same run passed **10 Chromium checks** at desktop and mobile widths. It
covered role restrictions, form creation/deletion, memory-only token storage,
reload/logout cleanup, and clearing protected data after a real backend 401.
That last case deliberately replaced one outgoing bearer credential; its HTTP
response was produced by the real backend, not mocked.

The [HW6 smoke regression](raw/part1/hw6-smoke.json) passed **15 checks**, including
real document CRUD, chat/model response, persisted memory, aggregation, ownership
denial and file-memory commands. The [supplemental live checks](raw/part1/supplemental-live.json)
passed **8 checks**: real expiry and renewal using an explicitly temporary
two-second TTL, plus frontend/auth/API access through Vite. Normal configuration
remains 900 seconds.

## Automated tests and lint

| Check | Result | Test boundary |
| --- | --- | --- |
| Compatible web regression suite | 971 passed, 25 skipped | TestClient/HTTPX; real transactional MySQL where required; injected storage/model doubles in their named unit suites |
| Interrupted migration recovery | 8 passed | Real MySQL 8.4 in a separate disposable container; resume after each DDL step, preserve legacy rows/hashes, repeat safely |
| Historical MCP regression suite | 156 passed | Existing dedicated MCP environment; includes stdio; controlled doubles in applicable unit tests |
| Ruff check/format and pre-commit | Passed | Pinned versions, configured current-backend/HW7 scope |
| Dependency compatibility | Passed | 88 installed packages checked |
| Frontend production build | Passed | Existing React/Vite application |

The web suite's 25 skips are 17 existing opt-in cases and the 8 migration cases
that require their explicit isolated administrator configuration. The latter
were executed separately and passed. Heavy historical retrieval tests were not
run. Client lifecycle tests use MockTransport and a controlled clock; they are
not counted as live acceptance checks.

The genuine commit attempt at **00:14:30 UTC** was rejected by the installed
Ruff hook: 13 lint findings, including an unused import and a lambda assignment;
the format hook also changed 14 files. The issues were fixed, imports sorted,
files formatted and restaged. At **00:15:36 UTC**, both hooks passed and commit
`c0c8e86` succeeded. No hook bypass was used. Mechanical formatting also covered
the current backend files in the declared Ruff scope.

[RUN_LOG.txt](RUN_LOG.txt) retains the actual commands, UTC timestamps, results,
failed attempts and corrections. Early optional-dependency and application-user
DDL failures remain visible. The final compatible environments and separate
migration test service resolved them. The web regression run tested the final
code before the successful commit; no source changed between that run and the
commit. Final live checks then tested the committed revision.

## Selected evidence

HTTP images are clearly labeled screenshots of **recorded live output**. The
terminal image shows a real browser-hosted PTY session replaying labeled
historical hook output, followed by current Git/Ruff commands. It is not a native
Terminal-window capture or a claim that the old commit ran again.

| Requirement | Evidence | Main implementation |
| --- | --- | --- |
| Valid/invalid login | [login](screenshots/p1-login.png) | [auth router](../../code/web_application/routers/auth.py) |
| Missing token | [missing](screenshots/p1-missing-token.png) | [JWT validation](../../code/web_application/jwt_security.py) |
| Invalid/expired token | [invalid](screenshots/p1-invalid-token.png) | JWT validation and auth dependency |
| Reader denied / writer create | [create](screenshots/p1-create.png) | [rental routes](../../code/web_application/routers/rentals.py) |
| Writer denied / moderator delete | [delete](screenshots/p1-delete.png) | Rental role dependencies |
| Authenticated read | [read](screenshots/p1-read.png) | Rental auth dependency |
| Hook failure, correction, commit | [terminal](screenshots/p1-lint-terminal.png) | [.pre-commit-config.yaml](../../.pre-commit-config.yaml), [pyproject.toml](../../pyproject.toml) |

[Screenshot manifest](screenshots/manifest.json) records provenance and hashes.
[Baseline](raw/part1/baseline.json) and [final preservation check](raw/part1/preservation.json)
confirm original user IDs/hash fingerprints and SQL/Mongo counts. The one extra
legacy session was created by the genuine baseline login; JWT logins create no
session records. No private workflow artifacts or credentials are included.

There are no remaining Part 1 functional blockers. Collaborator access and final
report/tag packaging remain submission-stage work. Next, freeze the Part 2/3
fixtures, expected results and model settings before measured agent-loop runs.
