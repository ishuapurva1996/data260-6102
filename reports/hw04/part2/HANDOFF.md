# Part 2 handoff

The shared backend foundation is available locally at **f29e7cc85baf52bea30bd4bb3209d1bd79b22051**. Merge it into each sibling branch to preserve common ancestry. Part 2's final integration of Parts 1–3 is still pending completed sibling commits and their evidence handoffs.

| Item | Value |
| --- | --- |
| Task | 01a0e563-f790-7aa0-8dd0-e0d6c24fff71 |
| Worktree | /Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend |
| Branch / final integration branch | codex/hw4-part2-backend |
| Verified HW3 baseline | 5742b2aadbafee5ba208311723ea470c09811dc5 |
| Foundation B | f29e7cc85baf52bea30bd4bb3209d1bd79b22051 |
| Final integrated commit | Pending sibling completion and local merge |
| Coordination file | /Users/pragyaapurva/Documents/SJSU/DATA 260/HW4_coordination/part2.md |

## Available backend

- MySQL database `s6102_rel`; exact exported engine variable `db_session_basede26`.
- Shared `Rental`, `User`, `SessionToken`, and `PropertyManager` models, migration `001_initial.sql`, and explicit repeatable setup/seed CLI.
- Argon2 email/password login, opaque HTTP-only secure cookie, MySQL session lookup, logout revocation, 300-second idle expiry, and 3,600-second absolute expiry.
- Protected create/list/ID-read/update/delete, plus preserved search and delete-highest routes. Create has six fields; update has only title/address.
- HTTPS launcher and minimal React asset/deep-link serving already included in B. A missing frontend build returns 503; unknown API routes remain JSON 404.

[FOUNDATION.md](FOUNDATION.md) is the committed interface agreement. Use `web_application` imports with `code/` on Python's path. Part 3 registers its literal routes before the ordinary rental router and uses the exported shared dependencies.

## Runtime ownership and test results

The foundation harness stopped its own HTTPS process and released port **8702** to Part 1 at `2026-09-28T00:33Z`, as recorded in external coordination. This report has no continuing API process or PID to hand off. Check current shared coordination before starting any process; later owners may already be running.

The evidence database remains in dedicated container `data260-hw4-mysql`, host **127.0.0.1:3362**, database `s6102_rel`, with its persistent volume. It was handed to Part 1 without reset. Part 2's subsequent selected tests use the separate `data260-hw4-part2-tests` container on **3363**. Part 3 reported its own instance on **33363**. Private configuration remains outside tracked files and must not be printed or copied into evidence.

| Check | Outcome / artifact |
| --- | --- |
| Real HTTPS/MySQL foundation acceptance | 23/23 pass; `raw/part2/api-acceptance.json` |
| Actual process restart | Existing login and rental retained |
| Repeat migration and seed | No new migration/seed rows; two rentals preserved; `raw/part2/schema-smoke.json` |
| Selected web tests on separate real MySQL | 122 passed, 98 warnings, no skips, 4.31 s; `raw/part2/pytest-backend.txt` |
| First acceptance attempt | Failed ConnectError; retained in `api-acceptance-attempt1.json` |
| First test attempt | 110 passed, four failed driver-exception assertions; retained in `pytest-backend-attempt1.txt` |
| Postman/manual UI evidence | Seven screenshots pending; collection and exact steps provided |

The successful foundation acceptance identifies the dirty baseline working tree that was tested before B was committed. Do not relabel it as a committed-revision or final integrated run. The project path inventory similarly reflects the backend branch before the frontend merge.

## Integration dependencies and next actions

1. Obtain Part 1's completed commit on `codex/hw4-part1-react`, with B merged, production build, browser outcomes, screenshot inventory, and released port/database ownership. Its final hash is not recorded here yet.
2. Obtain Part 3's completed commit on `codex/hw4-part3-performance`, with B merged, generator, performance router/counter, index migration, all 180 measured requests, equivalence checks, and released runtime ownership. Its final hash is not recorded here yet.
3. Follow the port-8702 order: foundation/auth completed; Part 1 browser flows; Part 3 measurements; final combined integration. Do not run heavy tests or database writes during Part 3's measurement slot.
4. Merge both completed branches into `codex/hw4-part2-backend`, resolve ordinary conflicts, and preserve common foundation ancestry. Do not import unrelated dirty main-checkout changes, including `.gitignore`.
5. Build the real frontend, serve it through the shared HTTPS launcher, and run the integrated API/browser checks, deep-link/API-404 checks, performance equivalence and SQL-count checks. Rerun the full performance experiment if integration changes measured query/auth/schema/serialization behavior.
6. Record the measured revision, final integrated commit, evidence database, run configuration, individual check outcomes, and clearly partial Parts 1–3 verification. Combine report fragments with their original timestamps and provenance.
7. Capture the five Postman CRUD responses and database/project screenshots following [MANUAL_CAPTURES.md](MANUAL_CAPTURES.md). Confirm each image depicts its labeled operation and keep tokens, credentials, and password hashes out of view.

Local commits are authorized. Push, PR, deployment, changing old tags, and creating `hw4` are outside this work. Part 4, the final whole-homework PDF, collaborator access confirmation, and verification on the eventual `hw4` tag remain later submission work.

Review follow-up:130tests now pass on isolated3363; see reviewed pytest output
and metadata. Ordinary q-search now preserves Python casefold Unicode behavior.
Acceptance cleanup is failure-resilient. Final integration remains pending.
