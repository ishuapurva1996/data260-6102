# HW8 observed results

Pragya Apurva | SID4=6102 | SEED=6102 | VERIFY_SEED=266102

Tested source: `6f309a36a1491146686cafbba647c2226cdaa654`. Failure source: `6f309a36a1491146686cafbba647c2226cdaa654`.
Entity replay source: `e1e445e77246948987f86e6e74b3ea16c62493bb` (same worker behavior; before final Docker volume fix).
Real-model journey: qwen2.5:7b. Transport failure runs: explicitly labeled fixture prose.

| Failure scenario | Before fix: observed | After fix: observed | Evidence under raw/part3/ |
|---|---|---|---|
| Duplicate delivery | 2 dictionary rentals / distinct UUIDs; 2 pipeline final outputs | 1 dictionary rental; same UUID twice; 1 pipeline final output | duplicate_*.jsonl; pipeline_duplicate_*.jsonl |
| Writer killed mid-work | Early commit at offset 6; 0 outputs during 4-second observation after restart | Same offset 7 redelivered; 1 output then commit 8 | consumer_death_*.jsonl |
| Poison task | Writer exit 1 after attempt 1; later task has 0 outputs | 3 total attempts, 1 consumed DLQ record; later same-partition task completes | poison_*.jsonl |
| Two partitions / two Writers | 20 distinct outputs over partitions 0 and 1; not in send order | 20 distinct outputs in partition 1; sequence 1-20 | ordering_unkeyed.csv; ordering_keyed.csv |

Unkeyed observed order: [2, 4, 6, 8, 1, 10, 12, 14, 16, 3, 18, 20, 5, 7, 9, 11, 13, 15, 17, 19].
Keyed observed order: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20].
Unkeyed distribution deliberately alternated explicit partitions with no key.
Both runs used the same seeded delay schedule and unique per-run correlation IDs.
Draft-topic offsets establish observation order; source offsets from different partitions are not a global clock.

Publish-before-commit boundary: cached Writer output recovered after SIGKILL;
Reviewer suppressed the repeated Kafka record; one final logical output.
Local Kafka-volume check: a real task record survived broker-container replacement
(end offset 1 before and after). This is not a high-availability experiment.

## Verification and limits

- Objective smoke/evidence checks: 17/18 passed.
- Live authenticated FastAPI check: blocked/failing while setup approval is pending.
- Focused HW8/shared-auth tests: 37 passed; 31 real-MySQL tests skipped.
- Ruff and whitespace checks passed.
- Kafka, dictionary worker, real three-process local-model journey and all four failure experiments were observed.
- FastAPI startup screenshot and authenticated HTTP round trip are pending; direct Kafka outputs must not be represented as HTTP outputs.
- GitHub link loaded; collaborator membership requires GitHub reauthentication.
- `hw8` tag is pending successful remaining acceptance work. No push/publication/submission occurred.

The first harness run stopped recovered Writer before its commit acknowledgment
was captured. Its verifier failed. The harness now waits for offset_committed;
RUN_LOG.txt retains the failed and corrected runs. Kafka log.dirs was also corrected
to the mounted volume and tested by actual container replacement.

Dictionary rentals and their replay cache disappear on entity-worker restart.
Pipeline receipts require intact local state. Kafka/SQLite are not an atomic transaction;
transport is at least once with application deduplication. No latency or throughput benchmark is claimed.
