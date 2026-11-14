# Recorded dashboard verification

Pragya Apurva captured the five figures in the report from the integrated
dashboard using the recorded HW10 evidence. The repository contains the
original PNG files. The combined verifier records their SHA-256 checksums,
checks the dashboard code against C1 and audits the raw evidence against its
source milestones.

- The default completion window was 2026-11-12 09:58:54.028 UTC through
  2026-11-13 09:58:54.028 UTC. It included 53 of 55 saved API completions
  from `raw/tracing/spans.jsonl` and `raw/benchmark/spans.jsonl`.
  One request was a hit, 52 were misses, and one of the misses failed.
  The hit rate and error rate were both 1.9% at dashboard precision.
  API p50 and p95 were 20,416.922 ms and 27,596.0454 ms. The one hit
  took 578.690 ms, which is both hit percentiles for that window.
- Evaluation showed Planner 5/5, Writer 4/5 and Reviewer 4/5. The
  Reviewer kept the draft verbatim. The 60 judge scores reproduced
  Spearman 0.5402805999 and mean absolute difference 0.75 points.
  All 20 cases had zero change.
- Browser and Streamlit AppTest both opened all three D1 IDs. The hit
  `bdf62b55-6040-4701-8eae-3c0e6db8bf53` showed two spans.
  The successful miss `813b4e22-6b35-4f5c-a163-5350c18652d6`
  showed ten. The Writer failure `05a689b3-b160-4fcb-a383-fb2c58aff1d3`
  showed eight, including three Writer failures and the API timeout.
  Displayed timestamps, durations, statuses, cache decisions, attempts
  and errors agreed with the source at displayed precision.
- Session C passed all eight dashboard tests plus Ruff lint and format.
  Its initial dashboard verification preceded the student captures.
- Integration repeated the three lookups in Chrome on the joined worktree
  with zero page errors. Streamlit AppTest checked the displayed rows against
  the raw trace rows. The integrated metrics and evidence checks are in
  [verification.json](verification.json).

## Figure files

1. [Summary](screenshots/01-summary.png)
2. [Evaluation](screenshots/02-evaluation.png)
3. [Cache hit](screenshots/03-trace-cache-hit.png)
4. [Successful cache miss](screenshots/04-trace-successful-miss.png)
5. [Writer failure](screenshots/05-trace-writer-failure.png)
