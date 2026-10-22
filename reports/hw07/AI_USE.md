# AI use — Part 1 checkpoint

Pragya Apurva · DATA 260 · SID4 6102

## 1. What AI helped with and what I supplied

I supplied the assignment, execution plan, personal configuration, existing HW6
baseline and this session's Part 1 scope. The AI assistant inspected the existing
application, implemented the migration and JWT roles, updated frontend/HW6
clients, wrote and ran tests, reviewed the changes, and organized this evidence.
The commands and visual inspections described here were performed by the agent.
This account does not claim that I manually performed those checks. Later parts
and the final report remain pending.

## 2. One unsuitable AI-produced choice

The agent tried adding optional MCP packages to the web environment for a broad
historical test run. Their dependency requirements upgraded Starlette and other
packages away from the existing FastAPI web pins. That was unsuitable for the
shared web application.

## 3. How the problem was detected

Package compatibility checks and the failed integrated startup exposed the
conflict. The genuine outputs and failed attempts remain in `RUN_LOG.txt`.
Separate checks also distinguished absent optional packages from application
bugs instead of treating every historical suite as one compatible runtime.

## 4. What changed and why it works now

The conflicting optional packages were removed from the web environment and the
pinned HW7/web requirements were restored. MCP regression tests ran in the
existing dedicated MCP environment. The final web dependency check found all
88 packages compatible; the web suite passed 971 tests and the separate MCP suite
passed 156. Real HTTPS, MySQL, MongoDB, Ollama and browser checks then passed on
the committed application. This verifies the corrected environment without
claiming that the initial install or failed runs were successful.


---

# AI use — Parts 2 and 3 checkpoint

## 1. What AI helped with and what I supplied

I supplied the authoritative assignment, execution plan, Part 1 checkpoint,
personal configuration and the instruction to complete Parts 2 and 3. The AI
assistant implemented the hand-written loop and bounded Reflexion, wrote and ran
controlled-response tests, reviewed the adapter's real HTTP serialization,
executed the local Ollama/MySQL study, computed tables from retained raw records,
and rendered the saved genuine execution transcripts into labeled screenshots.
A separate AI-assisted trace review checked the scored outcomes against frozen
facts and actual observations. These are agent-performed checks; I do not claim
that I manually performed the experiments or independently audited the answers.

## 2. One unsuitable AI-produced choice

The first controlled fixtures used rental codes such as `S6102-HW7-AGENT-308`.
The existing shared API requires the established `S6102-R-<id>` format. The AI's
initial fixture naming was unsuitable for this application.

## 3. How the problem was detected

A genuine broad regression run failed 30 tests while serializing those fixture
rows through the existing API. The failed command and results remain in
`RUN_LOG.txt`. Investigation identified the fixture codes as the cause; the API
contract and historical rental records were valid.

## 4. What changed and why it works now

Only the three owned course fixtures were corrected to `S6102-R-308`,
`S6102-R-309` and `S6102-R-310`. Existing validation and historical data were
preserved. The affected regression tests and the final full web-compatible
suite passed. The fixtures, prompts, model settings, scoring and budgets were
then frozen before the 42 scored original/Reflexion cases. The raw results,
computed tables, separate independent AI-assisted audit, controlled-fault label,
and post-cleanup preservation check are linked in `PARTS2_3.md`.

Mocked/controlled-response tests establish edge-case behavior and are excluded
from model measurements. The failed-then-retried illustration is explicitly an
unscored injected final-count fault; its tool calls and both retries used the
real local model. The retries still failed the fixed task checks and stopped at
`human_review` after the two-retry ceiling. It is not successful recovery, a
natural scored failure, or evidence of a general quality improvement. Parts 4–6
and the final submission remain pending.


---

## Part 4 AI use addendum

1. I supplied the authoritative assignment, personal configuration, scope and account-assumption requirements. An AI assistant implemented the framework integration, tools, UI and tests, ran the real local-model demonstrations, and produced the evidence. A separate AI-assisted standard-library computation audited the source values and costs; this is not a claim of manual student coding.
2. An unsuitable genuine pilot answer chose membership despite its own correct $790.25 casual and $3,125 membership totals. Earlier pilots also used wrong columns or incomplete tool chains.
3. Deterministic per-ride/account checks rejected the wrong recommendation; the unchanged failed answer remains in raw/part4/pilots/p10-occasional. Controlled negative tests also show that correct totals cannot certify false prose or a $0.054 rate in place of captured $0.05. Independent source-row and integer-cent auditing confirms the final values.
4. The trusted phase hint now compares both actual calculator observations before requesting the final decision, and the framework still obtains all native calls from the model. The verifier preserves and rejects unsupported original answers. Both final real UI runs passed. Hypothetical account labels, pre-tax assumptions, guided prompting, failed pilots and controlled tests are explicitly distinguished from genuine final measurements. Parts 5–6 and final submission remain pending.
