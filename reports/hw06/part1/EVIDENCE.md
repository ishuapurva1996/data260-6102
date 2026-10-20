# Part 1 evidence notes

Student: Pragya Apurva. Code handoff is ready for integration; live assignment
evidence is incomplete. This file is part-specific and does not replace A's
canonical report, run log, metrics, AI-use statement or final verifier.

Tested implementation commit: `af1dc160918d8e8ba9e04dbba1a6f099580d4791`.
Foundation: `51cfd410400683acf7cf9f7bb88a9581ba3834bb`.

## Observed verification

- Proof-first check at 2026-10-20 06:10 UTC failed during collection because
  `src.hw06_documents.schemas` did not exist yet. The complete exploratory red
  log remains external; it is not successful application evidence.
- Final committed-source run at 2026-10-20 06:15 UTC: **255 passed, 45 skipped**,
  including **124 passing Part 1 cases**. Skips require real configured MySQL.
  These are in-process engineering checks with disposable BSON-roundtripping
  fixtures, injected authentication and no shared data deletion.
- The tests cover CRUD, defaults, full PUT replacement, immutable `created_at`,
  server timestamps, millisecond/UTC roundtrips, malformed and missing IDs,
  missing/blank/long title, invalid enum/type/date inputs on create and update,
  forbidden client timestamps/IDs, auth on all routes, invalid JSON, sanitized
  storage/unexpected errors, existing-collection preservation and capture cleanup.
- Actual MongoDB probe at 2026-10-20 06:12:26–06:12:28 UTC acquired A's shared
  runtime lease, then `MongoConnection.ping()` raised
  `ServerSelectionTimeoutError`. No CRUD or HTTP capture was attempted.
  `mongod` and `mongosh` were absent from PATH. The raw file records the earlier
  working source hashes and foundation HEAD; it is not a committed-source CRUD run.
- A committed-source probe at 2026-10-20 06:15:18 UTC found the runtime leased
  by `E-file-cli` for Part 4 generation. It exited 2 without connecting or taking
  the lease. That result is a lease gate, not a second MongoDB failure.
- Python AST parsing and selected-file whitespace checks passed. No configured
  project lint/typecheck command was found. Deprecation warnings arise from the
  existing pinned FastAPI/HTTPX runtime.

## Selected files

| File under `reports/hw06/` | Meaning |
| --- | --- |
| `raw/part1/offline-regression.txt` | Actual commands, UTC start/end, console results and exit code |
| `raw/part1/offline-test-results.json` | Actual test receipt, source hashes, 124 Part 1 case results and regression counts |
| `raw/part1/live-availability-initial.json` | Real shared MongoDB timeout, sanitized configuration and source hashes |
| `raw/part1/live-availability-lease-busy.json` | Committed-source attempt correctly declined while the shared lease was busy |
| `part1/source-snippets.json` | Short excerpts with verified line locations, hashes and pending live-output pairing |
| `part1/AI_USE_FACTS.json` | Part-specific facts for A's four AI-use answers |

The evidence-only commit does not change the tested implementation. The raw
configuration still names A's foundation `source_commit`; the explicit test
receipt/source hash identifies B's actual tested code. A must set and verify the
actual integrated server revision before final acceptance.

## Remaining live evidence and integration

A must mount `create_router(DocumentService(connection.database))` in the
existing application, using the same shared connection as Part 2, install shared
error handlers, keep existing authentication and the sanitized validation
handler, and add shared CORS. FastAPI request models already parse JSON. The
foundation application has neither the new router mounting nor CORS support.
No shared application/configuration/dependency files were edited by B.

The MongoDB rental representation does not auto-sync the existing MySQL rental
data. This distinction and the full API contract are documented in
`scripts/hw06/part1/README.md`.

That guide contains exact acceptance commands, private-cookie/TLS inputs,
credentialed CORS checks, Compass/mongosh filters and fixture cleanup steps.
`python -m scripts.hw06.part1.verify` acquires A's lease, checks the shared
database and existing login, captures real responses for all five routes plus
invalid POST/PUT bodies, checks stored validators, and removes only its fixture
IDs. `--keep-sample` explicitly retains one new sample for a database screenshot;
its exact cleanup route is recorded. It launches no server.

After MongoDB and SQL/login are restored, A must capture real CRUD responses,
validation failures, BSON validation rejections, and successful operation plus
Compass/mongosh screenshots. Show Pragya Apurva in every terminal screenshot and
pair each output with its matching source excerpt. No such screenshot or live
success is claimed here. **A must rerun final combined-app acceptance after
integration**, including preserved SQL routes, login and CORS.
