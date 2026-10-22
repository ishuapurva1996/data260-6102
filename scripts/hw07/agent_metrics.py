"""Compute Parts 2/3 tables directly from all retained case/proposal records."""

import argparse
import csv
import json
from pathlib import Path

CATEGORIES = (
    "malformed arguments",
    "unknown tool",
    "text when a tool was required",
    "lost multi-step chain",
)


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def budget_violation(row):
    budget = row["budget"]
    return bool(
        budget.get("overrun", False)
        or budget.get("charged_tokens", 0) > budget.get("max_tokens", 24000)
        or row["tool_calls"] > (8 if row.get("mode") == "original" else 24)
        or row["retries"] > 2
    )


def summarize(rows):
    count = len(rows)
    proposals = sum(row["proposal_count"] for row in rows)
    initial = sum(row["initial_valid"] for row in rows)
    final = sum(row["final_valid"] for row in rows)
    known = all(row["budget"]["total_tokens"] is not None for row in rows)
    tokens = sum(row["budget"]["total_tokens"] for row in rows) if known else None
    tools = sum(row["tool_calls"] for row in rows)
    latency = sum(row["latency_ms"] for row in rows)
    return {
        "cases": count,
        "task_successes": sum(row["success"] for row in rows),
        "task_success_rate": sum(row["success"] for row in rows) / count if count else None,
        "proposal_denominator": proposals,
        "first_pass_numerator": initial,
        "post_repair_numerator": final,
        "first_pass_rate": initial / proposals if proposals else None,
        "post_repair_rate": final / proposals if proposals else None,
        "repair_operations": sum(row["repair_operations"] for row in rows),
        "tool_repair_cases": sum(row["repair_operations"] > 0 for row in rows),
        "retry_cases": sum(row["retries"] > 0 for row in rows),
        "retry_rate": sum(row["retries"] > 0 for row in rows) / count if count else None,
        "unsupported_final_fields": sum(
            len(row["verification"]["unsupported_claims"]) for row in rows
        ),
        "total_tool_calls": tools,
        "mean_tool_calls": tools / count if count else None,
        "total_tokens": tokens,
        "mean_tokens": tokens / count if count and known else None,
        "reported_input_tokens": sum(row["budget"]["reported_input_tokens"] for row in rows),
        "reported_output_tokens": sum(row["budget"]["reported_output_tokens"] for row in rows),
        "total_latency_ms": latency,
        "mean_latency_ms": latency / count if count else None,
        "failure_categories": {
            label: sum(label in row["failure_categories"] for row in rows) for label in CATEGORIES
        },
        "budget_violation_cases": sum(budget_violation(row) for row in rows),
    }


def write_csv(path, rows):
    fields = [
        "run_id",
        "task_id",
        "repetition",
        "mode",
        "success",
        "stop_reason",
        "retries",
        "tool_calls",
        "proposal_count",
        "initial_valid",
        "final_valid",
        "repair_operations",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "unsupported_final_fields",
        "unsupported_final_claims_audited",
        "failure_categories",
        "budget_violation",
        "source_commit",
        "started_at",
        "finished_at",
    ]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            data = {field: row.get(field) for field in fields}
            data.update(
                input_tokens=row["budget"]["reported_input_tokens"],
                output_tokens=row["budget"]["reported_output_tokens"],
                total_tokens=row["budget"]["total_tokens"],
                unsupported_final_fields=len(row["verification"]["unsupported_claims"]),
                failure_categories=json.dumps(row["failure_categories"]),
                budget_violation=budget_violation(row),
            )
            writer.writerow(data)


def build(study, audit_path=None):
    groups = {
        mode: read_rows(study / mode / "attempts.jsonl") for mode in ("original", "reflexion")
    }
    manifest = json.loads((study / "manifest.json").read_text())
    assert manifest["scored"] and not manifest["source_dirty"]
    expected_keys = {(task, repetition) for task in "ABC" for repetition in range(1, 8)}
    for mode, rows in groups.items():
        assert len(rows) == 21 and {(r["task_id"], r["repetition"]) for r in rows} == expected_keys
        assert len({r["run_id"] for r in rows}) == 21
        assert {r["task_id"] for r in rows} == {"A", "B", "C"}
        assert all(sum(r["task_id"] == task for r in rows) == 7 for task in ("A", "B", "C"))
        assert all(
            not r["source_dirty"]
            and r["mode"] == mode
            and not r["controlled_fault"]
            and r["source_commit"] == manifest["source_commit"]
            for r in rows
        )
        proposals = read_rows(study / mode / "proposals.jsonl")
        assert len(proposals) == sum(r["proposal_count"] for r in rows)
        assert len({p["proposal_id"] for p in proposals}) == len(proposals)
        assert all(
            p["mode"] == mode and p["study_case_run_id"] in {r["run_id"] for r in rows}
            for p in proposals
        )
        for row in rows:
            linked = [p for p in proposals if p["study_case_run_id"] == row["run_id"]]
            assert len(linked) == row["proposal_count"]
            assert sum(p["initial_valid"] for p in linked) == row["initial_valid"]
            assert sum(p["final_valid"] for p in linked) == row["final_valid"]
    result = {
        "student": "Pragya Apurva",
        "source_commit": manifest["source_commit"],
        "cases_sha256": manifest["cases_sha256"],
        "original": summarize(groups["original"]),
        "reflexion": summarize(groups["reflexion"]),
    }
    result["budget_checks_passed"] = all(
        result[mode]["budget_violation_cases"] == 0 for mode in groups
    )
    if audit_path is not None:
        audit = json.loads(audit_path.read_text())
        assert len(audit["cases"]) == 42 and len({r["run_id"] for r in audit["cases"]}) == 42
        assert all(
            type(row["false_rejection"]) is bool
            and type(row["unsupported_final_claims"]) is int
            and row["unsupported_final_claims"] >= 0
            for row in audit["cases"]
        )
        assert {r["run_id"] for r in audit["cases"]} == {
            r["run_id"] for rows in groups.values() for r in rows
        }
        for mode in groups:
            ids = {r["run_id"] for r in groups[mode]}
            result[mode]["verifier_false_rejections"] = sum(
                r["false_rejection"] for r in audit["cases"] if r["run_id"] in ids
            )
            result[mode]["unsupported_final_claims_audited"] = sum(
                r["unsupported_final_claims"] for r in audit["cases"] if r["run_id"] in ids
            )
            for row in groups[mode]:
                row["unsupported_final_claims_audited"] = next(
                    r["unsupported_final_claims"]
                    for r in audit["cases"]
                    if r["run_id"] == row["run_id"]
                )
    else:
        for mode in groups:
            result[mode]["verifier_false_rejections"] = None
            result[mode]["unsupported_final_claims_audited"] = None
    write_csv(study / "original/reliability.csv", groups["original"])
    write_csv(study / "reflexion/comparison.csv", groups["original"] + groups["reflexion"])
    (study / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.study, args.audit), indent=2))


if __name__ == "__main__":
    main()
