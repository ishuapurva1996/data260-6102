# Homework 5 Part 5: bounded local rental agent

The agent uses the existing Ollama model adapter and exactly three rental tools:
`search_rentals`, `get_rental`, and `count_rentals`. Its tool descriptions and JSON
schemas come from `src/rental_tools/registry.py`. It does not add an agent
framework, SQL interface, database writes, or a hosted-model route.

## Privacy boundary

`GetRentalInput` adds the optional strict Boolean `include_contact`, defaulting
to `false`. Omitted/false requests retain public detail results. Strings, numbers,
null, invalid IDs, and additional properties remain validation errors.

The production `execute_tool` validates arguments first, then blocks valid
`get_rental` requests with `include_contact=true` before constructing a runtime
service or accessing an injected reader. It returns the usual JSON envelope:

```json
{"ok": false, "data": null, "error": "Safety block: rental submitter contact information is private."}
```

The agent stops on that specific error, without executing later calls in the
same response. Other tool errors remain available to the next model response.
A model's direct prose refusal is a normal model completion; it does not prove
that the executor policy ran. Direct allowed/blocked executor demonstrations
provide that separate evidence.

MCP invokes shared service handlers directly. Its additive flag is accepted,
but both true and false return the same public fields: MCP does not inherit the
executor's request-blocking policy. No contact retrieval is added. Public field
selection also does not comprehensively redact free-text listing descriptions.

## Python interface

```python
from src.tool_agent import run_agent

result = run_agent(
    "Count rentals for manager 1.",
    model_name="qwen2.5:7b",  # Use a locally installed tool-capable tag.
    max_steps=4,
    timeout=60,
    log_path="/absolute/external/path/run.jsonl",
)
```

`run_agent(user_input, *, model=None, executor=None, log_stream=None,
log_path=None, max_steps=4, model_name=None,
base_url="http://127.0.0.1:11434", temperature=0.0, timeout=60.0,
code_revision=None)` returns a frozen `AgentResult` with `run_id`, `answer`,
`steps`, `tool_calls`, and `stop_reason`.

For offline proofs, inject an object implementing
`complete(messages, tools=None)` and a caller-owned `io.StringIO()` log stream.
The response follows the existing `CompletionResult(content, usage,
raw_response)` adapter interface. An executor callable can bind a caller-owned
`RentalService` to production `execute_tool`; test doubles are for offline tests
only. The agent never calls a reader directly. Importing it and using a mock
requires no Ollama imports, database configuration, API key, or network.

Live client construction is lazy. The supplied model tag is required for a live
run; the base URL must be a loopback HTTP endpoint. The adapter receives a finite
HTTP timeout, temperature zero by default, `num_ctx=4096`, and `reasoning=False`.
An injected model owns its own timeout behavior. The separate agent environment
uses `requirements-agent.txt`; it does not change the web environment.

## Native protocol and bounded execution

One step means one returned model response. A failed transport attempt consumes
no step and is logged separately. `max_steps` must be a positive non-Boolean
integer; timeout must be a positive finite number. No retry loop surrounds model
requests. The budget is checked before each request.

The protocol reads native `raw_response.tool_calls` and
`raw_response.invalid_tool_calls`. Empty text with native tool calls is valid.
The exact assistant message is retained in history, and each tool message uses
the original call ID. There is no prose parser or alternate JSON protocol.

Calls execute in their returned list order. At most three calls are allowed per
response. An oversized or malformed batch is rejected before any call executes.
Missing/duplicate call IDs, invalid native calls, non-string content, and empty
responses without calls terminate as `malformed_response`. The returned response
still consumes one step; malformed output cannot reset the budget. Unknown tool
names with well-formed native call structure go through production
`execute_tool`, whose failure envelope is logged and returned to the model.

| Stop reason | Meaning | Answer |
| --- | --- | --- |
| `completed` | Nonempty model text with no native calls | Model text |
| `safety_block` | Executor returned its specific privacy-policy error | null |
| `max_steps` | No response budget remains | null |
| `model_error` | Model construction or request failed | null |
| `malformed_response` | Invalid native response or rejected batch | null |
| `tool_error` | Executor raised or returned an invalid JSON envelope | null |

A tool result produced on the last permitted step is not an answer: another
model response would be needed to consume it. Ordinary domain errors, such as a
missing rental, are not safety blocks. Listing text is untrusted data and cannot
change the tool allowlist, policy, or runtime configuration.

## Logs and command line

Each run appends strict JSONL records with a run ID, increasing sequence number,
and UTC timestamp. The start event contains Git revision and configuration.
Requests include conversation history and schemas; returned responses include
text/native calls; each executor invocation records its name, inputs, result,
and original call ID. Failed attempts use sanitized error events. One terminal
event contains the exact returned result fields and measured elapsed seconds.
Dependency exceptions and private environment values are never dumped.

Use synthetic, nonsensitive prompts and fixture data for saved evidence: logging
records model text and tool results and is not a general content-redaction system.
`code_revision` can be provided explicitly; otherwise local Git HEAD is recorded,
or `unknown` if unavailable. A working-tree edit is not represented by that SHA,
so selected genuine evidence must run against a committed code revision.

Choose either `log_stream` or `log_path`. File logs open in append mode and flush
after each event. The default destination is
`~/code/agent_outputs/data260-hw5/agent-runs/<run_id>.jsonl`, outside the repository.
Injected streams stay caller-owned. A log open/write/flush/close failure raises
a clean `AgentLogError`; it never returns evidence-free success. A broken log
cannot guarantee a terminal record, and any incomplete file is failed evidence.

```sh
python scripts/hw05/run_agent.py 'Count rentals for manager 1.' \
  --model qwen2.5:7b --max-steps 4 --timeout 60 \
  --log-path /absolute/external/path/run.jsonl
```

Use the dedicated agent interpreter and reviewed read-only database runtime
configuration. Keep credentials in private external configuration files. The CLI
prints the run ID, stop reason, counters, and the model answer for completion;
other outcomes receive a concise explanation. It never substitutes raw tool JSON
for an answer. Exit codes are 0 for completion, 1 for a non-answer stop, and 2 for
invalid configuration or required logging failure.

## Verification and evidence

`python scripts/hw05/run_offline_tests.py` retains the six Part 4 cases and adds
executor privacy blocking and an exact-step-ceiling MockModel proof. The focused
`tests/test_hw05_agent.py` covers the loop, strict configuration, error paths,
ordered batches, history, lazy imports, logging, and CLI contracts. MockModel
outcomes are offline proofs, not genuine local-model scenario evidence.

Selected real-model runs, direct executor demonstrations, measured metrics,
provenance, and the 200–300-word reflection are stored under
`reports/hw05/raw/part5/` and `reports/hw05/part5/`. Earlier evidence remains
historical. Screenshots are deferred to the final evidence pass and must not be
represented as complete by text logs alone.
