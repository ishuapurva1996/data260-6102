# HW2 reproducible run instructions: Part 4 contribution

Run commands from the repository root. This guide covers the shared Planner–Reviewer
graph and Part 4 experiments. See the [graph guide](../../docs/agent_graph.md) for
contracts and routing, and the [web app guide](../../code/web_application/README.md)
for Parts 1–2. Integration into the final combined Parts 1–4 instructions remains
pending.

## Environment and fast checks

Use Python 3.11 or 3.12 and a separate agent environment. The recorded campaign
used Python 3.12.14 on macOS arm64; exact package versions, platform information,
and model metadata are saved in its manifest and environment snapshot.

```sh
python3.12 -m venv .venv-agents
source .venv-agents/bin/activate
python -m pip install -r requirements-agents.txt
python -m pip check
python -m unittest discover -s tests/agent_graph -v
```

The suite uses Python's built-in `unittest` and scripted adapters; it makes no
model calls and does not require `pytest`. Requirements pin Pydantic 2.13.5,
LangGraph 1.2.11, and langchain-ollama 1.1.0. Do not change packages or frozen source
files while a campaign is running or before resuming it.

For real runs, start `ollama serve` in another terminal if the service is not
already running. Check `ollama list`; run `ollama pull qwen3:1.7b` if the model is
missing, before preparing a campaign. Offline reporting and verification below
do not need a running Ollama service.

The baseline configuration is `qwen3:1.7b`, service
`http://localhost:11434`, temperature 0, 120-second timeout per model call, JSON
mode, reasoning disabled, and normal Reviewer. The shared adapter fixes context
size at `num_ctx=4096`. The manifest records the installed model digest and Ollama
version. `SEED=6102` and `VERIFY_SEED=266102` identify the assignment; neither is
supplied as a model RNG seed. Temperature zero does not guarantee identical text.

## Inspect and verify the recorded campaign offline

The preserved baseline is
[20260914T0610-baseline](raw/part4/20260914T0610-baseline/). Its manifest is the
authority for planned trials, frozen inputs, source/configuration fingerprints,
model identity, dependency versions, and observed Git state. The assignment
identity is HW2, SID4 6102, DOMAIN_ID 6 (rental housing), SEED 6102, and VERIFY_SEED
266102.

These commands make **zero model calls**:

```sh
source .venv-agents/bin/activate
python code/agents_experiments.py report \
  --campaign reports/hw02/raw/part4/20260914T0610-baseline
python scripts/report_part4.py \
  --campaign reports/hw02/raw/part4/20260914T0610-baseline \
  --report-dir reports/hw02
python scripts/verify_part4.py \
  --campaign reports/hw02/raw/part4/20260914T0610-baseline \
  --report-dir reports/hw02 \
  --output reports/hw02/verification_part4.json
```

`report` checks the frozen evidence and regenerates only the campaign's derived
`results.jsonl`, `results.csv`, and `summary.json`. It returns 0 for a complete
campaign, 1 for incomplete outcomes, and 2 for an integrity/processing error.
`scripts/report_part4.py` calls the same offline replay and formats the narrative
[METRICS.md](METRICS.md) and [deployment_choice.json](deployment_choice.json).
It preserves other parts' text outside the marked Part 4 section of METRICS.
The presentation utility was added after measurements; it records its own source
hash and generation timestamp separately in `presentation-provenance.json`,
without changing the frozen calculation-source fingerprint. No manual table
edits are needed. The verifier checks published table arithmetic and the decision
against raw evidence when `--report-dir` is supplied, including the recommendation's
campaign identity, manifest hash, evidence reference, and command ceiling.

The verifier writes the scoped [verification_part4.json](verification_part4.json),
with command, timestamp, identity, execution/verification Git state, source and
campaign fingerprints, individual checks, and overall pass/fail. Exit 0 means
all checks passed; exit 1 means a check failed. To keep the existing verification
timestamp, use `--output /tmp/data260-verification-part4.json` instead. Verification
does not repair application code or rewrite original campaign evidence.

Campaign-relative evidence references allow the entire campaign directory to be
copied to another checkout and inspected using its new `--campaign` path.
Historical absolute paths are observed metadata only. Preserved `sources/` files
are audit snapshots, not a second application to execute. Historical replay
checks stored source hashes and records without requiring current checkout source
bytes to equal the old snapshots. Actual execution/resume requires the current
source, environment, installed model, inputs, and configuration to match the
frozen campaign.

The baseline's original source snapshots remain authoritative for its 75 measured
runs. After measurement, changes to `code/agents_experiments.py` and
`scripts/verify_part4.py` hardened failure handling and recommendation provenance.
The graph, schema, prompts, shared adapter, and calculation rules were unchanged.
The current tools can replay and verify the existing evidence offline. They cannot
resume execution against that baseline when current source hashes differ from
its frozen hashes; use a new campaign for further measurements.

## Start a new real-model campaign (expensive)

Choose a **new** campaign directory. The following unique-name example preserves
the recorded baseline; a concrete alternative would be
`reports/hw02/raw/part4/20260915T120000-reproduction`, only if that directory does
not already exist. `prepare` refuses an existing directory.

```sh
source .venv-agents/bin/activate
PART4_CAMPAIGN="reports/hw02/raw/part4/$(date -u +%Y%m%dT%H%M%S)-reproduction"
python code/agents_experiments.py prepare \
  --campaign "$PART4_CAMPAIGN" \
  --schema-input reports/hw02/cases/schema_input.json \
  --adversarial-input reports/hw02/cases/adversarial_input.json
python code/agents_experiments.py run --campaign "$PART4_CAMPAIGN"
python code/agents_experiments.py report --campaign "$PART4_CAMPAIGN"
python scripts/verify_part4.py \
  --campaign "$PART4_CAMPAIGN" \
  --output /tmp/data260-part4-reproduction-verification.json
```

`prepare` queries installed-model metadata but does not generate text. `run` is
the expensive step: it saves an excluded ordinary warm-up and then executes
75 measured trials sequentially with fresh processes, state, and adapters. Avoid
other concurrent model workloads. Normal Ollama caching and model residency are
retained. A full campaign can take many minutes; each worker call has its own
120-second timeout, and the runner's outer deadline allows ceiling × timeout
plus 90 seconds of process/evidence overhead.

| Measured cohort | Runs | Frozen input | Turn ceiling |
|---|---:|---|---:|
| Schema/retry distribution | 30 | Ordinary schema input | 10 |
| Short-ceiling comparison | 20 | The same ordinary input | 2 |
| Long-ceiling comparison | 20 | The same ordinary input | 10 |
| Adversarial | 5 | One distinct adversarial input | 10 |

The first 30 trials and the 20 long-ceiling trials are distinct runs. After the
30 schema trials, 20 comparison pairs alternate order: odd pairs run ceiling 2
then 10; even pairs run 10 then 2. The five adversarial trials run last. The
baseline used no adversarial pilots. Measured trials cannot use
`--controlled-reviewer`, fabricated results, or forced validation failures.

The new campaign has its own observed outcomes and must not be pooled with the
baseline. The final verification command above checks its raw/derived evidence;
it deliberately omits `--report-dir` because the existing report describes the
recorded baseline. To format and verify a separate campaign analysis, use a new
report directory:

```sh
PART4_REPORT_DIR="/tmp/$(basename "$PART4_CAMPAIGN")-report"
python scripts/report_part4.py \
  --campaign "$PART4_CAMPAIGN" --report-dir "$PART4_REPORT_DIR"
python scripts/verify_part4.py \
  --campaign "$PART4_CAMPAIGN" --report-dir "$PART4_REPORT_DIR" \
  --output "$PART4_REPORT_DIR/verification_part4.json"
```

## Definitions and interpretation

One turn is one Planner **or** Reviewer execution; supervisor bookkeeping uses
no turns. A normal pair takes two turns. A run completes only when the current
schema-valid proposal has a matching Reviewer approval and status `accepted`.
An approval on the last allowed turn succeeds. An unreviewed valid draft at the
ceiling has status `turn_limit`, with no `final_output`.

Planner retries equal Planner attempts minus one. The required 30-run table
groups terminal acceptance after one, two, or at least three Planner attempts as
“Valid first attempt,” “Valid after 1 retry,” and “Valid after 2+ retries.” All
normal ceiling exits enter “Hit turn ceiling,” even if an earlier draft passed
the schema. Errors and interrupted/unknown trials are reported separately.
First-schema-valid attempt, schema failure count, Planner/Reviewer attempts,
issues across valid reviews, and retries caused by malformed Reviewer output
are recorded separately. A content revision can count as one Planner retry while
having zero schema failures.

Application-run latency is the CLI's `elapsed_ms`, including Git metadata
inspection, adapter construction, graph construction/execution, and trace
handling. It excludes process startup/imports and evidence writing. Subprocess
wall time and worker durations are separate fields. Each category's mean uses
the runs in that category; an empty category is N/A. Ceiling completion rate is
accepted / 20 × 100, and mean latency includes all 20 runs, including normal
ceiling exits. Calculations use stored times without further rounding until
display. Reported zero tokens may indicate missing usage metadata.

The deployment rule chooses higher observed completion rate, then lower all-run
mean application latency, then the smaller ceiling. See
[METRICS.md](METRICS.md) for actual counts, the chosen ceiling, and its explicit
graph command. The graph default remains 10; the recommendation does not modify
runtime defaults or deploy a website. It is limited to this model, input,
configuration, and sample. Adversarial evidence reports all five actual outcomes,
including a low ceiling rate if the case did not reliably trouble the graph.

## Preserve interruptions and historical evidence

The runner acquires exclusive ownership with `runner.lock` and creates each
trial's `started.json` before launching it. Each Git metadata command has a
five-second timeout, and metadata collection finishes before reserving a new trial
directory. A metadata failure therefore leaves that slot unstarted and launches
no graph process. The runner preserves process stdout/stderr,
terminal records, timestamps, return codes, and CLI traces. For each graph CLI
subprocess, exit 0 means accepted, 1 means ordinary ceiling exhaustion, and 2 means
an operational error. The campaign runner treats both content outcomes as normal
progress; it returns 0 after an uninterrupted batch, including a clean `--limit`
pause, and 2 on an integrity/operational error. A started
trial without a terminal record is interrupted/unknown, not a ceiling exit.

For a clean pause, `run --limit 5 --campaign "$PART4_CAMPAIGN"` executes at most
five pending measured trials and returns. A later ordinary `run` resumes only
never-started slots after checking all preserved warm-up evidence, then saves
another excluded warm-up. The full frozen conditions must still match. A
completed campaign is not run again.

A failed, unknown, or incomplete **excluded warm-up** also prevents resume into
measured slots. Preserve the entire campaign, diagnose the failure, and prepare
a new campaign. Do not replace the failed warm-up with a successful one or remove
its evidence to make verification pass. The same refusal applies when saved
warm-up evidence is invalid or tampered with.

Do not delete a failed trial, replace its ID, or restart an interrupted slot.
An error or unknown measured run prevents normal resume and a complete report.
Preserve that campaign, diagnose the problem, and use a new campaign if frozen
conditions must change or an execution remains unknown. Do not silently pool
campaigns. If a crash leaves `runner.lock`, inspect its PID and active process
before considering manual removal; the CLI will not take over a locked campaign.
Removing a stale lock does not make missing terminal evidence complete.

Historical Part 3 evidence, source hashes, timestamps, and run log remain under
[raw/part3](raw/part3/), [verification_part3.json](verification_part3.json), and
[RUN_LOG_PART3.txt](RUN_LOG_PART3.txt). The current Part 3 verifier imports the
stronger current validator. A fresh check must use a separate output directory:

```sh
python scripts/verify_part3.py --live \
  --output-dir /tmp/data260-part3-current-check
```

This live demonstration is separate from the 75 Part 4 measurements and should
run after any active measured campaign. Never run the Part 3 verifier into its
historical default output paths.

The Part 4 results and scoped verification are contributions to the final
submission. The full report PDF with matching code/output evidence, personal
AI-use answers, combined Parts 1–4 run log/instructions, final whole-assignment
`verification.json`, collaborator-access check, final HW2 tag, and tagged smoke
verification remain integration tasks. Reproduction does not require pushing,
tagging, or rewriting Git history. The implementation plan remains outside the
repository.
