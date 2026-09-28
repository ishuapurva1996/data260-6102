# HW4 execution prompts for three fresh Codex sessions

Created: 2026-09-27.

Open three separate tasks against the existing `data260-6102` repository. Paste one complete prompt below into each. Starting Part 2 first gives the backend foundation a head start, but all three can start immediately. These prompts ask the sessions to create separate worktrees; do not point three editors at the same working directory for writes.

Plans and shared contract are currently local uncommitted documents in the main checkout. A new worktree based on `hw3` will not automatically contain them. Each prompt therefore gives their absolute source paths. Read them there; Part 2 can copy this planning bundle into the final integration branch once, preserving the file names. Do not import the main checkout's unrelated changes.

The supplied coordination folder is a shared handoff location outside the Git worktrees. Each task writes only its assigned handoff file. Part 2 is also the integration owner for Parts 1–3. If it finishes its independent work before the other sessions, it should report the pending commits and resume integration when they arrive. No fourth implementation task is required.

## Session 1 prompt: React client

```text
Implement HW4 Part 1 for my existing Rental Housing Listings application. This is an execution request: build, verify, capture available evidence, and commit your own work locally.

Repository: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102
Read this plan: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102/docs/plans/2026-09-27-1715-feat-hw4-part1-react-plan.md
Read this shared contract: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102/docs/plans/2026-09-27-1715-hw4-shared-contract.md
Assignment: /Users/pragyaapurva/Documents/SJSU/DATA 260/Homework4_export/DATA260_HW4.pdf
Teaching reference: /Users/pragyaapurva/Documents/SJSU/DATA 260/Homework4_export/DATA236_demo4
Correct HW3 source for read-only reference: /Users/pragyaapurva/Documents/SJSU/DATA 260/HW3/worktrees/integration

The repository's main local checkout is on an older branch. Verify that hw3^{commit} is 5742b2aadbafee5ba208311723ea470c09811dc5. Create or safely reuse your own Git worktree on branch codex/hw4-part1-react from that baseline; do not reset the existing checkout or modify another task's worktree. If a branch/worktree already exists, inspect it and resume rather than overwriting it.

Follow the plan's requirements, units, verification and Definition of Done. Own frontend code, Part 1 browser checks and Part 1 evidence. Preserve the six-field create contract. You may begin with clearly labeled mocks, but the final result needs Part 2's real authenticated MySQL API. Read the published foundation commit from the Part 2 handoff and merge that commit into your branch when available. Do not implement a competing backend or authentication system.

Use /Users/pragyaapurva/Documents/SJSU/DATA 260/HW4_coordination/part1.md for your shared progress/handoff. Read sibling part2.md and part3.md for dependency and runtime ownership. Include your task ID if available, worktree, branch, commits, foundation hash, passed checks, evidence and remaining dependencies. Never put secrets in these files. Coordinate final port 8702 use; worktrees do not isolate ports or databases.

Keep working autonomously on all unblocked units. If a required sibling commit or UI tool is unavailable, finish independent work and identify the exact remaining step rather than claiming success. Use the local implementation workflow if available, but limit shipping to local commits: do not push, open a PR, deploy or tag hw4. Do not implement Part 4 or modify historical homework reports.

Return the branch and commit, files changed, tests actually run, evidence paths and any remaining integration/manual capture work. Write clear report prose, define necessary terms, and use actual outputs only.
```

## Session 2 prompt: MySQL backend and integration

```text
Implement HW4 Part 2 for my existing Rental Housing Listings application, and own the final local integration of Parts 1–3. Build, verify, capture available evidence, and commit your own work locally.

Repository: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102
Read this plan: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102/docs/plans/2026-09-27-1715-feat-hw4-part2-backend-plan.md
Read this shared contract: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102/docs/plans/2026-09-27-1715-hw4-shared-contract.md
Other part plans: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102/docs/plans/2026-09-27-1715-feat-hw4-part1-react-plan.md and /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102/docs/plans/2026-09-27-1715-feat-hw4-part3-performance-plan.md
Assignment: /Users/pragyaapurva/Documents/SJSU/DATA 260/Homework4_export/DATA260_HW4.pdf
Teaching reference: /Users/pragyaapurva/Documents/SJSU/DATA 260/Homework4_export/DATA236_demo4
Correct HW3 source for read-only reference: /Users/pragyaapurva/Documents/SJSU/DATA 260/HW3/worktrees/integration

The main local checkout is stale. Verify hw3^{commit} is 5742b2aadbafee5ba208311723ea470c09811dc5. Create or safely reuse your own worktree on codex/hw4-part2-backend from that baseline. Preserve existing changes, including the unrelated .gitignore modification; never reset another worktree.

Follow the plan's requirements, units, verification and Definition of Done. Own shared MySQL schema/models, connection setup, auth/session lifecycle, ordinary CRUD, backend wiring and root integration documentation. Keep database s6102_rel and the exact connection variable db_session_basede26. Publish the early foundation commit and FOUNDATION.md as soon as its real-MySQL smoke checks pass; Parts 1 and 3 need it and must not wait for your final evidence. Include the agreed manager table/relation, module imports, exported dependencies, HW4 HTTPS launcher and minimal React serving in that foundation; do not wait for the real frontend build to provide its serving plumbing.

Use /Users/pragyaapurva/Documents/SJSU/DATA 260/HW4_coordination/part2.md for shared progress/handoff. Read part1.md and part3.md there. Record task ID if available, worktree, branch, foundation commit, runtime ownership, checks and blockers without credentials. Coordinate exclusive port-8702 evidence slots for foundation/auth, then Part 1 browser flows on its branch, then Part 3 benchmarks on its branch, before the final combined merge. Coordinate the evidence database too. Do not stop unrelated servers or erase shared data.

After the other tasks publish completed commits, merge their branches into yours, resolve ordinary conflicts, serve the built React app, and run the integrated API/browser/performance checks. Preserve shared foundation ancestry. Combine the evidence into clearly labeled Parts 1–3 artifacts and partial verification. Re-run measurements if integration changes the measured behavior. Copy only this planning bundle into the integration branch if needed, never unrelated changes from the main checkout.

Continue all unblocked work while dependencies are being built. If other sessions are unfinished, publish the precise missing commits and integration steps; resume when their handoffs arrive. Use the implementation workflow if available, but keep shipping local: do not push, open a PR, deploy, change old tags or create hw4. Part 4, final whole-homework PDF, collaborator checks and tagged-commit verification remain later work. Do not claim the whole homework is finished.

Return the foundation hash, integrated branch/hash when ready, actual test outcomes, evidence paths and precise remaining dependencies/manual captures. Keep logs and report prose factual and readable; never invent outputs or screenshots.
```

## Session 3 prompt: N+1 measurement and tuning

```text
Implement HW4 Part 3 for my existing Rental Housing Listings application. Build the experiment, run it on real MySQL, preserve measured evidence, and commit your own work locally.

Repository: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102
Read this plan: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102/docs/plans/2026-09-27-1715-feat-hw4-part3-performance-plan.md
Read this shared contract: /Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102/docs/plans/2026-09-27-1715-hw4-shared-contract.md
Assignment: /Users/pragyaapurva/Documents/SJSU/DATA 260/Homework4_export/DATA260_HW4.pdf
Correct HW3 source for read-only reference: /Users/pragyaapurva/Documents/SJSU/DATA 260/HW3/worktrees/integration

Verify hw3^{commit} is 5742b2aadbafee5ba208311723ea470c09811dc5; the main local checkout is on an older branch. Create or safely reuse your own worktree on codex/hw4-part3-performance from that baseline. Preserve all unrelated work and do not edit sibling worktrees.

Follow the plan's requirements, units, verification and Definition of Done. Prepare the generator, benchmark/summarizer and tests while Part 2 builds the foundation. Merge its published foundation commit into your branch when available. Use its models, engine, sessions and auth dependency; do not create a competing backend or base migration. Own only the Part 3 modules/scripts/tests/evidence and the small agreed router-registration seam.

Use /Users/pragyaapurva/Documents/SJSU/DATA 260/HW4_coordination/part3.md for shared progress/handoff; read sibling handoffs there. Record task ID if available, worktree, branch, commits, imported foundation, runtime ownership and remaining dependencies without secrets. Coordinate the quiet final evidence run at port 8702. Use a dedicated MySQL instance with database s6102_rel and never reseed or drop a shared database.

Produce the exact required seeded dataset, real N+1/fixed queries, all 180 measured HTTP requests, query counts including auth, percentile/speed-up tables, index EXPLAIN before/after, and six real Postman endpoint/size screenshots if the UI is available. Validate equal payloads before measuring; guard against SQLAlchemy identity-map reuse hiding N+1. Preserve failed attempts separately and never fabricate speed-ups or SQL counts. If screenshots require manual access, complete everything else and provide exact capture steps with pending status.

Keep working on unblocked units; report an exact dependency if foundation/runtime access prevents completion. Use the implementation workflow if available, but limit shipping to local commits: no push, PR, deployment or hw4 tag. Do not implement Part 4 or alter historical reports.

Return your commit, actual measured revision/configuration, test outcomes, raw data/metrics/EXPLAIN/evidence paths and remaining integration steps so Session 2 can combine the work.
```
