# Part 3 preparation evidence

Status: code and fixed inputs prepared for integration. No measured comparison
has run. There are no measured answers, scores, latency results or filled results
tables in this preparation evidence.

The reproducible design and later invocation are documented in
`scripts/hw06/part3/README.md`. Actual user inputs are in its `conversation.json`;
root `memory_probes.yaml` contains exactly five fixed questions with concrete
expected facts, scoring rules, source-turn quotations and predeclared selection.

The selected `raw/part3/preparation-verification.json` records the observed final
offline check: **46 passed, no failures/skips**, with three dependency deprecation
warnings. It includes exact frozen input hashes and hashes for all 13 Python
source/test files, CLI help checks, and a local model-matching tokenizer check.
These checks used injected endpoints/model records and private external fixture
directories. They neither started the app on 8702 nor called a live model.
The Qwen tokenizer was loaded from the published local JSON with its SHA256
verified; this tests text counting and the selector, not model answer quality.

Checks cover N/whole-message eviction/oversized messages/nonmutation, full study
orchestration and new condition identities, optional probe clone allocation,
sequential-probe disclosure, event correlation/usage/config validation, failure
preservation, scoring-template integrity and manual assessments, signed quality
change, undefined savings at a zero denominator, separate auxiliary/embedding
accounting, cost arithmetic and no qualifying setting. Offline fixtures cannot
export measured tables. A lease orchestration spy checked exclusive ownership
without starting a server or making model calls.

AI-use facts for this part: Codex drafted the synthetic script, probes, selector,
runner, validation, metric/export code and engineering tests, then executed the
offline checks. An independently checked arithmetic fixture used 6,000 main
input and 600 output tokens: the assigned 10,000-conversation main-chat estimate
is $90. Adding 420 auxiliary input and 78 auxiliary output tokens gives $98.10.
These are deliberately constructed arithmetic checks, not experiment results.
Initial policy/live-boundary tests failed because their modules did not yet
exist, then passed after implementation. All actual model answer scoring and
interpretation remain to be done against the frozen rubric.

Pending integrated evidence: A's app factory injections and authenticated config
endpoint; C's actual request/auxiliary telemetry; real MongoDB/SQL login; verified
TLS and credentials; A's N30 context-fit pilot and source/config/input gate. The
live runner defaults to sequential fixed-order probes because no complete C
snapshot/clone interface was published. Later measurement must keep that declared
limitation or integrate a complete isolated clone implementation before freezing.
No file-memory content enters these MongoDB experiment prompts.
