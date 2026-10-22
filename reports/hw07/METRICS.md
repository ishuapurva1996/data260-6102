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


---

## Parts 2 and 3 — completed checkpoint

The preceding Part 1 tables are the preserved historical checkpoint. The later-part status rows above describe that earlier checkpoint. Parts 2/3 results below supersede only those status entries. Parts 4–6 remain pending.

Tested application: `996c476ac4d52d13f9712913df488b9c8b966158`. Fixed seven repetitions each of A/B/C in each mode; real local Ollama/MySQL, with mocked tests excluded.

| Original-loop measure | Result |
| --- | --- |
| Complete tasks | 21/21 |
| First-pass valid proposals | 70 / 70 (100.0%) |
| Valid after the single repair opportunity | 70 / 70 (100.0%) |
| Tool-operation repairs | 0 |

| Failure category (overlapping case counts) | Original / 21 | Reflexion / 21 |
| --- | --- | --- |
| malformed arguments | 0 | 0 |
| unknown tool | 0 | 0 |
| text when a tool was required | 0 | 0 |
| lost multi-step chain | 0 | 0 |

| Metric | Original loop | Reflexion loop |
| --- | --- | --- |
| Task success | 21/21 | 21/21 |
| Unsupported final claims, independently audited | 0 | 0 |
| Cases entering a Reflexion retry | 0/21 (0.0%) | 0/21 (0.0%) |
| Actual tool calls, total | 70 | 70 |
| Actual tool calls, mean | 3.3 | 3.3 |
| Reported input tokens, total | 48076 | 48076 |
| Reported output tokens, total | 4186 | 4186 |
| Model tokens, total | 52262 | 52262 |
| Model tokens, mean | 2,488.7 | 2,488.7 |
| End-to-end latency, mean ms | 20,888.5 | 20,990.7 |
| Verifier false rejections, cases | 0 | 0 |

All denominators, scoring rules and budgets were frozen before scoring. Required raw data: [reliability](raw/part2/reliability.csv), [comparison](raw/part3/comparison.csv), [metrics](raw/parts2-3/metrics.json), [independent audit](raw/parts2-3/audit.json). See [Parts 2/3 checkpoint](PARTS2_3.md) for provenance, cost definitions, controlled-fault distinction and limitations.
