# Homework 1 - Part 3 Non-Determinism Metrics

## Fixed input

The unchanged experiment input is saved in `cases/nondeterminism_input.json`.

- Title: Modern Two-Bedroom Apartment Near Downtown San Jose
- Content: Bright two-bedroom apartment with in-unit laundry, covered parking, pet-friendly policies, and convenient light rail access near downtown San Jose.
- Model: `qwen3:1.7b`
- Successful runs: 20 at temperature 0.7 and 20 at temperature 0.0
- Experiment window: 2026-08-31T02:05:20Z to 2026-08-31T02:23:34Z

## Tag-set results

| Metric | Temp 0.7 | Temp 0.0 |
|---|---:|---:|
| Distinct tag sets | 12 | 2 |
| Tags in all 20 runs | None | `modern two-bedroom apartment`; `pet-friendly` |
| Tags in exactly 1 run | `convenient light rail access`; `downtown san jose light rail`; `in-unit laundry & light rail`; `modern`; `modern apartment`; `near downtown san jose`; `pet-friendly and light rail access`; `pet-friendly with parking` | `light rail access` |

## Latency results

Latency is the sum of the Planner and Reviewer call durations for each successful pipeline run. Percentiles use linear interpolation.

| Metric (ms) | Temp 0.7 | Temp 0.0 |
|---|---:|---:|
| p50 | 22,820.50 | 18,844.50 |
| p95 | 48,035.70 | 25,745.40 |
| p99 | 54,126.34 | 26,025.08 |

## Interpretation

Two users submitting this identical listing at temperature 0.7 could receive noticeably different emphases. One run might focus on `downtown san jose`, while another might choose `pet-friendly policies` or `light rail access`. Temperature 0.0 was substantially more stable: 19 of 20 runs selected the same three-tag set, although one run substituted `light rail access` for `downtown san jose`.

Run-to-run variation is acceptable when tags are used for exploratory discovery or search suggestions because several faithful descriptions can be useful. It is not acceptable when the generated value drives a deterministic business rule, such as eligibility, compliance status, or billing, because identical inputs should not receive different decisions.

## Attempt accounting

Temperature 0.7 required 22 attempts to obtain 20 publishable runs. Two attempts were rejected by the deterministic Finalizer because the Reviewer returned non-empty `issues`. Temperature 0.0 completed 20 publishable runs in exactly 20 attempts. Rejected attempts remain in the raw file for auditability and are excluded from tag and latency metrics.

## Commands

The recorded experiment used this command when the output file did not yet exist:

```bash
python reports/hw01/run_nondeterminism.py --model qwen3:1.7b --count 20 --temperatures 0.7 0.0 --timeout 120 --max-errors 10
```

The checkpointed raw output is `raw/nondeterminism_runs.json`. To deliberately replace that checked-in result and run a fresh 40-run experiment, add `--overwrite`. To validate and reuse the existing completed checkpoint without calling Ollama, add `--resume`.
