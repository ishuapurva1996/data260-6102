# Part 4 implementation and evidence

Part 4 extends the existing shared Part 3 graph with a strict Pydantic Planner contract and bounded schema repair. `ResponseContractError` still routes malformed output back to the correct worker. There is no automatic tag padding, replacement, coercion, or unreviewed acceptance.

## Measured results

One frozen campaign contains exactly **75 real model runs**, plus one excluded ordinary warm-up and no pilots. All requests used the shared model adapter and normal Reviewer configuration.

- Schema cohort: **30/30 accepted on the first Planner attempt**, mean application-run latency **2104.40 ms**; all retry/ceiling buckets empty (N/A latency).
- Ceiling 2: **20/20 accepted**, mean **2485.63 ms**.
- Ceiling 10: **20/20 accepted**, mean **2472.25 ms**.
- Adversarial: **5/5 reached the ceiling**, each with ten invalid Planner attempts and no Reviewer execution. The embedded `AI`/`SJ` instructions repeatedly overrode minimum tag-length feedback.
- **70 accepted, five normal ceiling exits, zero operational errors, zero unknown runs.** No measured result was replaced or silently rerun.

The declared decision rule selects **ceiling 10**, because completion rates tied and its observed mean latency was lower. Both comparison groups completed in two turns; the small latency gap does not establish a causal speed advantage. Five adversarial failures are an observed fraction, not proof of deterministic behavior. The proposed prompt fix is documented but deliberately untested and unapplied to this baseline.

See [METRICS.md](METRICS.md), [deployment_choice.json](deployment_choice.json), and [unrounded results](raw/part4/20260914T0610-baseline/summary.json).

## Source and provenance

Execution HEAD was `17fd1b38ee3bc7046ddccbc60c324258186da2e1` with a dirty working tree on `codex/fix-hw1-form`. Part 3 commit `84ff199` remains its ancestor. During initial intake the other task committed its seven staged Part 2 files as `17fd1b3`; the implementation phase preserved that commit and left the Git index untouched. The existing checkout was used; no worktree was needed.

The [manifest](raw/part4/20260914T0610-baseline/manifest.json) freezes exact input bytes, schedule, source hashes, package versions, model digest, and metric definitions. Original source audit snapshots are under `sources/`; these are evidence, not another application. All source files that executed during the campaign remain recoverable even when later failure-path checks are strengthened. No later commit or edit is substituted for execution-time provenance.

The frozen calculation/verification implementation is separate from the postmeasurement presentation utility, [report_part4.py](../../scripts/report_part4.py). [Presentation provenance](presentation-provenance.json) records that utility's source hash. [Postmeasurement source reconciliation](raw/part4/checks/postmeasurement-source-changes.json) identifies any final review fixes relative to the frozen campaign; the original snapshots are never overwritten.

## Verification

- Premeasurement graph, schema, runner, aggregation and verifier gate: **90 unittest tests passed**.
- Final graph, schema, runner, aggregation and verifier gate after review fixes: **95 unittest tests passed**. All three confirmed review findings are resolved; see [review closure](raw/part4/checks/review-closure.json).
- Dependency consistency: passed (`pip check`); Pydantic 2.13.5, LangGraph 1.2.11, langchain-ollama 1.1.0.
- Offline verification: raw hashes, full trace replay, approval/revisions, turn limits, exact cohorts, timing/usage counters, tables and deployment decision. See [verification_part4.json](verification_part4.json).
- HW1 regression: **46 tests ran, one skipped, otherwise passed**.
- Existing API regression: **35 passed** (37 existing deprecation warnings).
- Final tests, review closure, syntax/diff and local-link checks are recorded in [RUN_LOG_PART4.txt](RUN_LOG_PART4.txt) and [checks](raw/part4/checks/).

Tests use scripted transports only in clearly labeled test fixtures. Measured results use real Ollama calls. The schema-repair demonstration is deterministic test evidence, excluded from the campaign; the adversarial ceiling screenshot is real measured evidence. `SEED=6102` and `VERIFY_SEED=266102` are identity metadata and were not supplied as model RNG seeds.

## Code and matching output screenshots

Each PNG is a browser rendering of saved source and its actual output, not a fabricated terminal screenshot. The adjacent HTML preserves selectable text. Place each relevant code excerpt above its matching output in the final PDF.

| Evidence | Screenshot | Saved page |
|---|---|---|
| Strict Pydantic schema and real accepted run | [PNG](screenshots/part4/01-schema-real-output.png) | [HTML](screenshots/part4/01-schema-real-output.html) |
| Validation feedback and three-turn repair; scripted test, excluded | [PNG](screenshots/part4/02-schema-repair-test.png) | [HTML](screenshots/part4/02-schema-repair-test.html) |
| Supervisor budget and real ten-turn adversarial stop | [PNG](screenshots/part4/03-bounded-termination.png) | [HTML](screenshots/part4/03-bounded-termination.html) |
| All measured tables and ceiling decision | [PNG](screenshots/part4/04-measured-tables.png) | [HTML](screenshots/part4/04-measured-tables.html) |
| Frozen adversarial case and actual rejected responses | [PNG](screenshots/part4/05-adversarial-output.png) | [HTML](screenshots/part4/05-adversarial-output.html) |

## Reproduction and final submission

[Reproduction instructions](REPRODUCIBLE_RUN_INSTRUCTIONS.md) separate expensive new model campaigns from offline report regeneration and verification. Preserve the existing campaign; new execution must use a new directory. Failed/interrupted runs remain visible and must never be silently replaced.

Part 4 was initially left uncommitted for review; the user subsequently authorized a local commit. Original execution and verification records retain the Git state observed when they were recorded. Nothing was pushed or tagged, and history was not rewritten. Root README additions preserve the other task's committed changes. Historical Part 3 evidence, hashes, original verification timestamps, and reports remain unchanged.

Remaining whole-assignment tasks: assemble `report.pdf` and the required `{last_name}_HW2.pdf` submission with code/output screenshots and repository link; write personal `AI_USE.md` answers; integrate Parts 1–4 run logs/instructions; confirm both required collaborators can access the repository; review/commit the final work; create the final HW2 tag when authorized; run the tagged whole-assignment smoke check and produce final `verification.json`. This Part 4 fragment does not claim those tasks are complete.
