# HW6 Part 3 reproducible experiment

This directory contains the frozen study inputs and reproducible project tools.
Preparation uses offline engineering fixtures. It supplies no measured model
results. Run live comparisons only after the later user measurement prompt and
A's integrated gate. The foundation readiness file alone is insufficient.

## Frozen design

`conversation.json` contains the actual **30 submitted user messages**. Each
normally receives one assistant reply, so the stored history normally contains
60 records before probing. The five additional questions in root
`memory_probes.yaml` are probes, not primary turns. N counts previous stored user
and assistant records, excluding the current message. A complete study makes
120 primary and 20 probe requests, plus separately logged auxiliary calls.

All facts are synthetic. Willow Glen is introduced at turn 2, the indoor cat
Juniper at turn 3, January 15, 2027 at turn 4, the $2,200-to-$2,400 correction
at turn 12, and step-free access with a conditional working elevator at turn 16.
Turns 26-30 request neutral organizational advice and discourage profile recaps.
The model can still repeat facts in its own replies; retain those replies rather
than editing them. Each probe's exact source quotations, essential facts, full
credit criteria, minor omissions, and 1-5 scoring rules are frozen in the YAML.
Never change expectations in response to measured answers. A design change
requires a new freeze and a new complete study, preserving the previous attempt.

Conditions in fixed order: A=N4 baseline, B=N12 baseline, C=N30 baseline,
D=N12 token-budget eviction. D starts with at most 12 previous records and removes
the oldest whole record until `count_tokens(render_window(retained)) <= 160`.
The injected Qwen counter counts each whole rendered block; message token counts
are not added together. Retained ordering is unchanged. An oversized newest
record leaves an empty window. The current message is appended separately by C.
The selector performs no persistence, summarization, or episode deletion.

Each condition constructs a fresh integrated app with immutable `HW6Config`,
fresh owner-prefixed user and session IDs, and the same other settings. Seed 6102
is passed by A's generation adapter; verify seed 266102 is recorded, not used as
a claim of deterministic model output. No random conversation is generated.
There is no explicit warm-up in any condition. The preceding unscored context
pilot and fixed condition order can affect cache/warm-start latency; report that
limitation. Probes and pilot work are excluded from production projections.

The live path uses **sequential probes in frozen order** because the published C
storage contract has no complete snapshot/clone API. Earlier probes and answers
persist and can affect later summaries, episodes and recall. The manifest states
this limitation. An injected `ProbeIsolation` can instead capture all three
collections after turn 30 and clone the same snapshot into fresh namespaces for
each probe, remapping every ID/reference. The truncated `/api/memory` inspection
response is not a complete snapshot and must never be used for cloning.

## Integration boundary and gate

Run modules from the repository root with A's pinned Python environment. No new
dependency is needed. A owns MongoDB/SQL, shared configuration, `create_app`, the
config endpoint and the final acceptance pass. C owns memory and telemetry.
`serve.py` launches the actual existing integrated app through A's published
`create_app(hw6_config=..., hw6_window_policy=..., hw6_telemetry=...)` injections.
It does not implement an alternate chat API. A injects the D function
`src.hw06_experiments.policy.token_budget_window`; baseline gets `None`.

The authenticated `/api/hw06/config` must return `config.public_dict()` either
directly or as `{"config": public_config, "source_commit": actual_revision}`.
The public config must include the actual `source_commit`. Every C event must
carry that config (additional nonsecret facts are allowed), the same request
context, and `hw06.v1` fields. The runner checks one chat event, one extraction
and one query embedding per completed request, scheduled primary summaries,
reported usage, selected window text, signed component residuals and identities.
Additional fact embeddings and lifetime summaries are preserved separately.

A's later gate must include these fields (a specification, not a ready receipt):

```json
{
  "live_integrated_ready": true,
  "source_commit": "actual integrated HEAD",
  "source_sha256": "source_state()['source_sha256']",
  "input_hashes": {"scripts/hw06/part3/conversation.json": "sha256", "memory_probes.yaml": "sha256"},
  "config_sha256": "digest of the baseline N12 public config with actual source_commit",
  "file_memory_enabled": false,
  "pilot": {"n30_context_fit": true, "no_prompt_truncation": true}
}
```

`source_state()` hashes tracked source/configuration paths including the lockfile;
it requires those paths clean. `load_design()[2]` supplies exact input hashes and
`design.digest(config.public_dict())` supplies the configuration hash. If the
N30 pilot needs more context, A must change it uniformly, refreeze, and restart.
The live runner checks installed model digests before and after the study and
source/input hashes after it. The whole study reserves A's canonical runtime
lease, including child server lifetimes, with no nested acquisition. It refuses
an occupied port 8702 and stops only its own child. Other roles must suspend
model jobs, embeddings and shared database writes for the whole window.

## Later live invocation

The following is an invocation template, **not a command run during preparation**.
Use real paths and the authenticated principal's ID. Put login credentials in a
private environment file under `HW6_EXPERIMENT_EMAIL` and
`HW6_EXPERIMENT_PASSWORD`; never put them on the command line or in evidence.
Pass legacy SQL/auth env first, HW6 env second. TLS verifies a certificate valid
for 127.0.0.1 using the supplied CA. Use a new external output directory for
every attempt. Promote only reviewed final evidence into `reports/hw06/raw/part3`.

```bash
python -B -m scripts.hw06.part3.run --measurement-authorized \
  --gate /absolute/integrated-gate.json --output /absolute/new-study-directory \
  --runtime-dir /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime \
  --env-file /absolute/legacy-app.env --env-file /absolute/hw06.env \
  --cert /absolute/cert.pem --key /absolute/key.pem --ca /absolute/ca.pem \
  --owner-id AUTHENTICATED_PRINCIPAL_ID
python -B -m scripts.hw06.part3.export validate --study /absolute/new-study-directory
python -B -m scripts.hw06.part3.export scoring-template \
  --study /absolute/new-study-directory --output /absolute/scores.json
# Manually assess all criteria and fill scores, explanations, scorer and UTC timestamp.
python -B -m scripts.hw06.part3.export metrics \
  --study /absolute/new-study-directory --scores /absolute/scores.json \
  --output /absolute/new-metrics-directory
```

## Raw data, scoring and metrics

The manifest saves source/config/lock/input hashes and complete condition
settings. Each condition retains launch/server config, private server console
log, `attempts.jsonl` written before requests, `requests.jsonl` with actual replies,
HTTP elapsed latency and real public errors, and C's `events.jsonl`. No retries
are hidden. A failed request aborts the study, records an incomplete manifest,
and keeps every existing file; rerun in fresh namespaces and a new directory.
Missing usage, auxiliary failures, orphan/duplicate events, configuration drift,
unfinished calls and missing postflight prevent a complete measured export.

Component counts are model-tokenizer estimates of actual selected blocks, not
reported prompt totals. The export command recomputes them with the frozen Qwen
tokenizer. `template_residual` is reported prompt tokens minus the six estimates
and can be negative. Embedding work has null generation counts and stays separate.
File-memory injection is disabled by the integrated gate; the runner never loads
AGENT.md or MEMORY.md into prompts (their source hashes only detect source drift).

The scoring sheet copies each actual answer, its hash, frozen expectations,
rubric and each criterion. A human assigns `correct`, `missing` or `incorrect`
with a reason for every criterion, plus a 1-5 score and overall explanation.
The evaluator cannot rewrite answers or criteria. Incorrect essential facts score
at most 2, missing essential facts at most 3, and 5 requires every criterion.
The exact-date question has no score-4 minor omission. Scoring is manual; no
unvalidated model judge is used.

Exports include a required four-row CSV/Markdown table (also mean completion
tokens), metrics JSON with policy comparison and best/worst selection, all scores
and explanations, per-turn component CSV, and separate auxiliary-generation and
embedding JSON. Primary means and cost totals use exactly 30 turns; quality uses
exactly five probes. D savings = `100*(B_prompt_total-D_prompt_total)/B_prompt_total`;
quality change = `D_mean_quality-B_mean_quality`. Zero baseline prompts make
savings undefined, explicitly represented as null with a reason.

Assigned hypothetical prices are $1/million input and $5/million output. For
one 30-turn conversation with prompt total P and completion total O,
`10000*(P+5*O)/1000000` is the projected dollar cost. Decimal arithmetic produces
both main-chat and main-plus-generative-memory estimates. Extraction and session/
lifetime summarization enter the latter. Probes, warmups and pilot work enter
neither. Embedding calls/input counts/latency are reported without a price.
Best is the lowest main-plus-generative-memory cost with mean quality >=4 and
no incorrect essential fact. Worst is the highest such cost among complete
settings. Ties use A,B,C,D order. No qualifying setting yields an explicit null
best; the lowest-quality setting is also identified. Fixture studies cannot
export measured result tables.
