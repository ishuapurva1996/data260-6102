# Reproduce Part 3 results

Use the repository root and A's pinned HW6 Python environment. These commands read stored evidence and the local frozen tokenizer; they do not contact the model or rerun the study. Use a fresh output directory each time.

The measured application commit `4c0bd7c2dd0bedeab73d6a31d9f5c3a83a84e961` rejected a scored JSON round trip because JSON changes rubric integer keys into strings. The coordinator later fixed only that key-type comparison in `validate_scores`; the ordinary CLI now reproduces all seven saved exports byte for byte, without running the model or changing frozen inputs. Use a fresh external output directory:

```bash
python -B -m scripts.hw06.part3.export metrics \
  --study reports/hw06/raw/part3/measured-study \
  --scores reports/hw06/raw/part3/scores.json \
  --output /absolute/new-export-directory
```

The in-process adapter below records how D verified results before that coordinator repair. It converts exactly the five rubric key types back to integers, then calls the original validator and exporter. It leaves rubric values, answers, criteria, assigned scores and calculation code unchanged. The adapter was used after measurement; measured application source remained frozen.

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

The coordinator repair and scored-JSON public-export regression check are separate from the frozen measured app. The seven regenerated files were byte-identical to the committed D exports.
