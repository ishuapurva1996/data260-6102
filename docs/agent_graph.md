# Planner–Reviewer graph (HW2 Part 3)

The graph turns listing text into three topical tags and a summary of at most
25 whitespace-separated words. A Planner proposes metadata; a Reviewer critiques
that proposal; Python decides whether to accept it, request a revision, retry a
malformed response, or stop. It calls the existing local Ollama adapter in
`src/model_client.py` and does not require the Part 2 API server.

## Run it

From the repository root, use a separate agent environment with Python 3.11 or 3.12:

```sh
python3.12 -m venv .venv-agents
source .venv-agents/bin/activate
python -m pip install -r requirements-agents.txt
ollama serve
```

Run `ollama serve` in a separate terminal if Ollama is not already running. The
recorded HW1 substitute model is `qwen3:1.7b`; check it with `ollama list` and use
`ollama pull qwen3:1.7b` if it is missing. No model download is part of graph execution.

```sh
python code/agents_graph.py \
  --input-json reports/hw02/cases/part3_listing.json \
  --evidence-dir reports/hw02/raw/part3
```

Or provide `--title "..." --content "..."` directly. Do not combine those with
`--input-json`. Optional `--email` is input metadata, not model context.
Use `python code/agents_graph.py --help` for the complete options.

Defaults are model `qwen3:1.7b`, temperature `0.0`, timeout `120` seconds per model
call, and `--max-turns 10`. Temperature zero reduces sampling variation but does
not guarantee repeatable text. A finite timeout stops a failed call; the turn
ceiling stops repeated model work.

The CLI streams readable progress to **stderr**, then emits exactly one terminal
JSON object on **stdout**. This lets another program parse the result while a
person watches the steps. Exit codes:

| Exit | Status | Meaning |
|---|---|---|
| 0 | `accepted` | Current valid proposal has a valid review with no issues. |
| 1 | `turn_limit` | Budget exhausted; draft is diagnostic, not approved output. |
| 2 | `error` | Invalid configuration, model/service error, internal error, or failed evidence capture. |

`final_output` contains accepted metadata only. An unsuccessful run retains its
latest proposal, feedback, revision, and error for diagnosis.

## What changed from HW1

The sequential entry point, `code/agents_demo.py`, always calls Planner followed
by Reviewer. Its final Python processing can repair or replace metadata. The graph
keeps the same adapter but makes the decision after each worker explicit. It never
silently shortens a summary, invents tags, strips Markdown fences, or treats a
missing review as approval.

```mermaid
flowchart TD
    Start([START]) --> S[Supervisor: count completed worker; decide status]
    S -->|needs draft or revision| P[Planner]
    S -->|draft needs review| R[Reviewer]
    P --> S
    R --> S
    S -->|accepted, ceiling, or error| End([END])
```

`AgentState` is a `TypedDict` representing the current run: original input, runtime
adapter, current draft, review, revision IDs, retry context, counters, status, and
trace. LangGraph merges the partial updates returned by each node. Nodes replace
lists and dictionaries instead of mutating the incoming state. Each run starts
with fresh state; the adapter is never serialized or checkpointed.

The **supervisor** performs bookkeeping and decides terminal status. The pure
`router_logic` function chooses the next edge from that state. The supervisor
does not make a model call. This follows LangGraph's
[state, node, and edge model](https://docs.langchain.com/oss/python/langgraph/graph-api).

## One turn means one worker execution

A Planner execution is one turn. A Reviewer execution is another turn. An initial
supervisor visit and later routing visits consume no turns. Each worker marks its
attempt pending; the next supervisor consumes that marker exactly once.

| Ceiling | Example worker sequence | Result |
|---|---|---|
| 1 | Planner | Unreviewed draft; `turn_limit`. |
| 2 | Planner → Reviewer accepts | `accepted` on the last allowed turn. |
| 2 | Planner → Reviewer rejects | `turn_limit`. |
| 3 | Planner → Reviewer rejects → Planner | Revised draft remains unreviewed. |
| 4 | Planner → Reviewer rejects → Planner → Reviewer accepts | `accepted`. |
| 10 | Five rejected draft/review pairs | `turn_limit`. |

Malformed responses can cause consecutive calls to the same worker. Ten turns
therefore allow **at most** five complete pairs. LangGraph's recursion limit counts
graph steps, including supervisor visits; it is set above the worker budget so
ordinary exhaustion ends normally rather than raising a recursion exception.

The supervisor checks fatal error first, current acceptance second, and ceiling
third. A valid approval on the last allowed turn is still successful.

## Response contracts and retries

Planner JSON:

```json
{"tags": ["Apartment", "Transit", "Pet friendly"], "summary": "Two-bedroom apartment near downtown San Jose with laundry, parking, pet-friendly policies, and light rail access."}
```

Reviewer JSON:

```json
{"issues": ["The summary claims a balcony that the listing never mentions."]}
```

An empty `issues` array approves the current proposal. A Reviewer can supply a
short `message`, but cannot substitute new tags or a replacement summary. The
Planner revises using the previous draft and critique. No private reasoning is
required in either response.

`contracts.py` validates the entire JSON response. A Planner must supply exactly
three nonblank strings and a nonblank summary of no more than 25 words. A
malformed Planner response retries Planner with the parsing feedback; a malformed
Reviewer response retries Reviewer on the same proposal. This is content retry,
not an unbounded transport retry.

Every Planner attempt advances `proposal_revision` and invalidates the old review,
including attempts whose JSON is malformed. Acceptance requires
`reviewed_revision == proposal_revision`. An old approval can never approve a
new or failed draft. Service, timeout, and unexpected internal errors end the run.

Raw responses and usage are recorded before parsing. A rejected response still
counts as work. A transport failure consumes a worker attempt but may produce no
adapter response or token counts. Missing usage metadata can be normalized to zero
by the shared adapter; zero reported tokens do not prove the call was free.

## Demonstrate the feedback loop

```sh
python code/agents_graph.py \
  --input-json reports/hw02/cases/part3_listing.json \
  --max-turns 10 --controlled-reviewer \
  --evidence-dir reports/hw02/raw/part3
```

This explicitly labeled demonstration still calls the real Reviewer. After a
valid review, it appends a forced issue so Planner must revise. The raw model
response stays unchanged in the trace, and the simulation is recorded separately.
It defaults off. Expected exit code **1** proves normal bounded termination; it
does not mean the demo produced approved metadata. Malformed model responses are
recorded honestly and may interrupt the alternating pattern.

## Tests and evidence

```sh
python -m unittest discover -s tests/agent_graph -v
python scripts/verify_part3.py --live
```

Unit tests use scripted adapters through the actual compiled graph. They cover
turn boundaries, revision safety, malformed output, retry context, transport
errors, state isolation, usage accounting, and CLI behavior without model wording
assertions. The live verifier runs an ordinary case and the controlled ceiling
case, preserving separate stdout, stderr, result JSON, and structured trace.

The verifier writes `reports/hw02/verification_part3.json` and
`reports/hw02/RUN_LOG_PART3.txt`; each CLI run gets a unique folder in
`reports/hw02/raw/part3/`. The records include resolved model settings, timestamps,
observed Git commit, dirty-tree status, and dependency versions. The assignment's
SID/seed fields are identity metadata; the verifier does not claim to have seeded
the model. `--live` is required for real-model checks; offline success alone does
not establish live acceptance. Use `--output-dir` to keep another verification run
separate from the checked-in evidence.

Part 4's Pydantic output schemas, tag character limits, repeated-run comparison,
adversarial evaluation, and final combined report/tag remain separate work.
`contracts.py` is the replacement point for that stricter output validation.
Part 3 neither edits the web app nor depends on Part 2's endpoints. Application
code remains in shared root-level folders; assignment evidence is grouped under
`reports/hw02/`. The implementation plan remains outside this Git repository.
