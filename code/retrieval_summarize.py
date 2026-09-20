#!/usr/bin/env python3
"""Regenerate saved retrieval metrics without a model or network connection."""

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.retrieval.metrics import markdown_summary, summarize


def _read_json(path):
    def reject_constant(value):
        raise ValueError(f"nonfinite JSON constant {value} in {path}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "reports/hw03/METRICS.md")
    parser.add_argument("--check", action="store_true", help="verify saved summary and Markdown without modifying files")
    args = parser.parse_args(argv)
    try:
        summary = summarize(*[_read_json(args.run_dir / name)
                              for name in ("run.json", "records.json", "annotations.json")])
        markdown = markdown_summary(summary)
        summary_path = args.run_dir / "summary.json"
        if args.check:
            if _read_json(summary_path) != summary:
                raise ValueError(f"saved summary differs from recomputed metrics: {summary_path}")
            if args.output.read_text(encoding="utf-8") != markdown:
                raise ValueError(f"saved Markdown differs from recomputed metrics: {args.output}")
            print(f"Verified offline metrics for {summary['run_id']}; no files modified.")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
            args.output.write_text(markdown, encoding="utf-8")
            print(f"Wrote {summary_path} and {args.output}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Retrieval metric verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
