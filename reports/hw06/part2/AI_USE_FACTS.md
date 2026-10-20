# Part 2 AI-use facts for integration

AI implemented the owned MongoDB service, mountable router, focused tests and live-capture runner using A's published interfaces. Verification used actual commands and inspected source; offline model/database outputs are explicitly synthetic and are not evidence of live model recall.

An independently checked issue: the first router implementation accessed `service.config` although the published `ChatService` protocol requires only `chat`, `memory`, and `aggregate`. A focused in-process test with a protocol-only service produced HTTP 500. Making the router's revision lookup optional changed that test to HTTP 200 while the actual service continued to stamp telemetry with its configured server revision. Client-supplied revision headers cannot replace it.

The committed-source regression run passed 159 checks and skipped 45 SQL-dependent checks. A real leased MongoDB preflight failed with `ServerSelectionTimeoutError`. No live chat response, memory JSON, collection contents, score, screenshot or benchmark result was invented. The student/A must still perform and assess the live integrated demonstration, report captures and submission.
