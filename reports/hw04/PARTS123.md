# HW4 Parts 1–3: local integration record

This is a partial homework write-up. Part 2 backend implementation and foundation
verification are complete; final combined integration awaits the completed
Part 1 and Part 3 commits. This file will record the final merged checks without
relabeling independent branch evidence as integrated evidence.

## Part 1 — React interface

Part 1 owns the five required React pages, routing, mutation props and browser
evidence. Its final report and committed handoff are still pending integration.
The external task has reported real browser, restart and expiry checks; those
results are not yet imported here.

## Part 2 — Persistent backend

Foundation B is `f29e7cc85baf52bea30bd4bb3209d1bd79b22051`. It provides the
MySQL schema, shared manager relation, email/password login, opaque server-side
sessions, authenticated CRUD, HTTPS launcher and React serving. The early
foundation gate passed 23 real HTTPS/MySQL checks; the separate expanded backend
suite passed 122 tests. See [Part 2 report](part2/REPORT_SECTION.md),
[raw API output](raw/part2/api-acceptance.json), and
[test output](raw/part2/pytest-backend.txt).

## Part 3 — Query performance

The completed measured run, 180 raw requests, query-count and percentile table,
EXPLAIN evidence, and final code revision are not yet imported. No performance
numbers are inferred here.

## Remaining verification and submission work

The integration owner must merge completed sibling branches, build React, run
the current API/browser/performance checks, compare the measured backend source
with the merged tree, and rerun the experiment if executed behavior changed.
Required Postman screenshots remain pending because Postman is unavailable.
Database and project-folder captures are tracked individually in
[manual-captures.json](manual-captures.json).

Part 4, the final whole-homework PDF, collaborator checks, the `hw4` tag and
verification against that tag remain later work. `verification.parts123.json`
can only describe this partial scope.
