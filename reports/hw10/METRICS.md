# HW10 measured results

## Dashboard window

2026-11-12 09:58:54.028 UTC to 2026-11-13 09:58:54.028 UTC.
[Recorded span sources and receipt](DASHBOARD_VERIFICATION.md).

| Completions | Hits | Misses | API errors | Hit rate | Error rate | API p50 / p95 | Hit p50 / p95 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 53 | 1 | 52 | 1 | 1.9% | 1.9% | 20,416.92 / 27,596.05 ms | 578.69 / 578.69 ms |

The window combines captured examples and trials. Its cache-hit rate describes
that evidence set. It is unsuitable as an estimate of normal demand because
the benchmark deliberately empties the experiment namespace.

## Pipeline evaluation

Question: “How many units are available at S6102-R-9101?”
Trace `103f3e33-f9bb-459e-9e6d-5dda37f24b45`.
[Original Kafka messages, rubric scores and reasons](raw/evaluation/pipeline_scores.jsonl).

| Stage | G-Eval normalized | Converted (1–5) |
| --- | ---: | ---: |
| Planner plan quality | 0.90 | 5 |
| Writer helpfulness | 0.70 | 4 |
| Reviewer final helpfulness | 0.70 | 4 |
| Final minus draft | 0.00 | 0 |

The Writer and Reviewer both said Cedar Court had two available units. The
Reviewer kept the correct draft verbatim, so the answer did not improve.
The Planner returned that same answer in place of a plan, despite its 5/5.
The helpfulness reasons claimed the title was absent although the text said
“Cedar Court.” The saved facts and text make both judge issues verifiable.

## Judge validation

Twenty original Writer drafts, twenty human labels and sixty fresh judge
calls across three passes. Freeze commit
`7893184b8296862a4bfb04f9e8c6461aa89a6de8`.
[Human labels](human_labels.csv), [raw judge scores](raw/evaluation/judge_scores.csv),
and [joined case table](raw/evaluation/judge_validation.json).

| Measure | Recomputed result |
| --- | ---: |
| Spearman, human vs. pass 1 (average ranks for ties) | 0.5403 |
| Mean absolute difference, human vs. pass 1 | 0.75 points |
| Exact human/pass 1 matches | 7 of 20 |
| Changed cases across three passes | 0 of 20 (0%) |
| Mean per-case max minus min across passes | 0.00 points |
| Largest per-case max minus min across passes | 0 points |

The judge repeated its ratings under fixed settings. The rank agreement is
moderate and 15 of 20 pass-1 scores were 4, limiting discrimination. Two
drafts differed from the human label by two points. Before using a threshold
to gate deployment, collect independently rated held-out examples and
measure false passes and false blocks, especially for wrong listing IDs,
wrong unit counts and invented rental facts.

## Fifty confirmed misses

[Attempt receipts](raw/benchmark/attempts.jsonl), [spans](raw/benchmark/spans.jsonl),
[per-trace latencies](raw/benchmark/latency_rows.csv),
[summary](raw/benchmark/latency_summary.json), and [exclusions](raw/benchmark/exclusions.jsonl).
Measured source `d14796a39f8934965913c84fb7217f2b6dbd11c4`.

| Stage | p50 (ms) | p95 (ms) | Share of full trace |
| --- | ---: | ---: | ---: |
| Cache lookup | 547.11 | 824.75 | 1.03% |
| Planner | 7,192.90 | 10,559.49 | 13.13% |
| Writer | 5,640.52 | 7,880.57 | 10.26% |
| Reviewer | 6,198.59 | 8,509.46 | 11.08% |
| Queue wait (total) | 16.55 | 63.25 | 0.05% |
| Evaluation | 34,246.01 | 43,386.94 | 62.98% |

API ingress to response was **20,489.16 ms p50** and **27,301.06 ms p95**.
Ingress to evaluation completion was **54,400.97 ms p50** and **71,289.31 ms p95**.
Percentiles use linear interpolation. Queue wait sums four Kafka handoffs
for each request before computing percentiles. Shares divide summed stage
durations by the same 50 requests' summed full-trace durations. The six
shares account for 98.53%. The remaining 1.47% includes fact retrieval,
client setup, cache writes and evaluator launch.

All 50 rows matched HTTP 200 with `is_cached=false`, a successful API
miss, a completed cache miss and a linked evaluation. The saved run includes
57 attempts and seven documented exclusions. Evaluation dominated the full
trace, and Planner time was the largest of the three agent stages in the API
path. The first full-trace optimization to test is keeping one Ollama context
configuration across generation and evaluation, then rerunning the same
workload and checking answer quality. Evaluation runs after the HTTP
response, so that experiment targets the evaluation workflow.
