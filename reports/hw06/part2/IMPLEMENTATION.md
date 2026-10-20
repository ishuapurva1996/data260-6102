# Part 2 implementation and verification

MongoDB memory code is complete for integration. Live acceptance remains pending: the leased attempt on 2026-10-20 UTC could not connect to MongoDB (`ServerSelectionTimeoutError`). No live conversation, memory inspection, aggregate response, or collection screenshot is claimed. The JSON fixtures used in tests are engineering checks only.

## Integration API

Use `MongoMemoryStorage(database)` from `src.hw06_memory_mongo.storage`, passing the same `s6102_doc` database object used by Part 1. Construction does not connect or write. The first chat lazily creates the memory indexes. The storage never closes the shared connection and never writes to `rentals`.

Construct `MongoMemoryService` from `src.hw06_memory_mongo.service` with keyword arguments `model`, `embedder`, `storage`, `config`, `count_tokens`, `clock`, `telemetry`, and optional `window_policy`. A supplies its existing generation adapter, pinned embedding model and tokenizer. Inject `JsonlTelemetry` for real captures; the default sink discards events. Set `config.source_commit` to the actual integrated server revision.

Mount `web_application.routers.chat.create_router(service)`. Its default dependency is the existing `require_user`; shared error handlers must be installed on the app. The factory also accepts `current_user_dependency` for offline tests. Routes are:

- `POST /api/chat`: owner-scoped chat; returns user/session/request IDs, reply, and selected memory.
- `GET /api/memory/{user_id}?session_id=...`: at most 16 messages in that session, latest session/user summaries, and the user's last 20 episodes. With no session filter, the user's latest session is selected. Recent sets are returned oldest first.
- `GET /api/aggregate/{user_id}`: UTC daily counts across all this user's sessions, including both roles and any stored partial failed turns; latest 10 summaries newest first.

User IDs must match the authenticated principal or its `:hw6:` experiment namespace. Every storage lookup filters by user. Session messages and summaries also filter by session; user summaries and episode retrieval span that user's sessions.

## Memory behavior

N counts previous stored records of either role. Save the current user record, exclude its ID from the last-N query, invoke the optional policy, then append the current text once in a labeled JSON data envelope. The response describes the selection before any post-answer updates. The system primer treats stored text as data and gives it no instruction authority.

After the assistant reply is stored, extraction receives only the current user message. Facts need nonblank text (at most 500 characters), finite importance in 0..1 and a supporting verbatim quote from that user message. Malformed/invalid entries are skipped, duplicates within an extraction are removed, and at most three valid facts are stored. Quote validation supplies a grounding check; it does not prove that a model's paraphrase is entailed by the quote. Fact and query embeddings must match the configured dimension, contain finite numbers and be nonzero. Corrupt historic episode vectors are skipped during ranking. Ranking uses cosine similarity and deterministic recency/ID tie breaking.

Session summaries are appended every M stored user messages (default 5), merging the previous summary with records since its covered-message marker. Stored summary metadata includes `user_message_count` and `through_message`. Once at least two distinct sessions have summaries, each session-summary update condenses only the latest summary from each session into a new user summary with `session_id=null`. User-summary metadata records `source_summary_ids`. A new lifetime summary is usable on the next request. The live runner includes ten turns in session one and five plus a recall turn in session two to expose this rule.

The injected `WindowPolicy` receives a copy of at most N previous records, with `short_term_n`, `token_budget`, and `count_tokens`. Its ordered-subset result is checked for record integrity. Baseline uses the candidates unchanged. C imports no D module and implements no eviction rule. A must inject D's policy when `config.policy=token_budget`; that setting without an implementation is rejected at construction.

## Instrumentation and errors

Every service chat emits one `request/chat` event, including failures. It includes the request context, sanitized configuration, main reported usage, actual six selected text blocks and their tokenizer component estimates. Missing reported counts remain null with `usage_source=missing`. Genuine reported zeros remain zero. `template_residual` is signed main prompt tokens minus the six estimates, or null if usage is missing.

Each extraction/session/lifetime generation call has its own usage and elapsed-time event. Each query/fact embedding has its own timing, input count, dimension and null generation token totals. All events share request correlation. Request service latency includes all these stages, storage and lock wait. Full HTTP elapsed latency, including transport/auth/serialization, is recorded separately by the live runner and D's measurement client.

Context preflight counts a Qwen chat rendering as an estimate and reserves output capacity. Reported usage is checked afterward too. Oversized prompts fail with `context_limit_exceeded` (422). Model/embedding failures return `model_unavailable` (503); PyMongo failures return `storage_unavailable` (503). Auxiliary failures retain main usage and mark the request failed. Writes before a failure remain durable; request IDs are correlation IDs, not idempotency keys. The service does not automatically retry a partial turn.

One service process serializes turns to protect the local adapter and summary cadence. Multiple app workers would need a shared user queue/lock; the controlled local runs use one process and sequential requests.

## Checks and remaining capture

`tests/test_hw06_mongo_memory.py` has 28 passing offline cases. The affected regression run has **159 passed, 45 skipped**; the skips are existing SQL-dependent checks without a real database. AST parsing and whitespace checks passed. No configured lint/typecheck command was found. Selected output and source hashes are in `reports/hw06/raw/part2/offline-verification.json` and `offline-tests.txt`.

Proof-first observations: initial collection failed because the memory package was absent. Later, a protocol-only injected service reproduced HTTP 500 because the router incorrectly required `.config`; the final code makes that router lookup optional, and the service still overwrites event source revision from server configuration.

After A restores MongoDB and real SQL/auth and mounts the routes, run `python -m scripts.hw06.part2.live_demo --help` and supply its runtime/env/CA/output paths. Set `HW6_DEMO_EMAIL` and `HW6_DEMO_PASSWORD` externally. The runner acquires the shared lease once, captures 16 real HTTP replies with latency, memory for both sessions, aggregate JSON and scoped collection/index documents, and checks the expected 32 stored messages and 2+1 session summaries plus lifetime summary. It stops on failure and never substitutes fake resources. Use a fresh output directory for every attempt.

A still needs to preserve matching server JSONL telemetry, verify all required real memory behavior and retrieval, confirm second-user isolation and persistence after app restart, and capture conversation and Compass/mongosh screenshots. Every terminal screenshot must visibly show Pragya Apurva. No Part 3 sweep, final report, push or tag was performed.
