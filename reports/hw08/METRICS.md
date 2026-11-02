# HW8 observed results

Pragya Apurva | SID4=6102 | SEED=6102 | VERIFY_SEED=266102

Tested code and resolved `hw8` target: `8caf32f200a8411db513a784e2f3f7073e8339c5`.
Evidence refreshed November 2, 2026. Report: 23 pages, 21 original native Terminal captures and 2 VS Code snippets.
The PDF refresh and new captures are later evidence; they are not claimed to be inside the existing tag.
Real-model journey: qwen2.5:7b, fixture=false. Failure tests: real Kafka/processes with fixture prose.

| Failure scenario | Before fix: observed | After fix: observed | Evidence under raw/part3/ |
|---|---|---|---|
| Duplicate delivery | 2 dictionary rentals / distinct UUIDs; 2 pipeline final outputs | 1 dictionary rental; same UUID twice; 1 final logical output | duplicate_*.jsonl; pipeline_duplicate_*.jsonl |
| Writer killed mid-work | Early commit 32 for task offset 31; 0 outputs during 4-second observation after restart | Task offset 32 redelivered to restarted PID; 1 output then commit 33 | consumer_death_*.jsonl |
| Poison task | Exit 1 at first failed attempt; no DLQ or later output | 3 attempts, 1 DLQ record; later task at offset 36 completes and commits 37 | poison_*.jsonl |
| Two partitions / two Writers | 20 outputs over partitions 0 and 1; not in send order | 20 outputs in partition 1; sequence 1-20 | ordering_unkeyed.csv; ordering_keyed.csv |

Unkeyed observed sequence: [2, 4, 6, 8, 1, 10, 12, 14, 16, 3, 18, 20, 5, 7, 9, 11, 13, 15, 17, 19].
Keyed observed sequence: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20].
The baseline explicitly alternates partitions without a key. Both runs reuse the VERIFY_SEED delay schedule.
Draft offsets define observed completion order; task offsets in separate partitions are not a global clock.
Pipeline experiment run: `hw8-20261102T080502Z`, 08:05:02-08:06:13 UTC.
Dictionary replay was recorded separately at 08:06:15 UTC on the same code.

Publish-before-commit boundary: Writer recovered cached work after termination; downstream receipts retained one final logical output.
A prior broker-container replacement test confirmed volume persistence, not high availability.

## Verification

- Full verifier: 24/24 checks passed without skip flags at the `hw8` target.
- HTTP roles: reader/writer/moderator login 200; missing or invalid tokens and wrong password 401; reader CREATE 403 / GET 200; writer and moderator CREATE/GET 200.
- Focused HW8/shared-auth tests: 68 passed, zero skipped, 34 dependency deprecation warnings in 1.68 seconds, with real MySQL enabled.
- All six database tables kept identical row counts and content hashes during the focused tests.
- Twenty-one original Terminal captures and two VS Code snippets are indexed in screenshots/current_manifest.json with SHA-256 hashes and report locations.
- Local model digest and hardware were confirmed against Ollama and sysctl during report finalization.
- GitHub link and both required collaborators were verified October 29; the dated receipt is retained.

## Limits

Entity rentals and replay cache disappear on worker restart. Pipeline receipts require intact local SQLite state.
Kafka publication and SQLite updates are not atomic; delivery is at least once with application deduplication.
A single broker with replication factor 1 does not demonstrate high availability. No throughput or latency benchmark is claimed.
Earlier failed/corrected runs remain in RUN_LOG.txt. Application code and the existing tag are unchanged by this report refresh.
