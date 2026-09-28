# HW4 submission

The approved report is [report.pdf](report.pdf), with the identical upload copy
[Apurva_HW4.pdf](Apurva_HW4.pdf). It has 79 pages covering personal configuration,
Parts 1–4, the required analysis, and [AI assistant use](AI_USE.md).

## Submitted code and evidence

| Item | Location |
| --- | --- |
| React client, Parts 1–2 | [`frontend/`](../../frontend/) |
| Persistent authenticated FastAPI/MySQL backend | [`code/web_application/`](../../code/web_application/) |
| Part 3 seed, benchmark, summary and index tools | [`scripts/hw04/part3/`](../../scripts/hw04/part3/) |
| Part 4 entry point and implementation | [`code/rag.py`](../../code/rag.py), [`src/rag/`](../../src/rag/) |
| Five-document corpus | [`part4/CORPUS_MANIFEST.json`](part4/CORPUS_MANIFEST.json), including references to preserved HW3 source snapshots |
| Original measured 180 requests | [`raw/part3/attempts/20260928T003859.945761Z-cd277c20/requests.jsonl`](raw/part3/attempts/20260928T003859.945761Z-cd277c20/requests.jsonl) |
| Selected Part 4 run | [`raw/part4/scored-20260928-04/`](raw/part4/scored-20260928-04/) |
| Tables and real console records | [METRICS.md](METRICS.md), [RUN_LOG.txt](RUN_LOG.txt) |
| Original report screenshots and placement hashes | [`screenshots/user/`](screenshots/user/), [report-build.json](report-build.json) |

The 180 benchmark rows contain 30 requests for each combination of page size
10/50/200 and naive/fixed implementation. Their original timings and provenance
are preserved. Part 4 includes retrieval printouts, 18 main answers, four extra
sweep answers, six sweep comparisons, and evaluation tables. Earlier attempts
remain historical records; `scored-20260928-04` is the selected report run.

Every screenshot in the final PDF comes from the student-supplied originals in
`screenshots/user/`. Images are embedded whole and scaled proportionally. The
older `screenshots/part4/` images are browser views of saved experiment outputs;
they are retained as historical evidence and are **not sources for the final
PDF**. Earlier part handoffs describe their state when written and do not
override this guide's report selection.

## Verification and publication

Follow [REPRODUCIBLE_RUN_INSTRUCTIONS.md](REPRODUCIBLE_RUN_INSTRUCTIONS.md) for
setup and the two verification modes. `--prepare` checks saved evidence only;
`--tagged` starts the system and checks the exact `hw4` revision. A successful
tagged run writes repository-root `verification.json` with the tested commit
and objective per-check results. A historical receipt is not a fresh test.

The publication convention separates `hw4-code` (code and experiment evidence),
`hw4` (the final code/report package), and the following receipt commit on
`main`. The final smoke test runs at `hw4`; its generated receipt is committed
afterward without changing application source or either PDF. This avoids
claiming that a receipt contains the hash of its own containing commit. Tag
targets, the receipt, and the publication log establish what actually completed;
these instructions alone do not claim a push, smoke-test pass, or current
collaborator access.
