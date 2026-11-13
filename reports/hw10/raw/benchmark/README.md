# HW10 Parts 4.2 and 4.3 evidence

Measured source `d14796a39f8934965913c84fb7217f2b6dbd11c4` includes A1
`2cfb15d5eaa589c195c3f8b42168fd9fe5caec41`, the immutable A2 label freeze
`7893184b8296862a4bfb04f9e8c6461aa89a6de8`, and B1
`fc375db61d24243b7a54d900ec6245f043c2afe2`. The stack ran on an Apple M4
with 24 GiB RAM and Ollama 0.33.0. The generator and judge used local
`qwen2.5:7b` with manifest digest
`845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`.
The judge used DeepEval 3.9.4 and the same rubric, settings, and timeouts as B1.
The Planner, Writer, and Reviewer used a 4,096-token context and the judge used
8,192 tokens. The embedding model was `nomic-embed-text:v1.5`. Redis used cutoff
0.85 with data-version enforcement and a dedicated empty index before every
measured request. Each of the 50 distinct questions concerns an approved
synthetic rental listing and follows the live authenticated pipeline.

## Example traces

| Example | Trace ID | Result |
| --- | --- | --- |
| Cache hit | `bdf62b55-6040-4701-8eae-3c0e6db8bf53` | Exact repeat of the successful miss as the same user. The API took 578.69 ms and returned after cache lookup. |
| Successful miss | `813b4e22-6b35-4f5c-a163-5350c18652d6` | HTTP 200, completed miss, three agents, four Kafka handoffs, and successful evaluation. The API took 11,795.22 ms. |
| Controlled failure | `05a689b3-b160-4fcb-a383-fb2c58aff1d3` | The Writer received Ollama 404 for the intentionally missing model. Three attempts ended at `s6102_dead_letter`, partition 0, offset 0. The API returned HTTP 504 at its deadline. |

The original Writer model and consumer group were restored. The same question
then returned HTTP 200 as a confirmed miss through Planner, Writer, Reviewer,
and final delivery under `ce24f3d8-608d-4e7f-a834-7953c5acd6d0`.
The [example receipts](example_receipts.json) include the recovery spans and
linked case. [Example IDs](examples.json) can be loaded directly in Streamlit.

## Timing results

| Stage | p50 (ms) | p95 (ms) | Share of full trace |
| --- | ---: | ---: | ---: |
| Cache lookup | 547.11 | 824.76 | 1.03% |
| Planner | 7,192.90 | 10,559.49 | 13.13% |
| Writer | 5,640.52 | 7,880.57 | 10.26% |
| Reviewer | 6,198.59 | 8,509.46 | 11.08% |
| Queue wait (total) | 16.55 | 63.25 | 0.05% |
| Evaluation | 34,246.01 | 43,386.94 | 62.98% |

For the same 50 misses, API ingress-to-response latency was **20,489.16 ms
p50** and **27,301.06 ms p95**. Ingress-to-evaluation completion was
**54,400.97 ms p50** and **71,289.31 ms p95**. Queue wait is the sum of the
four matched enqueue-to-receipt intervals per trace, including final
delivery. Stage shares use summed stage durations divided by summed full-trace
durations. The six shares total 98.53%. The remaining 1.47% includes work
outside the timed stages, such as fact retrieval, Kafka client setup,
cache writes, and launching the evaluator.

Evaluation was the largest measured contributor. Ollama logs showed that
switching between the pipeline and judge context sizes caused model reloads.
First, test a common context configuration that preserves the judge's
8,192-token setting and compare timing and answer quality on this workload.
The measured run used the original pinned configurations.

## Pilot and exclusions

The standalone pilot completed all six stages in 33.82 seconds through
evaluation, with 13.65 seconds through the API response. The main run also
began with a warm-up. The [attempt log](attempts.jsonl) records 57 requests,
including the benchmark warm-up and replacement attempts.
[Exclusions](exclusions.jsonl) gives the reason for each of the seven omitted
attempts. Two successful evaluations had UTC intervals that exceeded their
monotonic durations by more than 100 ms. Two attempts returned HTTP 504
during clock interruptions. Late Reviewer work from the first timeout
overlapped the next request, so that request was excluded too. The successful
replay of the affected fixture questions displaced one surplus repeat.
The four successful replays used the same source, namespace, services, and
settings with an active macOS sleep assertion.

The independent audit matched each admitted HTTP receipt to a completed API
miss and four queue spans by topic, partition, offset, and timestamps. It
checked linkage to the saved evaluation score and confirmed the 50 admitted
traces did not overlap. The audit recomputed each per-trace interval, all
six percentiles and shares, and both latency distributions from raw records.

## Reproduce

Use the [benchmark runbook](../../../../docs/HW10-benchmark.md) from this worktree
and the [evaluator settings](../evaluation/README.md). With the isolated
services running, set `A1_SHA` and `B1_SHA` to the values above, load the
private environment, and choose a fresh namespace and output folder.

```bash
caffeinate -is python -m scripts.hw10.benchmark \
  --a1 "$A1_SHA" --b1 "$B1_SHA" --exclusive-runtime \
  --judge-model qwen2.5:7b \
  --judge-digest 845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e \
  --evaluator-python "$HW10_EVAL_RUNTIME/venv/bin/python" \
  --log-dir "$D_LOG_DIR" --output "$D_RUNTIME/measure-next"
```

The [timing rows](latency_rows.csv), [aggregate table](latency_summary.json),
[spans](spans.jsonl), and [linked scores and messages](pipeline_scores.jsonl)
contain the measured inputs. The [excluded spans](excluded_spans.jsonl)
preserve the trace evidence for the clock interruptions and their effect.
The raw evidence directory also contains A's tracing files and B's evaluation
files for the dashboard.
