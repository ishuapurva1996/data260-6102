# Raw evidence layout

The study CLI originally writes `original/` and `reflexion/` within its chosen
study directory. The repository preserves those files without changing their
bytes under [part2](../part2) and [part3](../part3). In `audit.json`, an evidence
reference such as `original/traces.jsonl:17` therefore means line 17 of
`raw/part2/traces.jsonl`; `reflexion/` means `raw/part3/`. The audit's recorded
SHA-256 values verify that mapping. The manifest, metrics and audit here are
shared by both modes.

In the separate demonstration audit, `recovery-demo/` maps to
`raw/part2/recovery/`. Both `controlled-fault-demo/` and its `reflexion/`
subdirectory map to `raw/part3/controlled-fault/`. The original line numbers
and file bytes are preserved.

To recompute tables from this repository snapshot, copy `manifest.json` into a
fresh external directory. Create its `original` and `reflexion` subdirectories
and copy the corresponding attempts/proposals JSONL files from part2/part3.
Run `scripts/hw07/agent_metrics.py --study <that-directory> --audit
reports/hw07/raw/parts2-3/audit.json` with the compatible Python environment.
This is pure saved-data calculation; it does not call the model or database.

`part2/unscored-repair` is a genuine pre-freeze pilot repair and is excluded
from the study. `part2/recovery` is a separate real missing-ID demonstration.
`part3/controlled-fault` is a separate **unscored controlled fault**: a +1
change to the first generated count, followed by a real unmodified model retry.
The empty scored `part3/reflections.jsonl` records that no scored task required
a Reflexion retry. Neither demonstration is included in the 21+21 comparison.

`preservation.json` is a fresh live database read after owned-fixture cleanup.
`evidence-check.json` validates saved-data provenance, hashes and Part 1
preservation; it is separate from the later final tagged smoke verification.
