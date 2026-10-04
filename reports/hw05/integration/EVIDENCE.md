# Parts 1–4 integration evidence

Pragya Apurva · U5/U6c · tested code `f95597f91be0b5f81c800a6a5f2d7c039eb37665`.

The four reviewed histories were merged in order without conflicts. The only new executable repository file is `tests/test_hw05_executor_integration.py`; no production repair was needed. The earlier web/build/migration checks ran at `d4fdd54585c546e02b7f4d51776dacd79d43f565`; production source is byte-identical at the tested code revision. The new test file was characterized (38 passes), committed, then included in the full MCP run.

| Gate | Actual selected result |
| --- | --- |
| Backend/auth/prior routes, real owned MySQL | 160 passed |
| Separate destructive migration/recovery fixture | 11 passed |
| MCP/Meals/reliability/timeout/executor/offline/integration suites | 373 passed |
| All selected pytest suites | 544 passed, 0 failed, 0 skipped |
| Frontend lockfile install and production build | Passed |
| Controlled Chromium HTTP/cookie/race checks | 19 passed |
| Real HTTPS/MySQL browser checks | 8 passed |
| Real HTTPS API checks | 25 passed |
| Actual default executor and rental STDIO | 20 cases each; 11 exact envelope comparisons; 8 single reads/disposals; 12 invalid zero-I/O calls |
| Tool/API comparisons and rendered UI/API baseline | 7 API cases plus rendered rental 1 passed |
| Actual Meals STDIO with public upstream | All 4 tools passed |
| Offline runner | Two identical 6/6 runs; truthful negative exits verified |

The application fixture started with HW4 migrations 001/003, twelve synthetic rentals, three managers (one empty), one hashed login user and one session. Migration 004 preserved original rows, IDs, relationships, auth data and indexes; rerun preserved complete rows/timestamps. The final fixture check preserved all baseline domain rows and authentication. The dedicated MCP account was denied contact-column reads and writes. The separate migration fixture began empty and exercised seven interrupted-upgrade checkpoints. Both schemas are named `s6102_rel` in independent MySQL instances.

[Verification](../raw/integration/verification.json) identifies commands, exits, UTC times, counts, versions, classifications, cleanup and the initial stderr-harness diagnostic. [Source hashes](../raw/integration/tested-source-sha256.json), [live parity](../raw/integration/combined-live.json), [history audit](../raw/integration/history-audit.json), and [artifact hashes](EVIDENCE_MANIFEST.json) bind the evidence. [RUN_LOG](RUN_LOG.txt) retains actual selected output.

Controlled retry exceptions, live MySQL reads, and the real stalled-greeting driver timeout are distinct evidence. The timeout used 0.2 seconds and observed about 234 milliseconds; it is not an end-to-end deadline. The SDK emits its expected safe warning for the deliberate unknown tool; no stdout parsing error or credential disclosure occurred. The initial harness rejected that warning, was corrected without changing application code, and the focused check passed.

All historical reports remain unchanged: 9,872 accepted-head entries over 2,533 distinct report files, 126 source hashes against recorded commits, and 87 artifact references were checked. The selected Part 3 150-row dataset, original rejected examples, Part 1 review-fix Redux frames and capture-guard follow-up are preserved. New results are not pooled into old measurements.

Only the owned HTTPS8702 and MySQL3311/3312 services were stopped; data and isolated environments remain available. Inherited dependency warnings and two moderate npm advisories remain recorded.

**Code/live ready for independent coordinator review.** This receipt is not coordinator acceptance. Part 5, final report/verifier/tags and publication were not performed. Screenshots deferred to the final evidence pass remain required: Part 1 Postman/database images, Part 3 terminal demonstrations/metrics, and Part 4's named offline-runner terminal image.
