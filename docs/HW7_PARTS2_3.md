# Hand-written rental agent and bounded Reflexion

Parts 2 and 3 extend `src/tool_agent`, the HW1 `complete(messages, tools=None)`
adapter and the three HW5 rental tools. They do not introduce a framework agent
or a separate application. See `reports/hw07/PARTS2_3.md` for measured results.

## Task execution

`run_agent(user_input)` sends native tool calls through the existing allowlisted
executor. Original native IDs are retained on assistant calls and matching
tool-role observations. Unknown tools and malformed/schema-invalid arguments
are rejected before execution. The model receives the specific sanitized error
and one correction opportunity for that operation. A second invalid correction
ends the attempt. Missing rental IDs remain ordinary useful tool errors; the
model can explain them instead of crashing.

The JSONL log records proposals, rejected inputs, repairs, every actual executor
invocation/result, per-response usage, the final answer, counters and stop reason.
Rejected proposals and successful tool executions are separate quantities.
The blocking model adapter preserves malformed provider arguments before the
Ollama decoder rejects them. Repair history uses a serializable empty argument
placeholder with the same call ID; original rejected arguments remain in logs.
Placeholders are never executed. The synchronous response hook buffers the
bounded response so final usage survives malformed early stream chunks.

For the fixed study tasks, pass `task=<frozen case>`. The deterministic verifier
requires the successful tool chain and supported public facts in the requested
JSON object. It rejects a plausible answer without the required calls. Ordinary
CLI conversations without a task verifier still return plain text.
Dependent A/C lookups must be proposed in a later model response than the search,
so guessed IDs in the same response cannot earn chain credit.

`run_reflexion(user_input, task=..., user_id=...)` checks the whole task after
each attempt. On a verification failure it stores a concise diagnostic with the
failed assertions and relevant observations, then retries with that diagnostic.
At most two retries are permitted. A single token/tool ledger spans the initial
attempt and retries. Final stop reasons are `success`, `budget_exhausted` and
`human_review`.

Reflections are deterministic, so writing one makes no additional model call.
They are untrusted run data, keyed by user/run/task/retry. No reflection is loaded
from a shared file or written into global instructions or memory. Original system
instructions, static tool permissions and the shared budget remain authoritative.

## Bounds and accounting

The experiment freezes eight model responses and eight executor invocations per
attempt, 24 executor invocations and 24,000 tokens across a Reflexion task, and a
finite 90-second timeout per model request. Repairs count within these limits.
Before each model call, the ledger reserves a conservative bound on the serialized
prompt plus output cap. The byte bound and pinned tokenizer estimate are recorded.
The full request must fit both the remaining total and model context.

Backend-reported input/output usage is charged after each response. Unknown usage
is shown as unavailable and charged at the entire conservative reservation; it
never becomes a zero-token measurement. An observed backend overrun is recorded
and blocks subsequent requests. Tool allowance is claimed before execution.

## Reproduce the study

Use the compatible HW7 Python environment and private configuration described
in `docs/HW7_PART1.md`. MySQL and local Ollama must be available. Hold the shared
runtime lease; do not run competing model experiments. The controlled fixture
adds one course manager and three rentals, preserving existing data. Its codes
follow the existing `S6102-R-<id>` contract.

```sh
python scripts/hw07/agent_cases.py --env-file "$HW7_ENV_FILE" \
  --runtime-dir "$SHARED_RUNTIME_DIR"
python scripts/hw07/agent_study.py pilot --env-file "$HW7_ENV_FILE" \
  --runtime-dir "$SHARED_RUNTIME_DIR" --context-window 16384 \
  --output "$FRESH_EXTERNAL_PILOT_DIR"
```

The existing `reports/hw07/cases/agent_tasks.json` freezes resolved IDs, prompts
and expected public outcomes. Replay refuses collisions or drift. Frozen
`experiment.json` records settings, schemas, source/input hashes and the paired
schedule. Do not silently overwrite a freeze or reuse a populated output folder.
Create a distinct study/version when changing any scored input.

With committed application source matching the freeze:

```sh
python scripts/hw07/agent_study.py scored --env-file "$HW7_ENV_FILE" \
  --runtime-dir "$SHARED_RUNTIME_DIR" --output "$FRESH_STUDY_OUTPUT_DIR"
python scripts/hw07/agent_metrics.py --study "$FRESH_STUDY_OUTPUT_DIR" \
  --audit "$INDEPENDENT_AUDIT_JSON"
```

The paired schedule runs seven repetitions of each A/B/C task in each mode.
Pair order alternates by repetition to reduce systematic warm-cache order
effects. Every model request uses seed 6102 and temperature 0. These repetitions
do not establish general reliability on unseen tasks.

`recovery` runs the nonexistent-ID demonstration. `controlled-fault` runs a
separate, explicitly unscored demonstration that increments B's first generated
count by one and lets the real model retry. It never alters scored output.
Both use the same CLI/env/lease/output arguments.
The missing-ID result is a typed JSON object containing only `rental_id` and
`found: false`, verified against the actual tool error. This avoids accepting an
unrelated error phrase followed by invented listing details.

Supply `--tokenizer /path/to/qwen2.5-tokenizer.json` when reproducing on another
machine. Its bytes must match the SHA-256 in the experiment freeze; the local
default reuses the existing HW6 runtime asset. Scored preflight also checks the
dependency-lock and tool-schema hashes. Install the pinned web requirements
before reproduction; the recorded lock hash does not inspect arbitrary packages
installed outside that environment.

After verification, `agent_cases.py --cleanup` removes only the frozen owned
fixtures. The saved inputs allow recreation at the same IDs when they are free;
any collision stops setup instead of overwriting a current record.

## Tests and interpretation

Run `tests/test_hw07_{budget,loop,verifier,reflexion,agent_metrics}.py` and the
existing tool/agent regression tests. These controlled-response proofs are
separate from real Ollama/MySQL measurements. The first-pass and post-repair
validity rates use the same denominator of original operation proposals. A repair
does not create a new denominator entry. A case with no proposal still counts in
task success/failure. Failure labels may overlap.

Unsupported factual fields are checked against the fixture and all successful
observations independently of chain completion. Missing required steps still
fail the task. Review rejected final answers independently for verifier false
rejections, including any answer outside the requested JSON format.

A retained backend overrun remains in the generated table with its real cost and
an explicit budget-violation flag. It fails the separate budget acceptance check;
it never causes a failed case to disappear from the denominator.
