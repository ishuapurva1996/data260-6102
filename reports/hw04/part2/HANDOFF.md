# Part 2 and integrated Parts 1–3 handoff

Parts 1–3 are merged locally on **codex/hw4-part2-backend**. Current tested code **307b1d9adc050e422a205e2d3219914c2234d816** passed the cleanup follow-up checks; the original API and integration evidence at `e7382ddb9cc5e0a5cd867653254a0c6f62f2f9c7` is preserved below. The partial verifier reports **automated_status: pass** and **status: incomplete** because 12 required manual captures remain unavailable. There are no unfinished sibling implementation dependencies.

| Item | Value |
| --- | --- |
| Task | 01a0e563-f790-7aa0-8dd0-e0d6c24fff71 |
| Worktree | /Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part2-backend |
| Integration branch | codex/hw4-part2-backend |
| Verified HW3 baseline | 5742b2aadbafee5ba208311723ea470c09811dc5 |
| Early foundation B | f29e7cc85baf52bea30bd4bb3209d1bd79b22051 |
| Initial Part 1 handoff | 5db1d4a12d996fa5eb45e9b71d7b2dbcd0708991 |
| Current Part 1 cleanup handoff | 5d84f1a038cfdfcedb667b8047e06d5ef095164b |
| Imported Part 3 final commit | 4f8390b84752d861ea6b47c5ac8615680192d841 |
| Current tested code | 307b1d9adc050e422a205e2d3219914c2234d816 |
| Initial integrated tested code | e7382ddb9cc5e0a5cd867653254a0c6f62f2f9c7 |
| Original performance measured revision | 9860a20342072168ed68a8d41eb16d9bfecf7729 |
| Current committed evidence/documentation tip | Resolve `git rev-parse codex/hw4-part2-backend` after the local evidence commit |
| Coordination file | /Users/pragyaapurva/Documents/SJSU/DATA 260/HW4_coordination/part2.md |

Both sibling branches share B as an ancestor. The partial verifier confirms all three imports and unchanged historical reports/unrelated code. The main checkout's unrelated `.gitignore` modification was not imported. Later report-only commits do not change the revision actually measured or tested.

## Integrated application

The existing FastAPI service uses MySQL database `s6102_rel` and the exact exported engine variable `db_session_basede26`. Shared models are `Rental`, `User`, `SessionToken`, and `PropertyManager`. Migration 001 defines the base schema; Part 3 adds title-index migration 003. Setup and seeding are explicit, never automatic on app startup.

Email/password login verifies Argon2 hashes and sets an opaque HTTP-only secure cookie. MySQL stores login sessions and enforces logout revocation, a 300-second idle timeout, and a 3,600-second absolute lifetime. The ordinary CRUD and performance routes use the same authentication. Create has six fields; update changes only title/address. The optional ordinary search retains HW3 Unicode casefold matching.

React production assets are served by the shared HTTPS launcher on port 8702. Explicit entry routes `/`, `/login`, `/create`, `/update`, and `/delete` work on fresh visits. Unknown API paths remain JSON 404; `/docs` remains available. The real build and both emitted assets passed the combined smoke.

[FOUNDATION.md](FOUNDATION.md) remains the early committed interface record. Use `web_application` imports with `code/` on Python's path. The live performance router is registered before dynamic rental-ID routes and uses the shared dependencies.

## Initial integration checks and evidence

| Check | Actual outcome / path under reports/hw04 |
| --- | --- |
| Production React build | Passed; `raw/part2/integrated-build.txt` |
| Integrated API/auth/CRUD | 23/23 passed; `raw/part2/integrated-api.json` |
| Integrated Python suite | 191 passed, 111 warnings, no skips, 5.42 s; `raw/part2/pytest-integrated.txt` and metadata JSON |
| Integrated real browser | 12/12 passed; `raw/part2/integrated-browser/real-browser.json` |
| Controlled real idle expiry | 2/2 passed; `raw/part2/integrated-browser/expiry-browser.json` |
| Runtime/MySQL/restarts | 6/6 passed; `raw/part2/integrated-browser/runtime.json` |
| Combined serving/auth/performance smoke | 29/29 passed; `raw/part2/integration-smoke.json` |
| Initial partial evidence verifier | 34/46 checks pass; 12 missing manual captures; `raw/part2/cleanup-followup/verification-before.json` |
| Original N+1 experiment | All 180 requests validated; `raw/part3/selected_run.json` names raw data and hashes |
| Separate title-index experiment | Equal data/results, observed EXPLAIN change; `raw/part3/index/20260928T004453-df40d32d/comparison.json` |
| Project-folder evidence | Actual Finder root/backend images; `screenshots/part2/07-project-structure.png` and `07-project-backend.png` |

Initial integrated API began at `2026-09-28T00:55:59.072951+00:00`; pytest began at `2026-09-28T00:56:08.104131+00:00`; the browser runtime ran from `2026-09-28T00:56:20.413881+00:00` to `2026-09-28T00:56:31.124030+00:00`; combined smoke ran from `2026-09-28T00:56:42.886910+00:00` to `2026-09-28T00:56:45.959111+00:00`. The initial partial verifier timestamp is `2026-09-28T00:58:08.565999+00:00`. Raw JSON retains exact check details and source hashes.

The original foundation gate and earlier 122/130-test runs remain separately labeled. Their failed attempts are retained rather than overwritten. The integrated acceptance and pytest records show a dirty tree because evidence was being assembled; metadata confirms tested source was unchanged. These are local integrated checks, not a clean tagged whole-homework run.

The integrated performance smoke used the exact 5,000/200 dataset and confirmed equal ordered results for naive/fixed pages of 10, 50, and 200. Total SQL was 13/53/203 naive and three fixed, including two auth/activity statements. Source comparison matches every recorded measured application path except ordinary `routers/rentals.py`, whose optional `q` search does not execute in the performance endpoints. No full benchmark rerun was needed. The published p50/p95/p99 values remain the original Python 3.13.5 unindexed benchmark results; the later functional smoke does not claim new latency measurements.

## Current cleanup follow-up

Part 1 cleanup commit `5d84f1a038cfdfcedb667b8047e06d5ef095164b` was merged at `6957de05690566887cab38a8d4c03537f665417a`. Current tested code is `307b1d9adc050e422a205e2d3219914c2234d816`. The change affects the browser test runner and verification provenance; frontend/backend application code and the measured performance path are unchanged, so the original benchmark remains selected.

| Follow-up check | Actual outcome | Evidence |
| --- | --- | --- |
| Normal HTTPS browser/runtime at merge `6957de0` | 12 browser, two expiry, and six runtime checks passed; cleanup `already_absent` for ID 14 | [browser](../raw/part2/cleanup-followup/browser/real-browser.json), [expiry](../raw/part2/cleanup-followup/browser/expiry-browser.json), [runtime](../raw/part2/cleanup-followup/browser/runtime.json) |
| Deliberate interruption at current code | 8/8 passed; exact confirmed-created ID 15 deleted and every pre-existing rental unchanged | [interruption check](../raw/part2/cleanup-followup/interruption/check.json) |
| Current selected Python suite | 209 passed, 111 warnings, no skips, 5.95 s | [pytest](../raw/part2/cleanup-followup/pytest-integrated.txt), [metadata](../raw/part2/cleanup-followup/pytest-integrated.metadata.json) |
| Current combined smoke | 29/29 passed | [smoke](../raw/part2/cleanup-followup/integration-smoke.json) |

The normal runtime ran at `2026-09-28T01:14:34.935389+00:00` through `01:14:46.483869+00:00`. The interruption check ran at `01:15:32.713257+00:00` through `01:15:35.397312+00:00` on isolated development port 8712; it deliberately produced runtime status `interrupted` and exit 143, then verified row cleanup, process shutdown, and port release. That interrupted browser trace is not a failed normal acceptance run.

The current pytest run began at `2026-09-28T01:15:32.510124+00:00`; the 29-check smoke ran at `01:15:50.150794+00:00` through `01:15:53.159300+00:00`. Seventeen new cleanup-guard unit tests use SQLite. Required MySQL evidence remains the live interruption check and integrated MySQL checks; SQLite is not substituted for that proof. The additional provenance regression and metadata cover the CJS browser runner, Python runtime runner, and interruption driver.

At `2026-09-28T01:16:15.241788+00:00`, [current partial verification](../verification.parts123.json) again reported 34/46 checks passing, automated status **pass**, and overall **incomplete** solely for the same 12 manual captures. [The previous verifier](../raw/part2/cleanup-followup/verification-before.json), initial integration timings, and original screenshot paths are preserved.

## Runtime ownership

Evidence-slot order was foundation/auth, Part 1 browser, Part 3 benchmark, then final combined integration. All owned API processes have been stopped, and the integration owner observed port 8702 free after the checks. Do not act on historical PIDs; consult the external coordination note and verify current ownership before starting or stopping anything.

| Instance | Host port | Purpose and retained state |
| --- | ---: | --- |
| `data260-hw4-mysql` | 3362 | API/browser evidence, shared with Part 1; retained without reset |
| `data260-hw4-part2-tests` | 3363 | Separate ordinary MySQL fixtures |
| `hw4-part3-mysql-6102` | 33363 | 5,000 rentals/200 managers; Part 3 and integrated performance checks; title index now present |

All use database `s6102_rel` and MySQL 8.4.11. Dedicated volumes remain for inspection. The read-only [preservation check](../raw/part2/integrated-database-preserved.json) at `2026-09-28T01:00:51.453365+00:00` passed: performance data/indexes/query results match the post-index snapshot, and ports 3362/3363 each retain two rentals. Private account/database configuration stays outside tracked files. The Part 3 database now contains migrations 001 and 003; reproducing the original unindexed benchmark requires a fresh owned instance with only 001, not dropping an index or reseeding shared data.

## Reproduce safely

Use the project Python environment and a privately configured, migrated MySQL instance. [The root README](../../../README.md) gives setup and local commands. Build and serve the same-origin app:

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/run_hw04_web.py --env-file /path/to/private/app.env
```

The managed checks below require exclusive port 8702 and must be run one at a time after stopping only an owned manual launcher. They never authorize taking another task's slot:

```sh
python scripts/hw04/part2/acceptance.py --env-file /path/to/private/app.env --manage-server --output /private/tmp/hw4-review/api.json
python tests/browser_hw04_part1_runtime.py --env-file /path/to/private/app.env --node node --raw-dir /private/tmp/hw4-review/browser --screenshots-dir /private/tmp/hw4-review/screenshots
```

These commands use a separate review output directory so the selected evidence remains available. The exact selected pytest command is in `raw/part2/pytest-integrated.metadata.json`. Part 3 setup, benchmark, and ownership-manifest commands remain in its committed [tooling README](../../../scripts/hw04/part3/README.md). Do not print private environment values, reset shared data, or run writes/heavy workloads during timing measurements.

## Remaining captures and later submission work

The integration dependencies are complete. Remaining evidence is precisely **12 images**:

- Part 2: five Postman CRUD responses and one database-client view.
- Part 3: naive/fixed Postman responses at page sizes 10, 50, and 200, six images.

Project-folder and browser evidence are captured. Postman is unavailable in the inspected native apps. The computer-use tool denied the native Terminal capture, so the database screenshot remains pending despite actual schema/query JSON. Follow [Part 2 capture steps](MANUAL_CAPTURES.md), [Part 3 capture steps](../screenshots/part3/README.md), and [the per-item manifest](../manual-captures.json). Use the provided collections with local credentials and record actual output; do not substitute fabricated images.

The combined [PARTS123.md](../PARTS123.md), [METRICS.md](../METRICS.md), and [AI_USE.md](../AI_USE.md) summarize the available evidence. `verification.parts123.json` objectively marks all automated checks passed and missing manual items failed. It is not `verification.json` for the eventual submission tag.

Part 4, the final whole-homework PDF, student review of the final explanation/AI-use disclosure, collaborator access checks, the `hw4` tag, and tagged-commit verification remain later work. No push, PR, deployment, or tag mutation is part of this local handoff.
