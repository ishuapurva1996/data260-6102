# HW10 evaluation evidence

The live run used the evaluator at merge commit
`6e8cceb1b6dd40ab8f19e4549aff14a54e52322f`. It includes tracing checkpoint A1
`2cfb15d5eaa589c195c3f8b42168fd9fe5caec41` and the draft and human label freeze A2
`7893184b8296862a4bfb04f9e8c6461aa89a6de8`. The runner verified the SHA-256
checksums against both the A2 blobs and the working files and matched 20 unique
drafts to 20 ratings by case ID.

| Frozen file | SHA-256 |
| --- | --- |
| `eval_cases.json` | `f5bc096bd248b25a508fecf7d0992af5d8aafe7ac9077a8799c0ff086bab5fff` |
| `human_labels.csv` | `2ae6c19e4ed25c99cc7384d02a276f3af913917ee7fde572974a58e986d6ddfb` |

The judge used Python 3.12.13, DeepEval 3.9.4, langchain-ollama 1.1.0,
and Ollama 0.33.0 on an Apple M4. The local model was `qwen2.5:7b`
with manifest digest
`845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`.
The Planner, Writer, and Reviewer used the same model tag and weights.
The judge used JSON mode, temperature 0, seed 6102, an 8,192-token
context, and a 256-token output limit. Evidence lookup had a 5-second
budget, Ollama connection and read timeouts were 45 seconds, and each
case had a 180-second wall deadline. Each metric allowed two attempts.
The score and validation files record the full rubric and settings.

## Pipeline case

Trace `103f3e33-f9bb-459e-9e6d-5dda37f24b45` was the confirmed miss
from [A's trace evidence](../tracing/README.md). Its original API and
Kafka spans came from source `022766b646aedfa272f095348fad5d6256ce7ee1`.
The evaluator verified the topic, partition, offset, and correlation ID
chain and saved the original messages in
[`pipeline_scores.jsonl`](pipeline_scores.jsonl).

| Stage | Normalized score | Score out of 5 |
| --- | ---: | ---: |
| Planner | 0.90 | 5 |
| Writer | 0.70 | 4 |
| Reviewer | 0.70 | 4 |

All three stages produced the same text, which correctly says that Cedar Court
has two available units. The Planner supplied the answer directly and omitted
the requested planning steps. The Writer carried the correct fact forward,
and the Reviewer kept the draft verbatim, giving a final-minus-draft score of
0. The Planner's high score missed the absent steps. The Writer and Reviewer
reasons also claimed the text omitted the listing title, although the text
names Cedar Court. The property type was outside the question's scope.

The [evaluation span](spans.jsonl) took 15.33 seconds. It was recorded
in a separate session after the original API request and represents the
evaluator's elapsed time for this case.

## Judge validation

Three fresh passes scored all 20 frozen drafts under the same settings.
All 60 measurements succeeded on their first attempt. The
[raw scores and reasons](judge_scores.csv) and the
[validation summary](judge_validation.json) record the three run IDs,
case comparisons, and settings.

| Measure | Result |
| --- | ---: |
| Spearman correlation with human labels, pass 1 | 0.5403 |
| Mean absolute difference from human labels, pass 1 | 0.75 points |
| Cases that changed across three passes | 0 of 20 (0%) |
| Mean per-case score change | 0 points |
| Maximum per-case score change | 0 points |

Pass 1 matched 7 of 20 human scores. Two scores differed by two points.
The judge gave 15 drafts a 4, so it distinguished relatively few cases
on this scale. In `hw10-05`, it scored a draft 2 and said the draft
failed to answer whether there were at least two units. The draft
explicitly answered “No” and explained that only one unit was available.
The human rating was 4. The separate practice check likewise produced
a parseable score but claimed the answer omitted a listing ID that it
included.

Use this judge as a diagnostic alongside human review. The 20 cases
show repeatable scores under fixed settings and limited agreement with
one human rater. A deployment gate would need a larger held-out set
with independently rated examples, including wrong unit counts,
wrong listings, and invented details. Measure how often the proposed
gate lets those serious errors through and how often it blocks correct
answers before setting a threshold.

## Failure checks

[`failure_checks.json`](failure_checks.json) records two CLI invocations
with a four-second case deadline, a two-second Ollama request timeout, and
a one-second evidence lookup budget. Replacing the saved Writer draft
with a JSON array returned `malformed_evidence` in 0.061 seconds. Using
loopback port 1, where no judge was listening, returned `judge_unavailable`
in 0.055 seconds. Both exited 1, produced an error span, and omitted a
numeric score.

## Reproduce the live runs

Use the [evaluator setup and commands](../../../../docs/HW10-evaluation.md).
Set `A1_SHA`, `A2_SHA`, `CASES_SHA256`, `LABELS_SHA256`, and
`JUDGE_DIGEST` to the values above. Run the pipeline command with
`--evidence-root reports/hw10/raw`, the trace ID above, and
`--model-digest "$JUDGE_DIGEST"`. Run the validation command with
the same judge settings. For a reproduction that preserves the recorded
evidence, pass `--output-dir` with a fresh directory to each command.

The saved pipeline record includes a `final` alias for the dashboard.
It repeats the original `final_answer` verbatim. The current evaluator
writes both fields.
