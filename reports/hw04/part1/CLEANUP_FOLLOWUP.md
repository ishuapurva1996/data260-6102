# Browser interruption cleanup follow-up

The browser runner now removes its own test rental when the Python wrapper is
interrupted after creation. This is a test-harness fix. It does not change React,
the six-field create request, authentication, the database schema, or the API.

The follow-up started from clean Part 1 commit
`5db1d4a12d996fa5eb45e9b71d7b2dbcd0708991` on `codex/hw4-part1-react`.
Foundation `f29e7cc85baf52bea30bd4bb3209d1bd79b22051` remains an ancestor.
Part 2 confirmed that port 8712 and its existing evidence database on 3362 could
be used for these checks. The original port 8702 evidence is preserved.

## Cause and change

Previously, JavaScript kept the newly created ID only in memory. On cancellation,
Python terminated Node, so JavaScript's `finally` block could not reliably delete
the row. A real regression reproduced this: POST created ID 11, the wrapper exited
with interruption status 143, and ID 11 remained in MySQL. The regression verified
its exact marker and removed only that row as separately recorded recovery.

The wrapper now creates a **journal**, a small private file that records one run's
random UUID, creation phase, and database ID. A UUID is a randomly generated
identifier; the browser also puts this run's identifier in the description and
test email. The journal directory has permission 0700 and the file has permission
0600, so only its owner can access them. It contains no credentials or cookies.

The browser saves intent before POST and atomically replaces the journal with the
returned ID immediately after the response. Python stops its browser and server
before cleanup. It then locks the selected row in a database transaction, compares
both ownership fields exactly, and deletes only the matching ID. If the response
did not reach the journal, it can locate one exact marker/email match. Ambiguous
matches and ownership mismatches are refused. A row already deleted by the normal
UI flow is safe. Failed or uncertain cleanup retains its journal and records the
recovery path in `runtime.json`; database exception messages are not serialized.

Node handles SIGTERM and SIGINT by closing Chromium. Python ignores repeated
signals while it finishes bounded teardown and records the cleanup result. A
leftover journal replacement file cannot turn a successful database cleanup into
a false recovery warning.

## Checks actually run

All new outputs are under `reports/hw04/raw/part1/cleanup-followup/`.

| Check | Actual result | Evidence |
|---|---|---|
| Before-fix confirmed-create interruption | Expected failure: ID 11 remained; guarded regression recovery removed it | `red-confirmed/check.json` |
| Cleanup guards using SQLite | 17 passed, including mismatch, already absent, missing ID, ambiguity, malformed journal, and sanitized connection failure | `static-checks.json` |
| Real Chromium/MySQL cancellation after confirmed POST | 8 passed; ID 12 deleted by wrapper, exit 143 recorded, existing rentals unchanged, all 7 captured processes stopped, port reusable | `interrupted/check.json`, `interrupted/runtime/runtime.json` |
| Normal real browser workflow | 12 passed, including six-field create, update, restart persistence, delete and logout | `success/real-browser.json` |
| Controlled idle expiry | 2 passed with the existing two-second test seam | `success/expiry-browser.json` |
| Runtime and restart checks | 6 passed; normal UI deletion of ID 13 verified, final cleanup reported `already_absent` | `success/runtime.json` |
| Node syntax, Python compilation, whitespace check | All exited 0 | `static-checks.json` |
| Final source, database, process, port and private-value checks | Source hashes match; IDs 11–13 absent; two original rentals remain; recorded processes absent; 8712 bindable; no private password/connection values found in new evidence | `final-check.json` |

The successful interruption finished at `2026-09-28T01:09:26.780467+00:00`.
The normal workflow finished at `2026-09-28T01:09:58.873466+00:00`.
Both ran the uncommitted follow-up against recorded HEAD `5db1d4a`; their source
SHA-256 values identify the exact changed files and match the final source.

Two setup failures are retained and are not counted as passing evidence:
`red/` rejected the first test email domain with HTTP 422 before creation, and
`green/` stopped before server startup because `Path.open` does not accept an
`opener` argument. The domain and private-file creation were corrected before
the selected runs. No rental was created by either setup attempt.

Screenshots are saved separately under
`reports/hw04/screenshots/part1/cleanup-followup/`: 14 from normal success and 4
each from the interrupted run and the two browser reproduction attempts. The
normal created-listing screenshot was visually inspected. The interrupted run
deliberately stops before the usual created-listing screenshot; its proof is the
actual POST checkpoint, database query, process observations and cleanup output.

## Reproduction and recovery

Use the existing private environment file, a built frontend, Python dependencies,
Node and Playwright. Coordinate the port/database slot before running:

```sh
python tests/check_hw04_part1_interruption.py \
  --env-file /path/to/private/app.env --node node --port 8712 \
  --raw-dir reports/hw04/raw/part1/cleanup-followup/new-interruption \
  --screenshots-dir reports/hw04/screenshots/part1/cleanup-followup/new-interruption

python tests/browser_hw04_part1_runtime.py \
  --env-file /path/to/private/app.env --node node --port 8712 \
  --raw-dir reports/hw04/raw/part1/cleanup-followup/new-success \
  --screenshots-dir reports/hw04/screenshots/part1/cleanup-followup/new-success

python -m pytest tests/test_hw04_part1_cleanup.py -q
```

If cleanup fails, inspect `rental_cleanup` in that run's `runtime.json`. Keep the
reported journal. After the owned processes have stopped and database access is
restored, `cleanup_rental(Path(recovery_path), engine)` in
`tests/browser_hw04_part1_runtime.py` can retry the same guarded operation with
an engine configured from the private environment file. Do not widen deletion
to a title prefix, change an ownership marker, or reset the database. SIGKILL or
host loss cannot execute Python's `finally`; retained journals support recovery,
but those scenarios were not claimed as live acceptance checks.

## Review and handoff

An independent reviewer checked ownership and failure paths and added the 17
guard tests. Its actionable findings about leftover `.next` files and regression
teardown evidence were fixed before the selected checks. A separate reuse review
found no suitable behavior-equivalent consolidation: regression recovery must
remain independent of the journal it is testing. Further reviewer dispatch hit
the host's agent limit; quality, efficiency and the final diff were reviewed
inline. No remaining actionable finding was retained. No frontend lint/typecheck
command exists, and neither is claimed here.

Changed source files are `tests/browser_hw04_part1.cjs`,
`tests/browser_hw04_part1_runtime.py`, `tests/check_hw04_part1_interruption.py`, and
`tests/test_hw04_part1_cleanup.py`. Documentation and new evidence are confined to
Part 1. The local follow-up commit must be incorporated by Part 2, whose previous
integrated tip was `2d03ae4074a8d6d69a9e84dacf1ce3fea7d2bafb`. The full follow-up
hash is published after commit in `HW4_coordination/part1.md`. Part 1 has no
remaining manual capture requirement for this fix. All owned processes are
stopped and port 8712 is released. Part 2/3 manual images and later homework
deliverables remain outside this follow-up.
