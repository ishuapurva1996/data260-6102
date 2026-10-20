# Part 4 AI-use facts for A's later report

1. AI assistance and human input: the human supplied the assignment, plan,
ownership, persistence/conflict requirements and permission for local commits.
Codex authored the file-memory service/CLI, synthetic fixtures, tests, audit and
part-specific evidence notes. Local qwen2.5:7b proposed conflict decisions,
extracted a user fact and answered recall questions through the HW1 adapter.
Do not describe this as code or evidence executed by the student personally.

2. Wrong AI outputs: the first live consolidation invented a parking correction
from F05 to F06. The second attempt's fresh-process answer misread the persisted
stove requirement as a rental-listing feature. Its earlier conversational reply
also invented an F55 memory ID; that assistant sentence was never stored as a
durable fact. All relevant raw outputs are retained in attempt-01/attempt-02.

3. How checked: the conflict validator compared model decisions with explicit
source correction links, and the separate audit compared the file against the
precommitted expected pairs. The restart process read the actual persisted file;
its stove answer contradicted the supporting user message. Offline tests cover
strict threshold boundaries, command results, evidence grounding, safe writes,
source retention and reopen behavior. Model answers were not used as their own
correctness judge.

4. Corrections: the conflict request now passes literal corrects arrays and says
an empty array cannot authorize a winner. The validator continues to reject
unsupported decisions before writing. Extracted facts now persist their exact
user quote and source-message ID with escaped newlines/pipes/comment markers,
so their meaning survives restart and compaction. The system prompt explains
the user-evidence field and that normal chat does not write facts or assign IDs.
Final live outcomes and any remaining limitations are in VERIFICATION.json.

The first incorrect parking proposal was rejected: zero incorrect decisions
were persisted. The final snapshot audit must independently report the number
of incorrectly resolved contradictions; keep that distinct from the count of
rejected model proposals. These are branch-level checks. A still owns the final
integrated comparison, report, screenshots and acceptance.
