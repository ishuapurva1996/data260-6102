"""Validate raw events, prepare human scoring, or export scored measured results."""
import argparse
import json
from pathlib import Path

from src.hw06_experiments.metrics import export_metrics, export_scoring_template
from src.hw06_experiments.validation import validate_study
from src.hw06_shared.models import QwenTokenCounter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("validate", "scoring-template", "metrics"))
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--scores", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.study / "manifest.json").read_text())
    config = manifest["base_config"]
    counter = QwenTokenCounter(config["tokenizer_path"], expected_sha256=config["tokenizer_sha256"])
    if args.mode == "validate":
        validate_study(args.study, count_tokens=counter)
        print("Complete correlated study; scores still required for metrics.")
    elif args.mode == "scoring-template":
        if not args.output:
            parser.error("scoring-template requires --output (a new JSON file)")
        export_scoring_template(args.study, args.output, count_tokens=counter)
    else:
        if not args.scores or not args.output:
            parser.error("metrics requires --scores and --output (a new directory)")
        export_metrics(args.study, args.scores, args.output, count_tokens=counter)


if __name__ == "__main__":
    main()
