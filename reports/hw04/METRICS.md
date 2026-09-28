# HW4 Parts 1–3 metrics and verification

These results keep the original Part 3 timing experiment separate from the later integrated functional checks. The combined local application passed its automated checks; required manual captures remain incomplete.

## Part 3 measured latency and SQL counts

Selected run: `20260928T003859.945761Z-cd277c20`. Measured revision: `9860a20342072168ed68a8d41eb16d9bfecf7729`, clean working tree. The run started at `2026-09-28T00:38:59.945643Z` and finished at `2026-09-28T00:39:05.948186Z`.

The dataset has 5,000 rentals and 200 managers, generated with seed 6102. Measurements used HTTPS port 8702, one Uvicorn worker without reload, Python 3.13.5, MySQL 8.4.11, and Apple M4 hardware with 10 cores and 24 GiB memory. The title index was absent. Three warmups per size/version were excluded, leaving exactly 180 measured requests: 30 for each of six groups. Requests ran serially, naive then fixed. Caches were warm; unrelated pre-existing services were left untouched.

Percentiles use R7 linear interpolation: rank = (n − 1) × p, then interpolate between adjacent sorted values. Latency is end-to-end HTTP time in milliseconds. Total SQL includes the shared session/user lookup and activity update; transaction protocol and connection initialization are outside the SQL statement-event count but inside latency.

| Page size | Version | Requests | Total SQL/request | Data SQL/request | p50 ms | p95 ms | p99 ms |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | naive | 30 | 13 | 11 | 11.514 | 21.160 | 23.194 |
| 10 | fixed | 30 | 3 | 1 | 7.557 | 12.575 | 85.671 |
| 50 | naive | 30 | 53 | 51 | 26.380 | 42.758 | 53.385 |
| 50 | fixed | 30 | 3 | 1 | 8.630 | 12.088 | 15.529 |
| 200 | naive | 30 | 203 | 201 | 74.496 | 175.151 | 205.407 |
| 200 | fixed | 30 | 3 | 1 | 14.202 | 25.722 | 29.632 |

Every request within a group had the displayed SQL counts. The naive route performs N+1 data statements and two auth/activity statements. The fixed route performs one data statement and the same two auth/activity statements.

| Page size | p50 speed-up | p95 speed-up | p99 speed-up |
| ---: | ---: | ---: | ---: |
| 10 | 1.524× | 1.683× | 0.271× |
| 50 | 3.057× | 3.537× | 3.438× |
| 200 | 5.245× | 6.809× | 6.932× |

Each ratio is naive percentile divided by fixed percentile. Values above one favor the fixed route. The fixed size-10 iteration 22 took 115.455 ms, making its p99 slower; the sample is retained and no cause is inferred. With only 30 samples per group, tail percentiles depend heavily on a few observations. These results do not establish latency outside the recorded environment.

Sources: [original Part 3 metrics](part3/METRICS.md), [machine-readable metrics](part3/metrics.json), [selected-run manifest](raw/part3/selected_run.json), [all 180 JSONL requests](raw/part3/attempts/20260928T003859.945761Z-cd277c20/requests.jsonl), [equivalent CSV export](raw/part3/attempts/20260928T003859.945761Z-cd277c20/requests.csv), and [independent recomputation](raw/part3/summary_recomputed.json). The CSV is another representation of the same run, not an additional experiment.

## Separate listing-title index experiment

Query: `SELECT id,listing_title FROM rentals WHERE listing_title=:title ORDER BY id`.

| EXPLAIN field | Before index | After index |
| --- | --- | --- |
| Access type | index | ref |
| Selected key | PRIMARY | ix_rentals_listing_title |
| Estimated rows | 4,868 | 1 |
| Extra | Using where | Using index |

The dataset and result hashes remained equal. The new title index lets MySQL use a selective equality lookup rather than scan the primary index and filter. Estimated rows are optimizer estimates; this experiment does not measure a latency speed-up. Execution revision: `62117550e2e2a253ea754152d2bb1007cc6b1f9a`. The successful evidence directory is [index/20260928T004453-df40d32d](raw/part3/index/20260928T004453-df40d32d/comparison.json). This DDL occurred after the 180-request run; reproducing the original unindexed experiment requires a fresh owned instance rather than removing the index from shared data.

## Initial integrated functional results

Initial tested integrated code: `e7382ddb9cc5e0a5cd867653254a0c6f62f2f9c7` on `codex/hw4-part2-backend`.

| Check | Actual result | Evidence |
| --- | --- | --- |
| React production build | Passed; 34 modules transformed | [build output](raw/part2/integrated-build.txt) |
| API/auth/CRUD and process restart | 23/23 passed | [API JSON](raw/part2/integrated-api.json) |
| Selected real-MySQL Python suite | 191 passed, 111 warnings, no skips, 5.42 s | [pytest output](raw/part2/pytest-integrated.txt) |
| Real browser | 12/12 passed | [browser JSON](raw/part2/integrated-browser/real-browser.json) |
| Controlled idle expiry | 2/2 passed | [expiry JSON](raw/part2/integrated-browser/expiry-browser.json) |
| Runtime/database/restart | 6/6 passed | [runtime JSON](raw/part2/integrated-browser/runtime.json) |
| Combined deep-link/auth/performance smoke | 29/29 passed | [smoke JSON](raw/part2/integration-smoke.json) |
| Partial evidence verifier | 34/46 pass; 12 missing manual captures; automated status pass, overall incomplete | [initial partial verification](raw/part2/cleanup-followup/verification-before.json) |

The integrated smoke observed 13/53/203 total SQL statements for naive pages of 10/50/200, and three for every fixed page, with equal ordered payloads at each size. The recorded measured execution source hashes match the integrated tree. Only ordinary CRUD `q` search changed in the application hash set; it is outside the measured routes. The original timing results are therefore retained without claiming a new integrated latency measurement.

Historical checkpoints remain distinct: the foundation gate passed 23 checks before B was committed; the first expanded web suite passed 122 tests; the reviewed backend suite passed 130; Part 1's branch passed 19 mock/12 real/two expiry/six runtime checks; and Part 3's final focused suite passed 52 tests. They support development history and are not added together as independent integrated test counts.

## Current cleanup follow-up

Current tested code is `307b1d9adc050e422a205e2d3219914c2234d816`, after Part 1 cleanup commit `5d84f1a038cfdfcedb667b8047e06d5ef095164b` was merged at `6957de05690566887cab38a8d4c03537f665417a`. The earlier 191-test integration and all benchmark values above remain their original observations.

| Follow-up check | Actual result | Evidence |
| --- | --- | --- |
| Normal browser / expiry / runtime | 12 / 2 / 6 passed at `6957de0`; normal cleanup `already_absent`, ID 14 | [runtime](raw/part2/cleanup-followup/browser/runtime.json) |
| Live MySQL interruption cleanup | 8/8 passed; exact ID 15 deleted; prior rows unchanged; owned processes stopped and port 8712 released | [check](raw/part2/cleanup-followup/interruption/check.json) |
| Selected Python suite | 209 passed, 111 warnings, no skips, 5.95 s | [output](raw/part2/cleanup-followup/pytest-integrated.txt) |
| Combined smoke | 29/29 passed | [smoke](raw/part2/cleanup-followup/integration-smoke.json) |
| Current partial verifier | 34/46 pass; automated pass; incomplete solely for 12 manual images | [verification](verification.parts123.json) |

The normal runtime began at `2026-09-28T01:14:34.935389+00:00`; the current pytest began at `01:15:32.510124+00:00`; smoke began at `01:15:50.150794+00:00`; partial verification ran at `01:16:15.241788+00:00`. Seventeen cleanup-guard unit tests use SQLite, while the live interruption and integration checks provide the real-MySQL proof. An added provenance regression records the browser runner, runtime runner, and interruption driver. This runner-only follow-up changes neither frontend/backend application behavior nor the measured performance path, so the original 180 timings are retained.

The remaining manual evidence is five Part 2 Postman screenshots, six Part 3 Postman screenshots, and one database screenshot. Project-folder and browser screenshots are captured. Part 4 and final tagged whole-homework verification remain outside these metrics.
