# Homework 2 submission evidence

The application is extended in the repository's shared `code/` and `src/` folders. Its frontend is in `code/web_application/static/`, and its Part 2 FastAPI backend is in `code/web_application/main.py`. See the [web app instructions](../../code/web_application/README.md) for setup, API behavior, and verification.

This directory is reserved for the assignment-required `RUN_LOG.txt`, `METRICS.md`, `AI_USE.md`, `report.pdf`, `verification.json`, raw evidence, and reproducible run instructions. Those deliverables are not complete yet. For each numbered question, place the relevant code excerpt immediately above its corresponding output screenshot in the final report; input screenshots are supplementary.

Parts 1, 2, 3, and 4 are implemented. The implementation plans and detailed screenshot guides remain outside Git in `../../../HW2/agent_outputs/`, relative to this directory. Use `SCREENSHOT_EVIDENCE_PLAN.md` for Part 1 and `PART2_SCREENSHOT_EVIDENCE_PLAN.md` for Part 2. Parts 1 and 2 still need final report screenshots; Part 3's recorded evidence is linked below. Only actual submission evidence belongs here.

## Part 3 graph and evidence

The [Part 3 guide](../../docs/agent_graph.md) explains the Planner/Reviewer graph and how to run it with the shared local-model adapter. From the repository root, with the agent environment prepared and Ollama running:

```bash
.venv-agents/bin/python code/agents_graph.py --input-json reports/hw02/cases/part3_listing.json
```

- [Implementation results and screenshot index](PART3_IMPLEMENTATION.md)
- [Part 3 verification fragment](verification_part3.json)
- [Run log](RUN_LOG_PART3.txt)
- [Raw runs and test evidence](raw/part3/)
- [Code and recorded-output screenshots](screenshots/part3/)

The verification fragment covers historical Part 3 only. The combined verification result and final HW2 report and submission tag remain pending.

## Part 4 schema and measured loop safety

The shared graph now applies the Pydantic contract and bounded validation repair. All 75 real measured trials are retained in one frozen campaign: 30 schema trials, 20 at each ceiling, and five adversarial trials.

- [Part 4 implementation, outcomes, and screenshot index](PART4_IMPLEMENTATION.md)
- [Required tables and deployment-ceiling recommendation](METRICS.md)
- [Deployment choice JSON](deployment_choice.json)
- [Part 4 offline verification](verification_part4.json)
- [Part 4 run transcript](RUN_LOG_PART4.txt) and [combined-log integration index](RUN_LOG.txt)
- [Frozen campaign and raw evidence](raw/part4/20260914T0610-baseline/)
- [Reproducible run instructions](REPRODUCIBLE_RUN_INSTRUCTIONS.md)

The Part 4 verifier does not replace the required final tagged whole-assignment `verification.json`. Historical Part 3 raw files and timestamps are preserved.
