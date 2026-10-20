# Reproduce Part 3 results

Use the repository root and A's pinned HW6 Python environment. These commands read stored evidence and the local frozen tokenizer; they do not contact the model or rerun the study. Use a fresh output directory each time.

The accepted source's ordinary metrics CLI currently rejects a scored JSON round trip: JSON changes rubric integer keys into strings. The following in-process adapter converts exactly the five rubric key types back to integers and then calls the original validator and exporter. It leaves rubric values, answers, criteria, assigned scores and all calculation code unchanged. The adapter was used after measurement; measured source remained frozen.

```bash
PYTHONPATH=.:code python -B - metrics \
  --study reports/hw06/raw/part3/measured-study \
  --scores reports/hw06/raw/part3/scores.json \
  --output /absolute/new-export-directory <<'PY'
"""Postprocessing-only JSON key normalization; no measured source/input changes."""
import runpy
import sys
from src.hw06_experiments import metrics
original_validate=metrics.validate_scores

def validate_json_scores(scores,template,probes):
    rubric=scores["rubric"]
    if set(rubric)==set("12345"):
        normalized={**scores,"rubric":{int(k):v for k,v in rubric.items()}}
    else:
        normalized=scores
    return original_validate(normalized,template,probes)

metrics.validate_scores=validate_json_scores
sys.argv=["scripts.hw06.part3.export",*sys.argv[1:]]
runpy.run_module("scripts.hw06.part3.export",run_name="__main__")
PY
```

The output directory contains `metrics.json`, `memory_cost.csv`, `memory_cost.md`, `per_turn.csv`, `scores.json`, `auxiliary_generation.json` and `embeddings.json`. Compare them with `reports/hw06/part3/metrics/`; the verified regenerations were byte-identical. Reported quality change contains ordinary floating-point representation (`0.39999999999999947`); the exact score difference is 0.4.

The exported table uses only 30 primary requests for token/latency means and five probes for quality. Costs use primary main generation and primary extraction/session/lifetime summarization; embeddings have no assigned price. All raw records, including probes, remain available. No failed measured attempt was discarded: this study had zero failed attempts and zero reruns.

Required coordinator repair: normalize rubric key types before the top-level equality comparison in `src/hw06_experiments/metrics.py:validate_scores`, and test a filled scoring template saved to JSON and loaded again through the public export entry point. That repair is separate from the frozen measured app.
