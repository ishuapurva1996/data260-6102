# Part 2 live evidence

The run used the authenticated Q&A endpoint on the isolated Session B stack at
source revision `4bc060d11adbd2b8a13bbb525b23cc0280b0ab5d`. The original HW8
CLI warmed the local Qwen model. A separate Ollama request warmed the pinned
Nomic embedder. Neither warm-up populated the measured namespace.

| Measured requests | Hits | Misses | Errors | Hit rate | Mean hit | Mean miss |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 12 | 7 | 5 | 0 | 58.33% | 27.445 ms | 9,012.847 ms |

The mean values use the server's elapsed time from ingress to answer.
[Request results](requests.jsonl) also record elapsed client HTTP time.
[Verification](verification.json) includes a separate read of both Kafka
partitions and a per-request join to the [process logs](correlated-events.jsonl).
All five misses had one inbox and final record each and three non-fixture
generative model results. All seven hits had zero broker records and zero
generative model results for their fresh IDs. They still called the embedder.
Redis Search reported five indexed final answers.

Cases 7–9 ask for the title of `S6102-R-9203`, whose fixture title is Bayview
Garden Condo. Redis reused case 4's response about the property type of
`S6102-R-9202` at similarities 0.86335, 0.86335 and 0.87879. The measured hit
rate includes those three incorrect cached answers. They remain Part 2 results.

The [console excerpt](bypass-console.txt) and [screenshot](bypass-screenshot.png)
show the first miss and exact hit. The screenshot displays a replay of the
saved evidence excerpt.
For the report's code snippet, see the filter and KNN in
[`SemanticCache.closest`](../../../../src/hw09/semantic_cache.py) and the
hit/miss branch in the [Q&A handler](../../../../code/web_application/routers/kafka_questions.py).

[Version checks](version-checks.jsonl) record a live 3-to-1 update, the stale
demo hit, and the fresh miss and hit with enforcement enabled. A second update
during a live Kafka request produced `skipped_version_changed`, with the
in-flight request's Redis key absent. The checks also cover rollback on a
duplicate code, both delete routes, and a Redis search where an eligible
0.90-similarity vector wins over a stale exact match.
