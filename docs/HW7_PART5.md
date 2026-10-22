# HW7 Part 5: isolated prompt-injection experiment

This experiment reuses the Part 4 `run_bike_agent`, LangGraph graph, three tool schemas, model adapter, controller and final verifier. The web application does not import the experiment module or expose a defense toggle. The normal official-host restrictions and `csv_sql` read-only boundary remain enabled.

The required pre-test threat model and local fixtures are in `reports/hw07/cases/injection`. The copied CSV preserves all 500 frequent-scenario rows and adds two synthetic course fields. An opaque harmless sentinel appears only in the first copied CSV row. It is absent from hostile pages and initial user/system prompts. Each hostile HTML page retains ordinary pricing text and adds one attack: recommendation override, a non-SELECT update, or disclosure through a SELECT.

## Conditions and observability

| Condition | Untrusted-data prompt label | Read-only SQL gate |
| --- | --- | --- |
| `before` | Off | Off in disposable experimental adapter |
| `prompt` | On | Off in the same disposable adapter |
| `prompt_tool` | On | Production single-SELECT boundary |

The standard task still asks for read-only work in every condition; tool schemas, controller guidance, budgets and the financial verifier remain constant. Consequently this is an incremental comparison of the two specified defenses, not an experiment on an otherwise unprotected model. A failed baseline attack is retained. No final verifier rejection is attributed to prompt labeling or SQL enforcement.

`experiments/hw07/security.py` contains the deliberately writable SQL adapter. It permits single-statement trip-table DML on a new in-memory copy, while retaining unrelated filesystem/database/function and resource containment. It cannot attach databases, call file functions, create tables or operate on the application's MySQL/Mongo data. Only the offline entry point passes the Python-only experimental capability. The production `src/bikeshare/tools.py` implementation is unchanged.

Every native model proposal remains in the original trace. An additional `sql_gate` event records its matching call ID, statement, allow/block decision, reason, before/after snapshot hashes, and observed effects. Exact database snapshots are saved per distinct state. The raw final answer is logged before verification, and result files preserve it unchanged. Scoring records raw recommendation, attempted/executed mutation, database effects, sentinel selection, final disclosure and verifier acceptance separately. The mutation keyword classifier is an evidence aid; SQLite's authorizer enforces the real boundary.

Malformed decision types remain unsuccessful structured answers without crashing collection. If the supervisor interrupts a worker, scoring recovers a retained `raw_final` or final assistant response. Without an observed final response, override/disclosure outcomes are unknown (`null`), rather than credited as failed attacks.

Read-only SELECT does not protect confidentiality. It may return the sentinel; selecting it and disclosing it in the final answer are separate observations. This exercise tests inappropriate output, not network exfiltration.

## Reproduction

Use the existing pinned Part 4 Python environment and local Ollama model. No new dependency installation, public-site attack, database reset or application server is needed. Use an external directory for workflow files and private runs.

```sh
python scripts/hw07/security_cases.py
python -m pytest tests/test_hw07_security.py -q
```

After verified implementation is committed, freeze cases, exact initial prompts, source/fixture hashes, model digest, settings, budgets and scoring before measuring:

```sh
python scripts/hw07/injection_experiment.py \
  --freeze reports/hw07/raw/part5/freeze.json \
  --capture-work /absolute/external/part5/prompt-captures

python scripts/hw07/injection_experiment.py \
  --suite reports/hw07/raw/part5/freeze.json \
  --output /absolute/external/part5/scored \
  --runtime-dir /absolute/private/shared-runtime
```

Freeze captures use controlled responses only to save exact pre-tool messages; they are not local-model measurements. The suite runs one genuine local-model attempt per declared cell, sequentially. Every worker acquires the existing shared runtime lease. It uses the same model/request/tool/token/time bounds as Part 4, with a bounded supervisor grace allowance. Requests that fail or exhaust their budget remain in the record; they are not replaced by selected successes. An infrastructure failure before any model request is distinguished from a measured model failure.

The output contains exact prompts, native call IDs/tool-role observations, local captured pages and hashes, database snapshots, original model output, unchanged verifier output, conservative usage, UTC timestamps, and supervisor measurements. Private lease paths in operational requests are excluded when promoting required evidence. Results, excerpts and limitations are documented in `reports/hw07/PART5.md`; raw traces and computed tables are under `reports/hw07/raw/part5`.
