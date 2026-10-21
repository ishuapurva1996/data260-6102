# Homework 6 measured results

Pragya Apurva, SID4 6102. Measured run `s6102-D-194d3e097b294115aefb49652326058d` on application commit `4c0bd7c2dd0bedeab73d6a31d9f5c3a83a84e961`. The 30 primary turns and five probes were repeated in a fresh namespace for each setting. The saved `part3/metrics/per_turn.csv`, `part3/metrics/scores.json`, and `part3/metrics/memory_cost.csv` support these values; see `part3/RESULTS.md` for method and limits.

| Setting | Mean prompt tokens/turn | Mean HTTP latency (ms) | Mean probe quality / 5 |
| --- | ---: | ---: | ---: |
| N=4 | 493.333 | 18,576.518 | 4.40 |
| N=12 | 753.900 | 23,930.900 | 4.40 |
| N=30 | 1,201.100 | 31,785.058 | 4.80 |
| N=12 + 160-token window eviction | 539.800 | 23,392.922 | 4.80 |

N counts previous stored user/assistant records; the current user message is added once, separately. D begins with at most 12 previous records and evicts oldest whole records until the rendered window fits 160 Qwen tokens. Relative to N=12, D used 16,194 rather than 22,617 primary prompt tokens: 6,423 fewer, or 28.40%. Mean probe quality changed from 4.4 to 4.8. All 120 primary requests and 20 probes succeeded. These are observations for one synthetic conversation per condition, with fixed order and sequential probes.

At assigned prices of $1/million prompt tokens and $5/million completion tokens, the 10,000-conversation estimate is `10,000 × (P + 5 × O) / 1,000,000`, using one 30-primary-turn conversation's token totals. Auxiliary extraction and summarization are added only in the rightmost cost column. Probes and pilot work are excluded; embeddings have no assigned dollar price.

| Setting | Main prompt/completion tokens | Auxiliary prompt/completion tokens | Main chat / 10,000 | Main + generative memory / 10,000 |
| --- | ---: | ---: | ---: | ---: |
| N=4 | 14,800 / 1,135 | 16,897 / 2,113 | $204.75 | $479.37 |
| N=12 | 22,617 / 1,199 | 16,957 / 2,139 | $286.12 | $562.64 |
| N=30 | 36,033 / 1,425 | 17,083 / 2,132 | $431.58 | $709.01 |
| N=12 + eviction | 16,194 / 1,127 | 16,664 / 2,436 | $218.29 | $506.73 |

Best qualifying total generative cost: N=4, $479.37, mean quality 4.4 and no incorrect essential fact. Highest cost: N=30, $709.01, mean quality 4.8. All four met the frozen mean-quality threshold of 4 without an incorrect essential claim. These are hypothetical assigned-price estimates, not paid local-model charges.

Study limits: a single 30-turn synthetic conversation per setting, fixed A-B-C-D order, sequential probes that could influence subsequent memory, background Docker services, and Codex criterion-based scoring rather than independent human grading. The unscored pilot and failed export attempts are retained separately from the accepted measurement.
