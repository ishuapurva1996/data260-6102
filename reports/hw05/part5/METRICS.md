# Part 5 metrics

Pragya Apurva. Tested code: `c7dc13ef214234fc0e34294b68e3cd74c76b2a73`. Local Qwen2.5 7B, native calls, temperature 0, context 4096, timeout 60 seconds, three-call batch cap. The first four runs use max_steps=4; the additional CLI run uses max_steps=1.

A step is one returned model response. Tool calls count actual executor invocations. All five rows below are genuine local Ollama runs against the dedicated upgraded MySQL3313 fixture; the blocked request performs no database lookup. Timing is the terminal event's measured run duration, rounded to three decimals here; exact values remain in JSONL.

| Scenario | Run ID | Steps | Tool calls | Stop reason | Seconds | Observed result / log |
| --- | --- | ---: | ---: | --- | ---: | --- |
| search | `31edc62e5ee3411ca12fc79e15ce8a6a` | 2 | 1 | `completed` | 9.969 | Returned titles and addresses for rentals 1–3. [JSONL](../raw/part5/search.jsonl) |
| search-detail | `c3ba82af82db440480e560bbefa5e5fd` | 3 | 2 | `completed` | 5.861 | Searched with limit 1, then fetched rental 1; final text used its description. [JSONL](../raw/part5/search-detail.jsonl) |
| manager-count | `159d4ef874204d6fa5aa1801909bbb81` | 2 | 1 | `completed` | 2.677 | Reported manager 1 has 7 rentals. [JSONL](../raw/part5/manager-count.jsonl) |
| private-contact | `7a5af19cd69c4af1938ad05e499fcc73` | 1 | 1 | `safety_block` | 1.652 | Native request set include_contact=true; executor blocked it; no model answer. [JSONL](../raw/part5/private-contact.jsonl) |
| cli-budget | `b205c9278a9b4da195a36a58a10aa91d` | 1 | 1 | `max_steps` | 1.646 | One real count call returned 7; budget stopped before another model response; no answer. [JSONL](../raw/part5/cli-budget.jsonl) |

The private-contact result is an actual executor safety block, not a prose refusal. The separate allowed/blocked demonstrations show one default factory construction for omitted/false flags and zero for true. MCP's real STDIO true/false calls both returned public details; MCP does not inherit the executor rule.

The deterministic offline MockModel test separately proves exactly three returned turns and three calls with no extra model request. It is not included in the real-run table. The additional real CLI budget run confirms a tool result is not presented as a model answer at the ceiling.

Verification: 473 pytest cases passed, zero failures/errors/skips; the eight named offline assertions passed twice with byte-identical stdout. Optimized Python was rejected with exit 2. An intentional failed assertion still printed all eight normal cases and an 8/9 summary with exit 1. `pip check` passed. One inherited MCP/Pydantic forward-reference warning remains.

These five synthetic scenarios establish the observed paths, not general model reliability. The first measured search includes lazy adapter initialization and longer answer generation; do not interpret single-run timings as database latency or compare them directly with Part 3's reused-service experiment. Prompt wording, model behavior, cache state, and hardware can change outcomes. Public column selection does not comprehensively redact free-text descriptions. Screenshots remain deferred.
