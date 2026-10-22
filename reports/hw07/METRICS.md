# Homework 7 measured results — Part 1 checkpoint

Pragya Apurva · SID4 6102 · application `c0c8e8671657cf94a03ecaadcdfe0124c5be11f9`

Only baseline setup and Part 1 have been executed. No results for Parts 2–6 are
claimed. This is not the final homework metrics sheet.

| Live Part 1 HTTP outcome | Observed / expected |
| --- | --- |
| 200 OK | 36 / 36 |
| 201 Created | 5 / 5 |
| 204 No Content | 5 / 5 |
| 401 Unauthorized | 12 / 12 |
| 403 Forbidden | 21 / 21 |
| Total matching checks | **79 / 79** |
| Chromium behavior checks | **10 / 10** |
| Preserved HW6 smoke checks | **15 / 15** |
| Supplemental renewal/Vite checks | **8 / 8** |

These are acceptance-check counts, not latency benchmarks or statistically
sampled reliability estimates. Source data: [acceptance](raw/part1/acceptance.json),
[HW6 regression](raw/part1/hw6-smoke.json), [supplement](raw/part1/supplemental-live.json).

| Automated check | Passed | Skipped |
| --- | --- | --- |
| Web-compatible regression suite | 971 | 25 |
| Isolated MySQL migration recovery | 8 | 0 |
| Separate MCP regression environment | 156 | 0 |

The web skip count includes eight isolated-migration opt-ins that passed in their
separate run, plus 17 existing opt-ins. Tests include real transactional MySQL and
explicit unit doubles; they are separate from live HTTP/model evidence. Ruff and
pre-commit passed after a genuine rejected commit and correction. See
[RUN_LOG.txt](RUN_LOG.txt) for exact commands, boundaries and earlier failed runs.

| Later homework result | Status |
| --- | --- |
| Part 2 original-loop call/chain rates | Not run |
| Part 3 Reflexion comparison | Not run |
| Part 4 scenario cost comparison | Not run |
| Part 5 attack/defense matrix | Not run |
| Part 6 safety/integration matrix | Not run |
