# Part 5 selected evidence

Pragya Apurva. U7/R14–R17 code, offline checks, five genuine local-model runs, and the 253-word reflection are ready for independent coordinator review. This is not completed homework submission or coordinator acceptance.

All selected scenario logs and authoritative checks name code commit `c7dc13ef214234fc0e34294b68e3cd74c76b2a73`. The later evidence-only commit adds this directory and `raw/part5/` without changing source. `tested-source-sha256.json` records source bytes for comparison. Earlier report evidence is preserved.

- `METRICS.md`: values derived from five terminal JSONL events, with exact run IDs and links.
- `REFLECTION.md`: trace of the real search-detail run; word-count receipt in raw evidence.
- `RUN_LOG.txt`: commands, exact exit codes, UTC timestamps, and genuine console output. The budget/optimization/intentional-failure nonzero exits are expected outcomes.
- `raw/part5/*.jsonl`: original model requests/responses, ordered executor requests/results, terminal events, code and configuration.
- `raw/part5/executor-demos.json`: genuine allowed omitted/false and blocked true calls; factory-construction counts. Separate from model prose.
- `raw/part5/mcp-current-tools-list.json` and `mcp-boundary.json`: current shared flag and real STDIO public-only behavior. Earlier schemas remain historical.
- `raw/part5/model-config.json`, `runtime-verification.json`, and `requirements-resolved.txt`: actual local model digest/configuration/packages and dedicated read-only fixture. Preparation receipts are explicitly labeled and precede the selected code evidence.
- `raw/part5/authoritative-tests.*`, offline outputs, and `verification.json`: 473 cases plus eight-case runner repeated twice, dependency check, and deliberate negative checks. JUnit synthetic DSN labels were redacted; original XML stays external and results are unchanged.
- `raw/part5/cleanup.json`: only positively owned MySQL3313/Ollama stopped, ports closed, fixture data retained.

Limitations: five synthetic scenarios are not a general success-rate estimate. Mock tests prove controlled behavior rather than live faults. One inherited MCP/Pydantic warning remains. Free-text descriptions are not comprehensively redacted. Screenshots are deferred and absent; final PDF, top-level consolidated metrics/reflection, verifier, tags, publication and submission belong to later finalization.
