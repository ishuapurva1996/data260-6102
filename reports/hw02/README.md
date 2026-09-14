# Homework 2 submission evidence

The application is extended in the repository's shared `code/` and `src/` folders. Its frontend is in `code/web_application/static/`, and its Part 2 FastAPI backend is in `code/web_application/main.py`. See the [web app instructions](../../code/web_application/README.md) for setup, API behavior, and verification.

This directory is reserved for the assignment-required `RUN_LOG.txt`, `METRICS.md`, `AI_USE.md`, `report.pdf`, `verification.json`, raw evidence, and reproducible run instructions. Those deliverables are not complete yet. For each numbered question, place the relevant code excerpt immediately above its corresponding output screenshot in the final report; input screenshots are supplementary.

Parts 1, 2, and 3 are implemented. The implementation plans and detailed screenshot guides remain outside Git in `../../../HW2/agent_outputs/`, relative to this directory. Use `SCREENSHOT_EVIDENCE_PLAN.md` for Part 1 and `PART2_SCREENSHOT_EVIDENCE_PLAN.md` for Part 2. Parts 1 and 2 still need final report screenshots; Part 3's recorded evidence is linked below. Only actual submission evidence belongs here.

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

The verification fragment covers Part 3 only. Part 4 experiments, the combined verification result, and the final HW2 report and submission tag remain pending.
