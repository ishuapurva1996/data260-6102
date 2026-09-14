# HW2 Part 3 implementation and evidence

Implemented on September 13, 2026 (America/Los_Angeles). The recorded UTC run
timestamps fall on September 14. The graph is runnable from the shared repository
and reuses `src/model_client.py`. No Part 2 API server is required.

## Run from the existing checkout

An ignored `.venv-agents/` environment has been created with Python 3.12.14 and the
dependencies in `requirements-agents.txt`.

```sh
cd "/Users/pragyaapurva/Documents/SJSU/DATA 260/data260-6102"
.venv-agents/bin/python code/agents_graph.py \
  --input-json reports/hw02/cases/part3_listing.json \
  --evidence-dir reports/hw02/raw/part3
```

Ollama must be running with `qwen3:1.7b` available. The implementation session
started the existing local Ollama service and verified that model. Instructions
for rebuilding the environment, options, and graph behavior are in
[the agent guide](../../docs/agent_graph.md).

## Implemented behavior

| Responsibility | Implementation |
|---|---|
| Fresh typed state, inputs, counters, draft/review revisions | `src/agent_graph/state.py` |
| Strict whole-response JSON contracts | `src/agent_graph/contracts.py` |
| Planner and Reviewer calls through the shared adapter; raw output and usage capture | `src/agent_graph/nodes.py` |
| Supervisor counting and terminal precedence | `supervisor_node` in `src/agent_graph/nodes.py` |
| Pure next-node selection | `src/agent_graph/router.py` |
| Compiled LangGraph topology and separate recursion allowance | `src/agent_graph/workflow.py` |
| Single streamed run, readable diagnostics, terminal JSON, atomic evidence saving | `code/agents_graph.py` |
| Scoped offline/live verification | `scripts/verify_part3.py` |

One turn is one Planner or Reviewer execution. A draft is accepted only when its
current revision has a valid review with no issues. Malformed responses become
retry feedback; the graph does not silently repair the metadata. Service failures
stop with `error`. Approval on the last allowed turn succeeds; otherwise budget
exhaustion returns `turn_limit` and `final_output: null`.

## Verified results

The final Part 3 suite ran **51 tests, all passing**. It exercises the actual
compiled graph with scripted adapters, including state isolation, odd/even limits,
stale-review invalidation, malformed output, transport failures, exact CLI exit
codes, stdout/stderr separation, and evidence-save failures. The existing HW1
suite ran **46 tests successfully, with one skipped**. Dependency checking passed.
Independent local correctness review found no actionable defects and additionally
checked final-turn approval, final-turn timeout, and malformed controlled review.

| Real local-model case | Outcome | Worker turns | Reported tokens | Graph run time |
|---|---|---:|---:|---:|
| Ordinary listing | `accepted`, exit 0 | 2 | 580 | 3,663.402 ms |
| Controlled always-issue Reviewer | `turn_limit`, exit 1 | 10 | 3,280 | 7,177.313 ms |

Both used `qwen3:1.7b`, temperature 0.0, timeout 120 seconds, JSON format,
reasoning disabled, and ceiling 10. Each reported run came from exactly one
streamed graph execution. A warm local model and prompt caching can affect
timings; these two cases are functional checks, not a benchmark or failure-rate
estimate.

The ordinary case returned:

```json
{
  "tags": ["apartment", "downtown", "pet-friendly"],
  "summary": "Modern two-bedroom apartment near downtown San Jose with in-unit laundry and light rail access."
}
```

In the controlled case, every real Reviewer response was valid. The demonstration
then appended a clearly labeled forced issue, causing five Planner/Reviewer pairs
and normal termination at turn 10. The raw Reviewer text is preserved separately
from the effective parsed review containing the forced issue. This is simulated
rejection evidence, not a natural model-quality failure.

## Evidence inventory

- [Ordinary result](raw/part3/20260914T044444-c467a8e18f/result.json), with sibling
  `stdout.json`, `stderr.txt`, and `events.json`.
- [Controlled result](raw/part3/20260914T044448-5dc5aad616/result.json), with the same
  sibling evidence files.
- [Verification fragment](verification_part3.json) and [combined Part 3 run log](RUN_LOG_PART3.txt).
- [Final Part 3 tests](raw/part3/final-tests.txt) and [HW1 regression log](raw/part3/hw1-regression.txt).
- [Installed dependencies](raw/part3/environment.txt) and [implementation SHA-256 hashes](raw/part3/source-sha256.json).
- [State and contract screenshot](screenshots/part3/01-state.jpg),
  [graph/supervisor screenshot](screenshots/part3/02-routing.jpg),
  [ordinary output screenshot](screenshots/part3/03-ordinary_model_run.jpg), and
  [controlled output screenshot](screenshots/part3/04-controlled_loop.jpg).

The JPEGs are browser screenshots of the corresponding local HTML evidence pages.
Code excerpts were read from the actual source; console text was read from the
saved stderr files. They are labeled as rendered recorded output, not native
Terminal captures. The native Terminal surface was unavailable to the capture
tool. The source HTML remains alongside each image for inspection.

The live evidence records observed commit
`42f1e1952072f5b6f93e7ac53eda7571cffcd6ac` and a **dirty working tree**. New Part 3
implementation files were uncommitted at capture time; the commit alone therefore
does not identify their contents. The source hashes identify the final runtime
files. The final verifier revalidated both saved live runs after its small cleanup
without executing the model again. SID4 6102, SEED 6102, and VERIFY_SEED 266102 are
assignment identity metadata, not claims that model generation was seeded.

## Scope and next integration

Part 3 owns its new graph package, CLI, dependency manifest, test subtree, guide,
and evidence. Part 2 was being implemented concurrently in the same checkout when
this evidence was captured; Part 3 was still uncommitted. The external implementation plan
remains under the workspace-level `HW2/agent_outputs/` directory outside Git.

The implementation is ready for use. Part 4 still needs its Pydantic schemas,
tag-length rule, repeated ceiling experiments, and adversarial evaluation. The
final HW2 report, combined verification, and submission tag should be assembled
after the other parts are complete. Merge this Part 3 verification fragment with
the backend's evidence at that stage; do not treat it as the complete HW2 result.
