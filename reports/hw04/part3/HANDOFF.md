# Part 3 integration handoff

Task: `01a0e566-5473-70d3-8b2f-84992d64c4e7`.
Worktree: `/Users/pragyaapurva/Documents/SJSU/DATA 260/HW4/worktrees/part3-performance`.
Branch: `codex/hw4-part3-performance`.
Verified baseline: `hw3^{commit}` = `5742b2aadbafee5ba208311723ea470c09811dc5`.
Imported foundation B: `f29e7cc85baf52bea30bd4bb3209d1bd79b22051`, merged with shared ancestry.

## Commits and measured source

- `1d9bab6`: deterministic generator/ownership checks, benchmark/summarizer, request counter and preparation tests.
- `4cec543`: live naive/fixed routes, tiny main registration seam, MySQL tests, index migration 003/tooling.
- **HTTP measured revision: `9860a20342072168ed68a8d41eb16d9bfecf7729`, clean.** This includes configuration/report preparation; executed code is unchanged from `4cec543`.
- `6211755`: all 180 measured rows, derived metrics and independent recomputation evidence.
- `df4d1a0`: seed evidence reservation/transaction guard and its regression tests.
- The final follow-up changes only the seed CLI evidence guard/tests plus evidence/prose. The pure generator, application runtime, benchmark, summarizer and index experiment remain unchanged from the measured revision. Find the final evidence commit with `git log -1 --format=%H -- reports/hw04/part3/HANDOFF.md` after merging.

The current app uses Part 2's models, engine, session dependency, auth and ordinary serializer. The only shared-source change is registration of the performance router/middleware before dynamic rental-ID routes in `main.py`. Part 3 defines no competing backend or base migration. No Part 4 work, historical report changes, push, PR, deployment or hw4 tag was made.

## Runtime ownership

Dedicated Docker container: `hw4-part3-mysql-6102` (full ID `5d65145f0fa1ff2e2d9304470e0ba70734a4bd00e7cd9d2f644569520a9318ad`), volume `hw4-part3-mysql-6102-data`, host `127.0.0.1:33363`, database `s6102_rel`, MySQL **8.4.11**, server UUID `3d515eaf-bad3-11f1-8b89-0ecd67fb62d4`.

The dedicated database remains running for inspection. All Part 3 API processes are stopped: development 8733 PID63386 and final 8702 PID65284. Port 8702 was explicitly released to Part 2/Part 1 after the successful run. Never stop a later owner's process using these old PIDs; verify ownership first.

Private runtime settings are in this worktree's ignored `.env`; do not print or commit them. The external ownership manifest is `/private/tmp/hw4-part3-ownership.json` (contains identity, no secrets). The local TLS certificate/key are ignored under `tmp/https/`. New installations must provision their own private settings and a fresh ownership manifest for their instance.

Python **3.13.5**, SQLAlchemy **2.0.43**, FastAPI **0.109.0**, Uvicorn **0.27.0**, HTTPX **0.27.2**, PyMySQL **1.1.2**, Pydantic **2.12.5**, Starlette **0.35.1**. Hardware: Apple M4, 10 cores, 24GiB. Complete package/source hashes are in `raw/part3/benchmark_config.json`.

## Verified evidence

- `reports/hw04/raw/part3/seed_manifest.json`: actual 5,000 rentals/200 managers, 25 rentals per manager, live schema journal/checksums and generated/stored SHA256 `9513ac766ab94f7c23c9257536d8e0f623c8bcbf530f6881e3c354cc7ced1b78`.
- `reports/hw04/raw/part3/selected_run.json`: selected-run paths and hashes.
- `reports/hw04/raw/part3/attempts/20260928T003859.945761Z-cd277c20/requests.jsonl`: original180 recorded rows; `requests.csv` is an equivalent180-row export, not another experiment.
- Adjacent `manifest.json`, `preflight.jsonl`, `warmups.jsonl`: clean revision/config, six full-payload equality checks,18 warmups kept outside the 180 rows. Exactly 30 samples per size/version, serial naive then fixed, one worker/no reload, HTTPS 8702, title index absent.
- `reports/hw04/part3/METRICS.md` and `metrics.json`: six-group percentiles, SQL ranges/distributions and ratios. `raw/part3/summary_recomputed.json` independently checks 18 percentiles/nine ratios plus counts/hash.
- `reports/hw04/raw/part3/sql_execution_evidence.json`: actual SQL shapes and independent counts, with no parameter values. Total SQL 13/53/203 naive and 3 fixed; data SQL 11/51/201 naive and 1 fixed. Shared auth contributes two observed statements.
- `reports/hw04/raw/part3/development_http_smoke.json`: six real HTTPS8733 functional checks, clearly separate from final timing.
- `reports/hw04/part3/RUN_LOG.txt`, `REPORT_SECTION.md`, `AI_USE.md`: actual command output, report fragment and AI disclosure.

Median speed-ups: **1.524× / 3.057× / 5.245×** at sizes 10/50/200. Size10fixed p99 is slower (0.271× ratio) because iteration 22 took 115.455 ms; all samples are retained. No causal claim is made about that outlier.

## Verification commands

After loading private environment variables, run:

```sh
HW4_PART3_MYSQL_TESTS=1 HW4_PART3_OWNERSHIP=/private/tmp/hw4-part3-ownership.json \
  .venv/bin/pytest tests/test_hw04_part3.py tests/test_hw04_part3_seed.py \
  tests/test_hw04_part3_measurement.py tests/test_hw04_part3_index.py \
  tests/test_hw04_foundation_gate.py -q

.venv/bin/python scripts/hw04/part3/summarize.py \
  --raw reports/hw04/raw/part3/attempts/20260928T003859.945761Z-cd277c20/requests.jsonl \
  --output-dir /private/tmp/part3-recomputed
```

Observed result: **52 passed**; dependency deprecation warnings only. Real MySQL checks cover equality, actual statement counters/auth, forced repeated/null manager cases, invalid inputs, empty/offset pages and concurrent requests. Use the direct pytest executable because the historical `code` package shadows stdlib `code` when invoking `python -m pytest` from the repository root. Part 2 owns adapting the broader legacy web test suite; Part 3 did not modify it.

Full setup and rerun commands are in `scripts/hw04/part3/README.md`. No seeder reset/drop option exists; a real repeat seed was refused and preserved in the log.

## Remaining integration and external evidence

1. Merge `codex/hw4-part3-performance` into Session2's integration branch. Retain the literal performance-router order and shared auth dependencies. Do not cherry-pick another copy of foundation B.
2. Compare measured source hashes with the integrated executed path. Rerun all 180 requests if query/auth/schema/serialization behavior changes. Part 2 reported its later ordinary `q` search-only fix in `routers/rentals.py`; it does not execute in these endpoints and can be documented as an unrelated source difference.
3. Import the real Postman collection `reports/hw04/part3/postman_collection.json`. **All six Postman screenshots are pending manual access:** naive/fixed ×10/50/200. The native UI inventory and local Applications directories contain no Postman. Exact private-variable, local TLS, cookie, request/test and capture steps plus filenames are in `reports/hw04/screenshots/part3/README.md`. No substitute image was fabricated.
4. Combine this fragment/evidence with Parts 1/2. The full homework PDF, Part 4, collaborators, final hw4 tag and tagged whole-homework verification remain outside this request.

## Final index evidence

Successful attempt: `reports/hw04/raw/part3/index/20260928T004453-df40d32d/`. `status.json` is complete; `comparison.json` records equal data/results and the observed `index/PRIMARY/4868 rows` -> `ref/ix_rentals_listing_title/1 row` plan change. `before.json`/`after.json` contain all inventories, EXPLAIN, query, parameters, results and hashes. Split files include `explain_before_traditional.json`, `explain_after_traditional.json`, `explain_before_format_json.txt`, `explain_after_format_json.txt`, `indexes_before.json`, `indexes_after.json` and journal snapshots.

Index execution revision: `62117550e2e2a253ea754152d2bb1007cc6b1f9a`; dirty=true from report/evidence files only, listed in its `configuration.json`. Source/migration bytes were unchanged. Database now has migrations 001 and 003 plus the title index. An indexed retry was intentionally refused with no DDL and preserved separately at `index/20260928T004504-a87ff5a9/`; migration repeat was a no-op. To reproduce the original unindexed 180 run, use a fresh owned instance and apply only migration 001; do not drop this index or reseed a shared database.

## Review resolution and final verification

Three simplification reviewers ran (reuse, quality, efficiency). Applied two hash-reuse improvements before measurement; skipped low-value constant extraction. The code review's one confirmed P2 was the seed CLI opening its evidence path after committing inserts. The final follow-up reserves an exclusive output first and writes/flushes/fsyncs it while the DB transaction is still open, before commit. Exceptions remove this invocation's reservation. An invalid-parent regression failed before the fix and passed afterward, along with failure cleanup. This changes only seeding/evidence safety; the actual 5,000/200 dataset and measured query paths are unchanged.

The completed nine-lens source-review receipt is preserved verbatim in `REVIEW.json`. It assessed `4cec543`, before final measurements and the seed-output fix; its historical "Ready with fixes" verdict and then-pending evidence statuses are not a fresh review of this final commit. The one actionable finding is resolved as described above. Two nonblocking coverage gaps remain: a real MySQL partial-DDL/missing-journal recovery fault was not injected, and ContextVar cleanup after downstream exception/cancellation was not tested directly (concurrent request isolation was tested). The review's external-provider attempt was rejected by automatic approval review because private-diff disclosure was outside authorization; native local adversarial review completed instead.

A subsequent bounded review of this handoff and `REPORT_SECTION.md` against the saved measurements and EXPLAIN found no material inconsistency; both accurately mark all six Postman images pending.

`reports/hw04/raw/part3/verification.part3.json` records 15 successful automated evidence checks and explicitly marks all six Postman screenshots pending. Final 52 focused tests passed (15 dependency deprecation warnings); saved metrics JSON/Markdown reproduce byte-for-byte. The app .py/.sql, requirements and launcher SHA256 hashes still match `benchmark_config.json`; benchmark/summarizer/index tool diffs from measured 9860a203 are empty. Raw console failure traces retain their original trailing whitespace; the source diff whitespace check passes when excluding that literal log.

Operational scope: local course experiment only. Preserve the dedicated data and evidence. If integration changes an executed path, rerun the entire measurement on a fresh unindexed owned instance; no production deployment or monitoring is involved.
