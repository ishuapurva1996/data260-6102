# Ungraded Tiny Shakespeare warm-up

The assignment's full public text download is retained as `tinyshakespeare.txt`. Each warm-up consumes only the first 12,000 characters, as recorded in `run.json`, and runs all three chunkers with local MiniLM. This text is never included in the graded housing corpus or its metrics.

`shakespeare-initial/` preserves the first successful development warm-up. Its `code_commit` is the base repository HEAD at that time; the implementation was still uncommitted. It is development evidence, not a claim that the base commit contained the new pipeline. `shakespeare-committed/` is the authoritative repeat against tested code commit `cc0a57bae6e19778021643bffebf5c66d5e7c0a3` before the graded campaign.

Setup encountered two local-model-loading errors before any graded retrieval: the offline snapshot check expected files excluded by the download filter, and LlamaIndex attempted a cache directory outside the sandbox. The loader now uses matching file filters for download and offline lookup and passes the dedicated cache directory explicitly. The original errors were development setup issues; no failed graded run was discarded or overwritten.
