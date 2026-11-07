# Homework 9 Part 4 · Rental answering and evaluation

Pragya Apurva · DATA 260 · SID4 6102

The Answering Agent sends the question, requested fields, and the listing's source export to local Ollama through the HW8 adapter. The Evaluator Agent compares the returned JSON fields and types with the corresponding canonical facts. It returns `PASS` or `REVISE`, an explanation, and feedback with the correct value for fields that need repair. The feedback and previous answer go back to the model for one revision. A second `REVISE` is returned as the final result.

The synthetic source export has two unlabeled inventory buckets. The scoped lesson tells the answering model how to read the immediate-availability bucket, including zero, when the requested fields include `available_units`. The training run stages and reloads the lesson before validation. Validation compares the same questions and the same repair settings with the lesson off and on. The gate checks expected lesson scope, targeted first answers, previously correct final answers, and new unsupported claims in unrelated questions. See the paired outcomes and training trace for the actual decision.

Each variant starts with a fresh answering client and its own lesson snapshot. All use the same canonical scorer offline. The end-to-end timer includes model generation, lesson selection, in-loop scoring and repair where enabled, and final response formatting. It excludes the single warm-up and offline scoring. The experiment calls Ollama directly, bypassing the semantic cache, Kafka, and the web application.

## Evidence

- [Reference facts](data/rental_reference.json) and input-only splits [training](data/training_data.json), [validation](data/validation_data.json), and [test](data/test_data.json)
- [Dataset checksums](dataset_hashes.sha256), [configuration freeze](freeze.json), and [freeze digest](freeze.sha256)
- [Training, repair, stop and reuse traces](development.json), [approved lessons](lessons.json), and [paired validation](validation.json)
- [Measured outcomes](held_out_results.json), [timing audit](timing_audit.json), and [results and report notes](METRICS.md)
- [Both agent snippets](agent_snippets.md), [terminal capture](terminal_evidence.png), and [run log](RUN_LOG.txt)

## Reproduce

From the repository root, use Python 3.12 with `requirements-hw08.lock.txt` and the installed local Ollama model `qwen2.5:7b` at `127.0.0.1:11434`. Work from a commit that includes the input splits. Choose a fresh external output directory and run both phases serially with an exclusive model window.

```bash
python scripts/hw09/part4_agents.py develop --output "$HW9_PART4_OUTPUT"
python scripts/hw09/part4_agents.py test --output "$HW9_PART4_OUTPUT"
python -m pytest -q tests/test_hw09_agents.py
```

Development checks the committed Git blob identifier for the held-out file. The test command verifies the freeze receipt, code, model and lesson state before reading that file, then checks the committed blob and records its SHA-256. The held-out questions were authored as distinct synthetic fixtures alongside the other splits. The live runner first read their contents after the freeze.

The Evaluator Agent is a deterministic reference checker. Inputs include requested field names, and answers use JSON fields. This confines scoring to explicit claims. Held-out reuse increments are recorded in each variant's runtime trace, while the persisted lesson snapshot stays frozen. The source code was pinned at `7767adc8fdc4afa8ba2157ea9ecda15f41162266` before live development.

The focused regression suite passed 42 checks. Repository-configured lint, explicit Part 4 lint and formatting passed. Broader-suite collection requires the earlier assignments' `langgraph`, `llama_index`, `numpy`, `mcp`, and `jsonschema` dependencies. See [verification.json](verification.json) for the recorded coverage and [AI-use evidence](AI_USE.md) for the assistance disclosure.
