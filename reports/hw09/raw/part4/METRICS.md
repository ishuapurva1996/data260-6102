# Part 4 results

Pragya Apurva · DATA 260

## Held-out comparison

Each row uses the same 10 held-out questions, in the same order, with the semantic cache bypassed. Latency is the mean wall time per question. Offline grading and the model warm-up are excluded.

| Variant | Correct | Incorrect | Mean attempts | Mean latency (ms) |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 5 | 5 | 1.00 | 1,296.2 |
| Evaluator Repair | 10 | 0 | 1.50 | 1,625.0 |
| Lesson Memory | 10 | 0 | 1.10 | 1,313.6 |
| Validated Improvement | 10 | 0 | 1.10 | 1,242.6 |

Evaluator Repair changed final correctness from 5/10 to 10/10, with mean attempts of 1.50. Validated Improvement reached 10/10 with 1.10 mean attempts. Lesson Memory and Validated Improvement used the same lesson because it passed validation. Their latency difference reflects separate runs of the same configuration.

## Validation and controls

- Training exposed immediate-availability errors on S6102-R-9401, S6102-R-9402. The scoped correction interprets bucket B as ready now, including zero. A separate training question, S6102-R-9403, loaded `rental-ready-units-v1` and passed on its first answer. The persisted use count reached 1.
- In the controlled repair case, S6102-R-9402, the first draft was intentionally stripped of immediate availability. Feedback led to a passing second answer. For S6102-R-9401, the field was stripped on both attempts. The run stopped after attempt two with `REVISE`. Controlled omissions were confined to these demonstrations.
- The gate retained the candidate. Targeted first-answer passes changed from 0/3 to 2/3, while final passes across all validation questions changed from 6/6 to 6/6. No validation regressions were observed. The full pairs and claim differences are in [validation.json](validation.json).

## Measurement context

Ollama 0.33.0 served qwen2.5:7b (Q4_K_M) on Apple M4 with 24 GiB RAM. The run used temperature 0 and seed 6102. The request log recorded 48 POST requests, matching the sum of answer attempts plus one warm-up. The audit recorded no other inference requests during that interval.

The reference contains a small synthetic inventory export and a deliberately opaque field. The evaluator supplies a known value for an incorrect field, so these results describe reference-assisted repair. The small structured fixture set limits how far these results generalize to open-ended rental questions and sources with incomplete facts.

The zero-availability validation case remained incorrect on its first answer after loading the lesson. It used the advertised count of 3 and passed after evaluator feedback supplied 0. The lesson met the retention rule because that target remained unchanged and the other targets improved. This case is preserved in the paired validation evidence.
