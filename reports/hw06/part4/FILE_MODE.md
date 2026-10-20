# File memory interface and comparison preparation

This is Part 4's standalone CLI in the existing semester repository. It neither
registers an API route nor inserts files into the Part 2/3 MongoDB prompts.

## Interface

`FileMemoryService(*, agent_path: Path, memory_path: Path, model: GenerationClient,
clock: Clock = utc_now, telemetry: TelemetrySink | None = None)` implements
`handle(message, *, recent_messages=(), context=None) -> dict` as A specified.
The model is the shared HW1 adapter, constructed by build_generation_client.
The injected clock returns aware UTC. Both paths must exist and be UTF-8 files;
missing files produce an explicit CLI error. The caller initializes new memory
as an empty file; missing metadata then requests consolidation on the next chat.
The caller owns per-user path selection and recent-message history. Do not share
one file among unrelated users. A can inject a fake model/clock without a runtime
lease. Live service callers must acquire A's runtime lease themselves; the CLI
acquires it around each model call, so do not wrap the CLI in a second lease.

All successful results include reply, kind, command, request_id. `/memory` also
returns counts, timestamp status and consolidation reasons. `/compact` returns
before/after counts, raw model attempts, per-key conflict decisions, final memory,
and trigger state before/after. Invalid proposals return an error and attempts;
the original is preserved. `/dream` returns added_entries, evidence provenance,
raw extraction and counts; it keeps the last-consolidated timestamp unchanged.
Normal replies include memory_state and any auto_compact result. A validation
error is observable and must not be treated as a successful answer. CLI emits
one JSON object per input and exits nonzero if any input failed.

Recent conversation exists only in the current CLI process. `/dream` extracts
facts from its user messages and requires a verbatim supporting quote and value.
Assistant messages are excluded. Facts persist; raw chat history does not.

## File representation and thresholds

The timestamp is `<!-- last_consolidated_utc: ISO8601_UTC -->`. Missing, invalid,
multiple, non-UTC/naive, and future timestamps explicitly require consolidation.
Otherwise triggers are strictly counted lines >40 OR elapsed age >24 hours.
Ordinary chat checks these before generation. `/memory` displays the file without
modifying it; `/compact` forces the same consolidation function; `/dream` appends
and the next ordinary chat checks thresholds. `/help` explains the commands.

Physical lines mean Python str.splitlines(), including comments and blank lines.
Counted lines exclude blanks, HTML comments (including multiline comments), and
full-line # comments. One counted line is one memory message/entry. It is not
the number of MongoDB messages or user turns. Compaction preserves other comments.
It does not force deletion when a file has >40 unique facts: report its actual
remaining counts and organize files explicitly if required.

Structured one-line facts use `- [F01] key: value`. A correction adds
` | corrects=F00`; multiple source IDs and correction IDs are comma separated.
Reserved separator ` | ` and newline characters cannot occur in extracted values.
Exact duplicate key/value pairs merge their source IDs. Conflict groups are
different values with the same key. Every value and source ID survives, with
current/superseded/unresolved status tags. Only explicit correction links reaching
all alternatives can select a current claim. An ambiguous conflict retains both
claims marked unresolved. Arbitrary plain lines are kept and exact duplicates
merge; semantic contradictions in differently named keys/plain prose require
human inspection. No claim of general semantic conflict detection is made.

Writes use a temporary file in the destination directory, flush/fsync, verify the
loaded original has not changed, and atomically replace the runtime file. The
optimistic edit check is not a multi-process transaction; use one writer per file.
The small temporary file is an application write mechanism and is removed.

## Exact file-side comparison commands for A

Use this small scenario on both integrated modes: budget 2200 USD, neighborhood
Willow Glen, one cat; explicitly correct the budget to 2400 USD; compact; restart;
ask the current budget, neighborhood and pet. Use a fresh synthetic MongoDB user
and session for its side. Do not reuse D's experiment users or data. This scenario
is outside the scored Part 3 experiment.

From the integrated repository root (replace only the Python/runtime paths if A
recreates the environment), initialize an isolated file:

```bash
mkdir -p /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/comparison-file
cp reports/hw06/raw/part4/MEMORY.comparison.start.md /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/comparison-file/MEMORY.md
/Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime/venv/bin/python scripts/hw06/part4/cli.py --agent-file AGENT.md --memory-file /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/comparison-file/MEMORY.md --env-file /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime/hw06.env --runtime-dir /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime --message /memory --message 'Correction: my budget is now 2400 USD, replacing 2200 USD.' --message /dream --message /compact --message /memory
```

End that process, then run a fresh process:

```bash
/Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime/venv/bin/python scripts/hw06/part4/cli.py --agent-file AGENT.md --memory-file /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/comparison-file/MEMORY.md --env-file /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime/hw06.env --runtime-dir /Users/pragyaapurva/code/agent_outputs/data260-hw6/parallel-prompts/runtime --message /memory --message 'What are my current budget, neighborhood and pet requirement?'
```

Inspect actual extracted keys/correction references and all error fields. Retain
raw responses when comparing. Expected criteria are 2400 USD as current, 2200 USD
as superseded history, Willow Glen, one cat. Do not count an unevidenced or
unresolved correction as successful recall.

## File half of the comparison (limits to test in integration)

| Dimension | File-side evidence/behavior | MongoDB work A must still observe |
| --- | --- | --- |
| Inspectability | Markdown shows all claims, source IDs and status; Git shows before/after | Inspect documents, IDs, summaries, retrieval choices in Compass/API |
| Persistence after restart | CLI reloads files on every handle; selected live restart logs must show both contents and recall | Restart integrated application and verify stored facts and recall |
| Many sessions | One explicit file per user/workspace; full-file reads and prompt insertion grow with facts; history is process-local; single writer limitation | Check actual user/session isolation, indexes and retrieval growth |
| Must-not-forget facts | All original values/IDs survive consolidation; model proposals are validated; prompt size and semantic-key mismatch still limit recall | Check existence in storage separately from selection and correct recall |

These are file implementation facts and integration questions, not a completed
observed comparison with MongoDB. No scalability benchmark is claimed. Persistence
alone cannot guarantee recall in either mode. File mode has no tokenizer window
eviction: use small files/history that fit the configured context and inspect
actual prompt usage; split/archive with provenance before large-scale use.
