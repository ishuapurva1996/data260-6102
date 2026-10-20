# HW6 shared foundation

This branch prepares shared interfaces for document storage, MongoDB conversation
memory, experiments, and separate file memory. The four parts and their routes
are implemented in subsequent role branches. Existing HW1–HW5 behavior remains
the starting application.

Use Python 3.12 and a private environment:

```sh
python3.12 -m venv /path/outside/git/hw6-venv
/path/outside/git/hw6-venv/bin/python -m pip install -r requirements-hw06.lock.txt
```

`requirements-hw06.txt` expresses the direct dependencies; the lock file records
the complete compatible environment. It combines the existing web requirements
with the HW1 adapter, PyMongo, a local tokenizer, and YAML. The older retrieval
and MCP environments remain separate.

`HW6Config.from_env()` reads configuration without connecting to services. Fixed
values are SID4 6102, port 8702, prefix s6102, domain 6, and database s6102_doc.
Initial settings are N=12 previous messages, summary cadence 5 user messages,
top-k=3, baseline policy, eviction budget 160, context 4096, output limit 512,
temperature 0, seed 6102, and verification seed 266102. The initial models are
qwen2.5:7b for generation and nomic-embed-text:v1.5 for 768-dimensional embeddings.
The largest-window pilot must establish that the final fixed context is adequate.

Most environment names are `HW6_` plus the uppercase field name. The two historic
assignment names are `SHORT_TERM_N` and `SUMMARIZE_EVERY_USER_MSGS`. For example,
set `HW6_MONGO_URI`, `HW6_MODEL_DIGEST`, `HW6_EMBEDDING_DIGEST`,
`HW6_TOKENIZER_PATH`, and `HW6_TOKENIZER_SHA256` in a private external env file.
`HW6_CORS_ORIGINS` is comma separated. No env file, key, certificate, model asset,
or coordination handoff belongs in Git. `config.public_dict()` excludes the
MongoDB URI so telemetry cannot disclose its credentials.

Create exactly one application-owned `MongoConnection(config)`. Pass the same
`.database` object to document storage and Mongo memory storage, then call
`.close()` on application shutdown. Importing or constructing the connection is
offline; `.ping()` explicitly checks availability. Workers own their collections
and indexes, without dropping the database or changing another role's records.

The public shapes and protocols are in `src.hw06_shared.contracts`. Model calls
continue through `src.model_client` and its `complete(messages, tools=None)`
interface. `build_generation_client(config)`, `OllamaEmbedder(config)`, and
`QwenTokenCounter(path, expected_sha256=...)` implement the injected dependencies.
The tokenizer JSON must come from the matching Qwen2.5 model and be pinned by
revision and hash. Its text counts estimate prompt components; model-reported
usage supplies prompt/completion totals. `usage_counts(result)` returns null
counts when the backend did not report valid usage. Existing adapter callers
retain their historic count fields and default context.

`render_window(messages)` defines the text counted by the optional pure window
policy. C passes previous messages ordered by `(created_at, id)`, oldest first,
excluding the current message. D's policy receives N, a token budget, and the
injected counter, and returns retained records in their original order. It must
not mutate persisted records. File memory is a separate service and CLI.

`CallEvent`, `RequestContext`, and `TokenComponents` define versioned JSONL
telemetry. Emit one request event covering the complete chat operation, plus
separate extraction, summary, and embedding events. Main generation counts appear
only in the request event; auxiliary generation events never get folded into
those totals. Preserve failures, null usage, component estimates, signed template
residual, and source/configuration metadata. Never log database credentials.

Acquire the shared runtime lease for model/embedding calls, port 8702, and entire
benchmark windows:

```sh
python scripts/hw06/runtime_lease.py \
  --runtime-dir /path/outside/git/runtime --owner A --purpose demonstration \
  -- python /path/to/live-command.py
```

Python callers can use `with RuntimeLease(runtime_dir, owner="D",
purpose="full benchmark"):`. All roles use the same external runtime directory.
A busy lease fails immediately; inspect owner.json and wait. Keep runtime.lock
in place permanently. Release only your own context; do not delete the lock or
kill another process. The kernel releases the lock on process exit; a subsequent
successful acquisition replaces stale owner metadata. D reserves the entire
measurement window, including warm-up, calls, and probes, without nested leases.

Focused checks (offline fixtures are not assignment measurements):

```sh
python -m pytest tests/test_hw06_foundation.py reports/hw01/tests/test_model_client.py -q
```

Live MongoDB, SQL authentication, integrated route mounting, controlled benchmark
measurements, and final report/submission verification are separate later gates.
