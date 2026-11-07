# Homework 9 measured results

Pragya Apurva · DATA 260

## Part 1 and Part 2

Part 1: views 1–25; MySQL at reads 9/10/20/25 = 0/10/20/20; final Redis=25, MySQL=20. Separate counters, concurrent initialization, and monotonic recovery passed.

Part 2 (12 requests): 7 hits, 5 misses, 0 errors; hit rate 58.33%. Mean server hit latency 27.445 ms; mean miss latency 9,012.847 ms. Hits bypassed Kafka and the three generative stages. Cases 7–9 were incorrect cached answers and remain included. Source: 4bc060d11adbd2b8a13bbb525b23cc0280b0ab5d.

## Part 3 audited threshold sweep

| Threshold | Hits / 40 | Hit rate | Incorrect cached / 40 | False-hit rate | Mean HTTP ms | Misses | Cost (seconds-equivalent) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.75 | 38 | 95.0% | 21 | 52.5% | 663.40 | 2 | 6310 |
| 0.80 | 34 | 85.0% | 17 | 42.5% | 2078.91 | 6 | 5130 |
| 0.85 | 30 | 75.0% | 13 | 32.5% | 3832.83 | 10 | 3950 |
| 0.90 | 29 | 72.5% | 15 | 37.5% | 4131.69 | 11 | 4555 |
| 0.95 | 29 | 72.5% | 15 | 37.5% | 4254.44 | 11 | 4555 |

Use audited-threshold-summary.json and audited-requests.jsonl as the final results. Hit rate = hits/40; false-hit rate = factually incorrect cached answers/40. At 0.85, 10/20 should-miss cases were accepted; 13/40 answers were incorrect cache hits. There were no wrong live answers in this sweep.

The keyword screen wrongly accepted a deposit answer without a definition of wear and tear and a lease answer without an explanation of a co-signer. The full-rubric audit corrected those two judgments in separate audited records. Automatic scores, expected facts and labels are unchanged.

Fixed illustrative cost = misses × 5 + incorrect cached answers × 300 seconds-equivalent. Five seconds is a nominal generation budget; 300 seconds is an assumed five-minute support correction. Neither is measured support effort or a monetary charge. The miss weight understates observed miss latency. Minimum cost is 3,950 at 0.85; ties prefer the higher threshold. It still produces 13 incorrect cached answers out of 40.

Each pass began with the same 10 verified seed entries. Normal writes on misses changed the within-pass cache. At 0.90/0.95, P02 misses and adds an answer; P04 then matches it across listing identities. This explains non-monotonic wrong-hit counts.

Source: 52c8ef470b124605a0fc51dd8c5821b4a5f3738b. Dependency B: 6938c71110845b7b73c53b795b709399f8a523a1. Frozen YAML: 3511ae67588f61eeff4199aa8f4db294aca04c57; SHA-256 4c180dd5a8b5dbd007797225889d1cb7e0921339d0670683b225674ee76f0c26.

Separate stale demo: prime at 3 (v12), SQL PUT to 1 (v13), stale hit at 3 with the demo filter disabled, enforced miss at 1, then fresh hit at 1. Dataset-wide invalidation also evicts unrelated listing answers. Counter-only checkpoints preserve the fact version.

## Part 4 held-out comparison

| Variant | Correct | Incorrect | Average attempts | Average latency (ms) |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 5 | 5 | 1.00 | 1296.2 |
| Evaluator Repair | 10 | 0 | 1.50 | 1625.0 |
| Lesson Memory | 10 | 0 | 1.10 | 1313.6 |
| Validated Improvement | 10 | 0 | 1.10 | 1242.6 |

Ten identical input-only held-out cases per row. Direct local adapter; semantic cache bypassed. Same reference-backed scoring, prompts and model; frozen per-variant lesson snapshots. End-to-end latency includes generation, lessons, in-loop evaluation/repair and response formatting; excludes warm-up and offline grading. Answer attempts count generated answers. All totals sum to 10.

Validation: target initial passes 0/3 → 2/3; final validation passes 6/6 → 6/6; no regression or new unsupported unrelated claims. The zero case still needed evaluator feedback. Lesson Memory and Validated Improvement used the same accepted lesson, so their latency difference reflects separate runs.

Part 4 frozen source: 7767adc8fdc4afa8ba2157ea9ecda15f41162266. Held-out SHA-256: 49c667b18a848fdb3756805bcaf6d27a658c307f6b38a2c943ed270a96f615b3. Timing audit: 48 real chat requests = 47 answer attempts + 1 warm-up.

Limitations: small synthetic structured fixtures, known reference values supplied in feedback, single timing runs without confidence intervals, and dependence on reference completeness. Integration preserved measured cache/agent code and all held-out inputs; no affected benchmark rerun was required.
