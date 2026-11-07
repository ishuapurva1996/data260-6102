# HW9 Part 3 evidence

Pragya Apurva | DATA 260 | November 6, 2026

The five real authenticated sweeps contain 200 successful requests. The selected cutoff is **0.85**, with 75% hits, 32.5% false hits, 3,832.83 ms mean HTTP latency, and 3,950 seconds-equivalent cost. This is the minimum cost among the five tested settings; the remaining wrong answers show why listing identity also needs protection before production use.

- [ANALYSIS.md](ANALYSIS.md): completed threshold table, cost assumptions, recommendation, full false hit, version trade-off, and AI use.
- [audited-requests.jsonl](audited-requests.jsonl) and [audited-threshold-summary.json](audited-threshold-summary.json): final answer decisions and metrics.
- [scored-requests.jsonl](scored-requests.jsonl), `requests-*.jsonl`, and [threshold-summary.json](threshold-summary.json): unchanged original automatic scores and HTTP records.
- [answer-audit.json](answer-audit.json): all 200 output reviews against the frozen facts and rubrics. Two keyword-screen errors were corrected; no query labels or expected facts changed.
- [seed.json](seed.json), [seed-review.json](seed-review.json), [snapshot-operations.jsonl](snapshot-operations.jsonl), and [restored-seed-verification.json](restored-seed-verification.json): ten checked live answers, five restores, and 50 byte-identical seed-entry checks.
- [false-hit-trace.json](false-hit-trace.json): incoming S6102-R-9106 query incorrectly served the S6102-R-9102 answer at cosine similarity 0.999333382.
- [stale-mutation.json](stale-mutation.json), [stale-trace.json](stale-trace.json), [demonstration-audit.json](demonstration-audit.json), and [chosen-smoke.jsonl](chosen-smoke.jsonl): authorized SQL change from 3 to 1, stale hit at 3, enforced miss/hit at 1, full-answer audits, and the separate selected-cutoff smoke check.
- `api-*.log` and `{seed,sweep,stale}-{planner,writer,reviewer}.log`: original correlated service logs. Sweep hits made zero generative calls; 40 misses made 120 calls.
- [run-metadata.json](run-metadata.json), [lease-windows.jsonl](lease-windows.jsonl), and [verification.json](verification.json): hardware, model digests, fixed configuration, exclusive Ollama windows, and experiment checks.
- The three `*-screenshot.png` files are labeled browser captures of evidence views rendered from the saved records. Pragya Apurva is visible in each; the captures are explicitly identified as evidence views.

The frozen case file is [cache_cases.yaml](../../cache_cases.yaml), committed at `3511ae67588f61eeff4199aa8f4db294aca04c57` before any sweep. Its SHA-256 is `4c180dd5a8b5dbd007797225889d1cb7e0921339d0670683b225674ee76f0c26`. The fixture facts are [rental_fixtures.json](../../rental_fixtures.json). Session B commit `6938c71110845b7b73c53b795b709399f8a523a1` was merged with history. Seed services used the frozen-case commit; measured sweep and stale services used runner commit `52c8ef470b124605a0fc51dd8c5821b4a5f3738b`.

For a fresh run, follow `docs/HW9_CACHE.md` to initialize an isolated MySQL `s6102_rel` database, Kafka broker, Redis Search service, private moderator account, Python 3.12 environment, and the pinned local Ollama models. This run used MySQL 3398, Kafka 19098, Redis 6398, and API 18708. Set `HW4_DATABASE_URL`, the private `HW7_*` account/JWT variables, `KAFKA_BOOTSTRAP_SERVERS`, `HW9_REDIS_URL`, `OLLAMA_BASE_URL`, `HW8_KAFKA_ENABLED=1`, `HW9_CACHE_ENABLED=1`, and `PYTHONPATH=.:code`. The runner starts and stops its own API and agent processes.

Run `python -m scripts.hw09.cache_experiments seed --runtime <external-directory>` on an empty owned database and fresh Redis. Review all ten returned seed answers and save `seed-reviewed.json`. Run the `sweep` phase, then the `stale` phase with the same external directory and environment. Review full answers against the frozen rubrics and save the per-request audit decisions. Run `python -m scripts.hw09.analyze_cache_experiments --runtime <external-directory>` to verify and package the records. Keep the shared Ollama lease at the `ollama-shared` sibling of that external runtime directory. Namespaces and log paths are deliberately single-use; a complete rerun starts with new isolated service state.

The experiment verification covers the recorded workload. The repository-wide pytest attempt failed at collection because this focused environment lacks `jsonschema`, `langgraph`, `llama_index`, `mcp`, and `numpy` for older homework modules. Targeted HW8/Part 3 tests and lint are recorded separately in the checks files.

Post-measurement review fixes retain HTTP transport/non-JSON failures and strengthen offline evidence verification. The measured endpoint, Redis search, models, and HW8 agent code did not change. [checks.json](checks.json) records 49 passing targeted tests, lint, review resolution, and the full-suite collection limitation. [evidence-sha256.json](evidence-sha256.json) covers all final evidence files except itself.
