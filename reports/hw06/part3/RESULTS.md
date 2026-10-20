# Part 3 measured memory costs

Student: Pragya Apurva. Real integrated study on 2026-10-20, 12:10:47 PDT to 13:07:23 PDT. All 120 primary requests and 20 probes succeeded on the first attempt. No measured errors, reruns, missing usage, output cutoffs or source changes occurred.

## Method and provenance

The fixed conversation has 30 submitted user messages, each receiving a reply. This normally gives 60 stored records before the five additional probes. N counts previous stored user/assistant records, excluding the current message. Each condition used a fresh user and session in the authenticated owner's synthetic namespace, with empty starting memory and no file-memory injection.

Measured source: `4c0bd7c2dd0bedeab73d6a31d9f5c3a83a84e961`. Application-source SHA256: `baf6ed1a45eb00e121b0c2091bb5c4f0fbc62c0469d386696fab381056543eba`. The two frozen input SHA256 values and complete source/configuration provenance are in `../raw/part3/measured-study/manifest.json`. The evidence commit is separate and changes only Part 3 results.

Runtime: Apple M4, 10 CPU cores, 24 GiB RAM; Python 3.12.14; Ollama 0.33.0; local qwen2.5:7b Q4_K_M, temperature 0, seed 6102, context 8192, output limit 1024 and per-model-call timeout 180 seconds. Embeddings use nomic-embed-text:v1.5, 768 dimensions. Summary cadence is five user requests; episodic top-k is three. Verify seed 266102 is recorded and was not used to generate a randomized workload. Full identities, installed package versions and hardware observations are in `verification/actual-environment.json` and the study manifest.

There was no explicit warm-up in any condition. A's earlier N30 pilot was unscored and is excluded. The four conditions ran sequentially in A, B, C, D order under one D runtime lease, with one request at a time on authenticated HTTPS port 8702.

## Required memory-cost table

Token and latency means use exactly 30 primary turns per row. Quality uses exactly five probes. HTTP latency includes transport, authentication, main generation and all memory work inside the request. Prompt-component counts are model-tokenizer text estimates; the reported main prompt total and signed template residual are preserved separately.

| Setting | Mean prompt tokens/turn | Mean completion tokens/turn | Mean HTTP latency (ms) | Probe quality (1-5) |
|---|---:|---:|---:|---:|
| N=4 | 493.333 | 37.833 | 18576.518 | 4.40 |
| N=12 | 753.900 | 39.967 | 23930.900 | 4.40 |
| N=30 | 1201.100 | 47.500 | 31785.058 | 4.80 |
| N=12 + token-budget eviction | 539.800 | 37.567 | 23392.922 | 4.80 |

## Eviction versus N12 baseline

The single D policy begins with at most 12 previous records and removes the oldest whole records until the rendered block fits 160 Qwen tokens. It leaves the current message separate and keeps durable memory intact. Every measured selection matched independent recomputation. The largest D window was 157 tokens. All four final namespaces contained 70 messages, seven summaries and 18 episodes.

B used 22,617 primary prompt tokens; D used 16,194. Savings were **28.40%**, or 6,423 tokens over the same 30 turns. Mean probe quality increased from 4.4 to 4.8, a **+0.40-point** change. Mean completion tokens were 39.967 for B and 37.567 for D. Mean HTTP latency was 23930.900 ms for B and 23392.922 ms for D.

## Projected cost for 10,000 30-turn conversations

At the assignment's hypothetical $1/million input and $5/million output prices, one measured conversation with prompt total P and completion total O projects to `10000 * (P + 5*O) / 1000000` dollars. The second estimate adds actual extraction and summarization input/output totals. Both exclude probes, pilot work and warm-ups. Each condition had 36 primary auxiliary-generation calls: 30 extractions and six session summaries. No lifetime summary was generated because every condition used one fresh session.

| Setting | Main-chat estimate | Main plus generative memory | Primary embedding calls / inputs |
|---|---:|---:|---:|
| N=4 | $204.75 | $479.37 | 48 / 48 |
| N=12 | $286.12 | $562.64 | 48 / 48 |
| N=30 | $431.58 | $709.01 | 48 / 48 |
| N=12 + token-budget eviction | $218.29 | $506.73 | 48 / 48 |

Embedding work is reported separately without a dollar estimate because no embedding price is assigned. Each primary conversation had 30 query embeddings and 18 fact embeddings. Actual embedding latency and separate records are in the metric JSON and `metrics/embeddings.json`.

Best qualifying is **A, N4**: mean quality 4.4, no incorrect essential fact, $204.75 main-chat and **$479.37 including generative memory**. This is the lowest total generative estimate among settings meeting the frozen mean-quality threshold of 4. All four qualify. A's accessibility answer has an important omission; the assigned score is 3, and the aggregate threshold still passes.

Worst by cost is **C, N30**: mean quality 4.8, $431.58 main-chat and **$709.01 including generative memory**. The lowest mean quality is a tie between A and B at 4.4. The implementation's deterministic first-in-order tie label is A.

D's main-plus-memory estimate is $55.91 (9.94%) below B. Its auxiliary generation costs $288.44 versus B's $276.52, so the full generative saving is smaller than the main-prompt saving. D has the same mean quality as C on these five probes, with a lower measured token-cost estimate.

## Scoring and limits

All settings correctly recalled the corrected budget, Willow Glen/San Jose and January 15, 2027. All pet answers specified one indoor cat but omitted Juniper, the frozen score-4 minor omission. A and B omitted the continuous route into the unit; C and D explicitly supplied the entrance-to-unit route and working-elevator condition. All exact answers, every criterion assessment and the explanations are preserved in `../raw/part3/scores.json` and summarized in `SCORING.md`. No incorrect essential assertion was found; omitted essential information was recorded as missing and scored at most 3.

Probes were sequential in fixed order because the published storage interface has no complete snapshot/clone operation. Earlier probes and answers persisted and could affect later probes, episodes and summaries. The single synthetic conversation, fixed condition order and lack of explicit warm-up limit conclusions about repeatability and latency. Unrelated Docker services remained running, as declared by A; the lease reserved cooperating HW6 model/app/embedding/database jobs. These results describe this workload and machine.

## Verification and export note

All 224 integrated offline HW6 checks passed before measurement. The completed study has 520 correlated events: 140 main request events, 168 auxiliary generation events and 212 embedding events. All 308 main and auxiliary model calls reported normal `stop` finishes; none touched the output cap. The source/input hashes and model identities matched postflight. The owned app stopped, the lease was released and port 8702 was free afterward.

Independent raw arithmetic matched every table value, and all seven regenerated export files were byte-identical. The original export CLI failed because JSON serializes the rubric's integer keys as strings. Postprocessing restored only those key types before calling the unchanged original validator/exporter. Frozen questions, criteria values, answers, scores and measured source were unchanged. `REPRODUCE.md` provides the exact normalization recipe. A should fix rubric-key normalization in `validate_scores` and add a scored-JSON round-trip regression check; no new measured run is required for that serialization fix.
