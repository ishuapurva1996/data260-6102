#!/usr/bin/env python3
"""Run reproducible Homework 1 checks and write verification.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


HW_DIR = Path(__file__).resolve().parent
REPO_ROOT = HW_DIR.parents[1]
CODE_DIR = REPO_ROOT / "code"
WEB_APP_DIR = CODE_DIR / "web_application"
DEFAULT_OUTPUT = HW_DIR / "verification.json"

MarkdownChecks = tuple[tuple[str, str], ...]

MARKDOWN_REQUIREMENTS: dict[str, tuple[Path, MarkdownChecks]] = {
    "README.md": (
        REPO_ROOT / "README.md",
        (
            ("Part 1 heading", r"^## Part 1 - Web application$"),
            ("Part 2 heading", r"^## Part 2 - Planner, Reviewer, and Finalizer$"),
            ("Part 3 heading", r"^## Part 3 - Non-determinism experiment$"),
            ("Part 4 heading", r"^## Part 4 - Model client and token accounting$"),
            ("verification heading", r"^## Verification$"),
            ("Part 2 command", r"^python code/agents_demo\.py\b"),
            ("Part 3 command", r"^python reports/hw01/run_nondeterminism\.py\b"),
            ("Part 4 command", r"^python code/hw1_client\.py\b"),
            ("verification command", r"^make -c reports/hw01 verify-hw01\b"),
            ("prior-context explanation", r"\bPrior context is resent because\b"),
            ("system-prompt explanation", r"\bA system prompt defines\b"),
            ("input-token explanation", r"\bInput tokens grow because\b"),
            ("context-window limit", r"\bfinite context window\b"),
        ),
    ),
    "AGENT.md": (
        REPO_ROOT / "AGENT.md",
        (
            ("code-review heading", r"^# Code Review Instructions$"),
            (
                "bullet-only instruction",
                r"^- Return only Markdown bullet points\.$",
            ),
            (
                "line-prefix instruction",
                r"^- Start every non-empty line with `- `\.$",
            ),
            ("review focus", r"^- Focus on correctness, edge cases, readability"),
        ),
    ),
    "DOMAIN_SCHEMA.md": (
        REPO_ROOT / "DOMAIN_SCHEMA.md",
        (
            ("assigned domain", r"^# DOMAIN_ID - 6 --> Rental Housing Listings$"),
            ("primary-field section", r"^# primary field$"),
            ("secondary-field section", r"^# secondary field$"),
            ("content-field section", r"^# content/description field$"),
            ("category values section", r"^  - Allowed values:$"),
            ("apartment category", r"^    - apartment$"),
            ("house category", r"^    - house$"),
            ("condo category", r"^    - condo$"),
            ("townhouse category", r"^    - townhouse$"),
        ),
    ),
    "METRICS.md": (
        HW_DIR / "METRICS.md",
        (
            ("fixed-input section", r"^## Fixed input$"),
            ("tag-set section", r"^## Tag-set results$"),
            ("distinct-tag-sets row", r"^\| Distinct tag sets \|"),
            ("all-20-runs row", r"^\| Tags in all 20 runs \|"),
            ("exactly-one-run row", r"^\| Tags in exactly 1 run \|"),
            ("latency section", r"^## Latency results$"),
            ("p50 row", r"^\| p50 \|"),
            ("p95 row", r"^\| p95 \|"),
            ("p99 row", r"^\| p99 \|"),
            ("interpretation section", r"^## Interpretation$"),
            (
                "acceptable-variation example",
                r"^Run-to-run variation is acceptable when\b",
            ),
            (
                "unacceptable-variation example",
                r"\bIt is not acceptable when\b",
            ),
        ),
    ),
    "AI_USE.md": (
        HW_DIR / "AI_USE.md",
        (
            (
                "AI-use answer",
                r"^## 1\. What I used an AI assistant for, and what I did myself\n\n\S.+$",
            ),
            (
                "independent-verification answer",
                r"^## 2\. One item I independently verified\n\n\S.+$",
            ),
            (
                "verification-method answer",
                r"^## 3\. How I detected or verified the problem\n\n\S.+$",
            ),
            (
                "change explanation",
                r"^## 4\. What I changed and why it works now\n\n\S.+$",
            ),
        ),
    ),
}


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "detail": detail}


def _required_files() -> dict[str, Path]:
    return {
        "domain schema": REPO_ROOT / "DOMAIN_SCHEMA.md",
        "repository README": REPO_ROOT / "README.md",
        "HTML form": WEB_APP_DIR / "index_hw1.html",
        "JavaScript": WEB_APP_DIR / "script_hw.js",
        "Dockerfile": CODE_DIR / "Dockerfile",
        "Part 2 pipeline": CODE_DIR / "agents_demo.py",
        "Part 3 fixed input": HW_DIR / "cases" / "nondeterminism_input.json",
        "Part 3 raw results": HW_DIR / "raw" / "nondeterminism_runs.json",
        "model adapter": REPO_ROOT / "src" / "model_client.py",
        "Part 4 CLI": CODE_DIR / "hw1_client.py",
        "agent instructions": REPO_ROOT / "AGENT.md",
        "Part 4 token counts": HW_DIR / "raw" / "part4_token_counts.json",
        "AI disclosure": HW_DIR / "AI_USE.md",
        "Part 3 metrics": HW_DIR / "METRICS.md",
        "reproducible instructions": HW_DIR / "REPRODUCIBLE_RUN_INSTRUCTIONS.md",
        "report": HW_DIR / "report.pdf",
    }


def validate_markdown_deliverables(
    requirements: dict[str, tuple[Path, MarkdownChecks]] | None = None,
) -> tuple[bool, str]:
    """Confirm that every assignment-named Markdown file has its required content."""

    using_default_manifest = requirements is None
    selected = MARKDOWN_REQUIREMENTS if using_default_manifest else requirements
    problems: list[str] = []

    for label, (path, required_phrases) in selected.items():
        try:
            contents = path.read_text(encoding="utf-8").lower()
        except OSError as exc:
            problems.append(f"{label}: could not read file ({exc})")
            continue

        missing_checks = [
            description
            for description, pattern in required_phrases
            if re.search(pattern, contents, flags=re.IGNORECASE | re.MULTILINE) is None
        ]
        if missing_checks:
            problems.append(f"{label}: missing {', '.join(missing_checks)}")

    if problems:
        return False, "; ".join(problems)
    if using_default_manifest:
        return True, "All 5 assignment-required Markdown files have the expected structure"
    return True, f"All {len(selected)} supplied Markdown files have the expected structure"


def validate_pdf(path: Path) -> tuple[bool, str]:
    """Perform dependency-free structural checks on the submitted PDF."""

    try:
        data = path.read_bytes()
    except OSError as exc:
        return False, f"Could not read report PDF: {exc}"

    if not data.startswith(b"%PDF-"):
        return False, "Missing PDF version header"
    if len(data) < 1024:
        return False, "PDF is unexpectedly small"
    page_objects = re.findall(rb"/Type\s*/Page\b", data)
    if not page_objects:
        return False, "PDF contains no page objects"

    trailer = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", data)
    if trailer is None:
        return False, "PDF trailer or EOF marker is missing"
    xref_offset = int(trailer.group(1))
    if xref_offset >= len(data) or data[xref_offset : xref_offset + 4] != b"xref":
        return False, "PDF cross-reference offset is invalid"

    page_count = len(page_objects)
    return True, f"PDF structure is valid; {page_count} page objects found"


def run_verification(node_bin: str | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    supported_python = sys.version_info[:2] in {(3, 11), (3, 12)}
    checks.append(
        check(
            "python_version",
            supported_python,
            f"Python {sys.version.split()[0]} (requires 3.11 or 3.12)",
        )
    )

    missing = [name for name, path in _required_files().items() if not path.is_file()]
    checks.append(
        check(
            "required_files",
            not missing,
            "All required files are present" if not missing else "Missing: " + ", ".join(missing),
        )
    )

    markdown_passed, markdown_detail = validate_markdown_deliverables()
    checks.append(check("markdown_deliverables", markdown_passed, markdown_detail))

    node = node_bin or os.environ.get("NODE_BIN") or shutil.which("node")
    if node:
        js_result = subprocess.run(
            [node, "--check", str(WEB_APP_DIR / "script_hw.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        js_detail = js_result.stderr.strip() or "Node.js syntax check passed"
        checks.append(check("javascript_syntax", js_result.returncode == 0, js_detail))
    else:
        checks.append(check("javascript_syntax", False, "Node.js executable not found"))

    test_environment = os.environ.copy()
    if node:
        test_environment["NODE_BIN"] = node
    test_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(HW_DIR / "tests"),
            "-v",
        ],
        cwd=REPO_ROOT,
        env=test_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    combined_test_output = test_result.stdout + test_result.stderr
    match = re.search(r"Ran (\d+) tests?", combined_test_output)
    test_count = int(match.group(1)) if match else 0
    checks.append(
        check(
            "automated_tests",
            test_result.returncode == 0 and test_count > 0,
            f"{test_count} tests passed" if test_result.returncode == 0 else combined_test_output[-1000:],
        )
    )

    try:
        nondeterminism = json.loads(
            (HW_DIR / "raw" / "nondeterminism_runs.json").read_text(encoding="utf-8")
        )
        successful = {
            temperature: sum(record.get("status") == "ok" for record in records)
            for temperature, records in nondeterminism["runs"].items()
        }
        part3_passed = (
            nondeterminism.get("status") == "complete"
            and successful == {"0.7": 20, "0.0": 20}
        )
        part3_detail = f"Successful runs by temperature: {successful}"
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        part3_passed = False
        part3_detail = f"Could not validate Part 3 data: {exc}"
    checks.append(check("part3_raw_results", part3_passed, part3_detail))

    try:
        token_data = json.loads(
            (HW_DIR / "raw" / "part4_token_counts.json").read_text(encoding="utf-8")
        )
        snapshots = token_data["stats_after_turn"]
        cumulative = token_data["cumulative"]
        part4_passed = (
            len(token_data["turns"]) == 5
            and snapshots["3"]["turn_count"] == 3
            and snapshots["5"]["turn_count"] == 5
            and cumulative["turn_count"] == 5
            and token_data["bullet_only_verification"] is True
        )
        part4_detail = (
            f"5 turns; cumulative tokens: input={cumulative['input_tokens']}, "
            f"output={cumulative['output_tokens']}, total={cumulative['total_tokens']}"
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        part4_passed = False
        part4_detail = f"Could not validate Part 4 data: {exc}"
    checks.append(check("part4_token_accounting", part4_passed, part4_detail))

    report_path = HW_DIR / "report.pdf"
    report_passed, report_detail = validate_pdf(report_path)
    checks.append(check("report_pdf", report_passed, report_detail))

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if all(item["status"] == "pass" for item in checks) else "fail",
        "checks": checks,
        "submission_note": "Create the final commit and hw1 tag before GitHub submission.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify DATA 260 Homework 1")
    parser.add_argument("--node", help="Path to the Node.js executable")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_verification(args.node)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
