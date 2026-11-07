# Part 3: Threshold economics and stale answers

Pragya Apurva | DATA 260 | November 6, 2026

Frozen YAML commit: `3511ae67588f61eeff4199aa8f4db294aca04c57`. SHA-256: `4c180dd5a8b5dbd007797225889d1cb7e0921339d0670683b225674ee76f0c26`. Labels and costs were committed before the sweep and remain unchanged.

Ten verified live seed entries were restored into five fresh namespaces. All 200 authenticated requests returned HTTP 200. Fixtures, account, case order, data version, model digests, and generation settings were fixed. The normal store-on-miss behavior stayed enabled within each pass. Restored seed fields and vectors were checked byte for byte after all passes.

| Threshold | Hits / 40 | Hit rate | Wrong cached / 40 | False-hit rate | Mean HTTP latency (ms) | Misses | Cost (seconds-equivalent) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.75 | 38 | 95.0% | 21 | 52.5% | 663.40 | 2 | 6310 |
| 0.80 | 34 | 85.0% | 17 | 42.5% | 2078.91 | 6 | 5130 |
| 0.85 | 30 | 75.0% | 13 | 32.5% | 3832.83 | 10 | 3950 |
| 0.90 | 29 | 72.5% | 15 | 37.5% | 4131.69 | 11 | 4555 |
| 0.95 | 29 | 72.5% | 15 | 37.5% | 4254.44 | 11 | 4555 |

Hit rate is hits divided by 40. False-hit rate is factually incorrect cached answers divided by 40. A separate negative-case acceptance rate counts hits on the 20 should-miss cases; it is retained in audited-threshold-summary.json. Wrong live answers are counted separately and do not become false hits. HTTP latency includes the full POST/response interval; server and stage timings are retained per request.

All answer decisions were reviewed against the full expected facts/rubrics frozen in the YAML. The automatic keyword screen produced two false correctness judgments: a deposit definition mentioned wear and tear without defining it, and a lease definition mentioned responsibilities without explaining a co-signer. answer-audit.json documents both corrections and every reviewed request. Original automatic scores and their preliminary summary remain unchanged in scored-requests.jsonl and threshold-summary.json; this table uses audited-requests.jsonl. No expected fact or should-hit label changed.

## Costs and choice

Both costs use seconds-equivalent: a miss costs 5 seconds, a nominal local three-stage generation budget; a wrong cached answer costs 300 seconds, an assumed five-minute support correction. These are fixed illustrative weights, not measured support effort or monetary charges. The nominal miss weight understates the observed miss latency, so the cost column must not be read as measured elapsed time. Total cost = misses × 5 + incorrect cached answers × 300. Actual measured latency remains a separate column.

Choose **0.85** from the five tested cutoffs: it minimizes the frozen cost at 3950 seconds-equivalent. The predeclared tie-break chooses the higher threshold. A separate smoke run at this setting returned a fresh miss and then a hit. This threshold still returns 13 wrong cached answers in 40 requests. Before production use, matching should also require the same listing identity; version checks alone cannot prevent cross-listing semantic confusion.

At 0.90 and 0.95, P02's similarity of 0.876015127 falls below the cutoff, so its fresh paraphrase answer enters the cache. P04 then matches that answer from a different listing at 0.999324322. This change in within-pass cache contents helps explain the increase from 13 wrong cached answers at 0.85 to 15 at 0.90 and 0.95. Every pass began with the same seed; normal cache writes remained enabled.

## One observed false hit

- Cached query: How many units are available at S6102-R-9102?
- Incoming query: How many units are available at S6102-R-9106?
- Similarity: 0.999333382; cutoff 0.75.
- Returned cached answer: The rental housing draft is clear and accurate. Here is the final answer: At S6102-R-9102, there are 4 units available.
- Correct answer: S6102-R-9106 has 1 available unit.
- Likely embedding confusion: the question template and requested field are identical; only the listing code changes. Their vectors are nearly identical, so cosine similarity does not preserve record identity.

The trace comes from the frozen sweep. No supplemental diagnostic was needed.

## Stale answer and version enforcement

The separate S6102-R-9199 fixture began with 3 available units. An authenticated SQL PUT changed it to 1. In the restricted stale-demo namespace, bypassing the version filter returned the old cached 3. Restarting the same namespace with normal enforcement returned a fresh miss at 1 and then a hit at 1.

| Step | Cached | Current version | Matched version | Returned answer |
| --- | --- | ---: | ---: | --- |
| prime_3 | False | 12 | None | At S6102-R-9199, there are 3 units available. |
| stale_hit_3_after_update_to_1 | True | 13 | 12 | At S6102-R-9199, there are 3 units available. |
| enforced_fresh_miss_1 | False | 13 | None | At S6102-R-9199, there is 1 unit available. |
| enforced_fresh_hit_1 | True | 13 | 13 | At S6102-R-9199, there is 1 unit available. |

Rental writes advance one dataset-wide version in the same SQL transaction. Cache lookup filters to the current version before selecting a neighbor, and stale in-flight results are not stored. This is simple and blocks reuse of old facts, but one listing mutation also invalidates unrelated listing answers and may lower the hit rate.

## Reproduction and evidence

Use docs/HW9_CACHE.md for the isolated service setup and requirements-hw09-cache.txt. Set private account/database variables and PYTHONPATH=.:code. Run `python -m scripts.hw09.cache_experiments seed --runtime <external-directory>`, review the ten answers, and create seed-reviewed.json. Then run the `sweep` and `stale` phases with the same runtime and configuration. Finally run `python -m scripts.hw09.analyze_cache_experiments --runtime <external-directory>`. Every run requires fresh namespaces, logs, and an owned empty database; use a fresh isolated Redis service for a complete rerun. The shared RuntimeLease directory must be the ollama-shared sibling of that runtime directory.

Source dependency: B commit `6938c71110845b7b73c53b795b709399f8a523a1`, merged with history. Seed service source: frozen-case commit. Sweep and stale source: runner commit `52c8ef470b124605a0fc51dd8c5821b4a5f3738b`. Hardware, library versions, model digests and settings are in run-metadata.json. Shared lease windows and D's release acknowledgement establish the coordinated exclusive model window. Unrelated Docker workloads remained on the host; these are local single-run latency measurements, without confidence intervals.

AI use: Codex prepared the synthetic cases, runner, calculations, and evidence text. Expected listing facts, returned seed answers, frozen labels, raw request outputs, and the stale transition were checked directly. The tests distinguish label acceptance from factually wrong answers and ensure listing-code digits cannot count as available-unit facts. The costs are assumptions declared before results. No label edits or supplemental sweep requests were made after results.
