# Part 1 integration handoff

- Task: `01a0e565-6736-7761-b4b0-ab24bc4f88d1`.
- Worktree: `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part1-react`.
- Branch: `codex/hw4-part1-react`.
- Verified baseline: `5742b2aadbafee5ba208311723ea470c09811dc5` (`hw3^{commit}`).
- Frontend checkpoint: `03dd6a3`.
- Imported foundation B: `f29e7cc85baf52bea30bd4bb3209d1bd79b22051` (merged, not cherry-picked).
- Foundation merge: `47299ad67ed6e956f7da171bf2396ec2f961688f`.
- Reviewed code checkpoint: `0c4906d` (all six retained findings fixed).
- Final commit: resolve `git rev-parse codex/hw4-part1-react`; the external `HW4_coordination/part1.md` records the full final hash after commit.

## Owned files

`frontend/` contains the React application, its own npm manifest and lockfile, Vite build configuration, five required page components, shared form helpers, and the credentialed API/authentication modules. `tests/browser_hw04_part1.cjs` owns the browser checks; `tests/browser_hw04_part1_runtime.py` makes the real port 8702 run repeatable. Part 1 owns only its report fragments, raw outputs, and screenshots. Backend files entered through foundation B. Root npm dependencies and historical homework reports were not edited.

## Build and test

Use Node 22.12 or newer and Python 3.12 with the foundation's `requirements.txt`. The local verified run used Node 24.19.0, React 18.3.1, React Router 6.30.6, Vite 7.3.6, Playwright 1.62.1, and MySQL 8.4.11. Run from the worktree root unless noted.

```sh
npm --prefix frontend ci
npm --prefix frontend run build
npm install   # root Playwright dependency, if not already available
npx playwright install chromium  # if Chromium is not already installed
```

A root install is setup only; do not commit a generated root lockfile as Part 1 work. `frontend/dist` and dependency directories are ignored build outputs. Part 2's FastAPI service serves `frontend/dist`; do not deploy a separate frontend service.

For isolated frontend failure tests, run `npm --prefix frontend run dev -- --port 5173` in one terminal and then:

```sh
HW4_BASE_URL=http://127.0.0.1:5173 node tests/browser_hw04_part1.cjs --mock
```

The mock runner intercepts only `/api/` and visibly labels its screenshots. It is never imported into the application.

After the port 8702 owner releases the slot, use an existing migrated MySQL database and private seed-account configuration:

```sh
python tests/browser_hw04_part1_runtime.py --env-file /path/to/private/app.env --node node
```

For combined integration, preserve the original Part 1 evidence with separate destinations:

```sh
python tests/browser_hw04_part1_runtime.py --env-file /path/to/private/app.env --node node \
  --raw-dir reports/hw04/raw/part2/integrated-browser \
  --screenshots-dir reports/hw04/screenshots/part2/integrated-browser
```

Direct CJS runs support the equivalent `HW4_RAW_DIR` and `HW4_SCREENSHOTS_DIR` environment variables.

The environment file must contain `HW4_DATABASE_URL`, `HW4_SEED_EMAIL`, and `HW4_SEED_PASSWORD`. It is read through dotenv; never print or commit it. The runner requires a built frontend, refuses an occupied port, starts only its own server, runs real browser CRUD, restarts for persistence, checks deletion after a second restart, then runs a separate two-second idle-expiry demonstration. Production remains 300-second idle / 3600-second absolute. It does not migrate or seed the database. The browser creates only uniquely named test records; successful runs delete them. A failed run's cleanup outcome must be inspected before removing any leftover row.

For an already-running service, load private seed credentials into the process environment and use:

```sh
HW4_BASE_URL=https://127.0.0.1:8702 node tests/browser_hw04_part1.cjs --real
```

That direct form does not prove restart persistence unless both `HW4_RESTART_READY_FILE` and `HW4_RESTART_DONE_FILE` are supplied and an owner performs the restart. Prefer the Python wrapper for the complete Part 1 check. Browsers use `ignoreHTTPSErrors: true` for the local self-signed certificate; no OS trust settings were changed.

## Evidence and runtime ownership

Selected evidence is `reports/hw04/raw/part1/mock-browser.json` (19 checks), `real-browser.json` (12 checks), `expiry-browser.json` (2 checks), and `runtime.json` (6 orchestration/database checks). Their timestamps, source hashes, revision, URL, viewport sizes, and check details are recorded. The final selected checks run code commit `0c4906d`; earlier successful and failed attempts are labeled separately. Failed attempts remain separately labeled. `REPORT_SECTION.md` pairs source excerpts with screenshots for each Part 1 question.

MySQL acceptance used existing container `data260-hw4-mysql` on `127.0.0.1:3362`, database `s6102_rel`. No database reset occurred. Port 8702 was released to Part 3 after the checks; all Part 1 API processes were stopped. Final ownership and any subsequent verification window are recorded in the external Part 1 coordination file. Never stop another task's server.

## Remaining integration and limitations

Part 2 incorporated the original Part 1 handoff into its integrated tip `2d03ae4074a8d6d69a9e84dacf1ce3fea7d2bafb`. A subsequent, narrowly scoped browser interruption cleanup fix is documented in [CLEANUP_FOLLOWUP.md](CLEANUP_FOLLOWUP.md), with separate reproduction and success evidence. Part 2 must incorporate that follow-up and refresh runner-dependent integration evidence. The follow-up commit hash is in `HW4_coordination/part1.md`. Part 1 has real screenshots; no Part 1 manual screen capture remains. Part 2/3 Postman screenshots, Part 4, the combined final PDF, collaborator verification, final tagged-commit verification, and the `hw4` tag are outside this task.

`npm audit` reported two moderate Router 6-related entries. The fixes advertised by npm require Router 7, while the shared teaching contract selects Router 6. This client uses fixed local destinations and positive numeric IDs and does not use server-side rendering/hydration, the features described by those advisories. The audit is not claimed clean; a later Router 7 migration should be coordinated rather than silently changing the shared contract.

There is no configured frontend lint or typecheck command; neither is claimed as passed. Frontend production build, dedicated browser checks, Node syntax checking, Python compilation, and `git diff --check` are the relevant checks. Historical HW2/HW3 DOM/auth tests target intentionally superseded behavior and were not used as Part 1 acceptance.
