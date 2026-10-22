"""Rates are derived from retained proposals/cases, with unchanged denominators."""

import json

import pytest

from scripts.hw07.agent_metrics import build, summarize
from scripts.hw07.agent_study import proposal_rows


def test_repair_does_not_enlarge_original_proposal_denominator():
    events = [
        {"event": "proposal", "proposal_id": "one", "initial_valid": False},
        {"event": "repair", "proposal_id": "one", "final_valid": True, "call_id": "fixed"},
        {"event": "proposal", "proposal_id": "two", "initial_valid": True},
    ]
    rows = proposal_rows(events)
    assert len(rows) == 2
    assert sum(r["initial_valid"] for r in rows) == 1
    assert sum(r["final_valid"] for r in rows) == 2


def test_empty_proposal_case_is_failed_and_never_disappears_from_task_denominator():
    rows = [
        {
            "success": False,
            "retries": 0,
            "tool_calls": 0,
            "latency_ms": 4.0,
            "proposal_count": 0,
            "initial_valid": 0,
            "final_valid": 0,
            "repair_operations": 0,
            "failure_categories": ["text when a tool was required", "lost multi-step chain"],
            "verification": {"unsupported_claims": []},
            "budget": {"total_tokens": 10, "reported_input_tokens": 8, "reported_output_tokens": 2},
        }
    ]
    result = summarize(rows)
    assert result["cases"] == 1 and result["task_successes"] == 0
    assert result["proposal_denominator"] == 0 and result["first_pass_rate"] is None
    assert result["post_repair_rate"] is None
    assert result["failure_categories"]["text when a tool was required"] == 1
    assert result["failure_categories"]["lost multi-step chain"] == 1


def test_unknown_usage_is_not_reported_as_zero_tokens():
    rows = [
        {
            "success": False,
            "retries": 1,
            "tool_calls": 2,
            "latency_ms": 9.0,
            "proposal_count": 2,
            "initial_valid": 2,
            "final_valid": 2,
            "repair_operations": 0,
            "failure_categories": [],
            "verification": {"unsupported_claims": []},
            "budget": {
                "total_tokens": None,
                "reported_input_tokens": 0,
                "reported_output_tokens": 0,
            },
        }
    ]
    result = summarize(rows)
    assert result["total_tokens"] is None and result["mean_tokens"] is None


def controlled_study(destination):
    """Synthetic offline records exercise table integrity, never measured evidence."""
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "scored": True,
                "source_dirty": False,
                "source_commit": "controlled-unit",
                "cases_sha256": "controlled-unit",
            }
        )
    )
    groups = {}
    for mode in ("original", "reflexion"):
        folder = destination / mode
        folder.mkdir()
        rows, proposals = [], []
        for repetition in range(1, 8):
            for task in "ABC":
                run_id = f"{mode}-{task}-{repetition}"
                rows.append(
                    {
                        "run_id": run_id,
                        "task_id": task,
                        "repetition": repetition,
                        "mode": mode,
                        "source_commit": "controlled-unit",
                        "source_dirty": False,
                        "controlled_fault": False,
                        "success": True,
                        "stop_reason": "success",
                        "retries": 0,
                        "tool_calls": 1,
                        "proposal_count": 1,
                        "initial_valid": 1,
                        "final_valid": 1,
                        "repair_operations": 0,
                        "latency_ms": 1.0,
                        "verification": {"unsupported_claims": []},
                        "failure_categories": [],
                        "budget": {
                            "overrun": False,
                            "charged_tokens": 2,
                            "total_tokens": 2,
                            "reported_input_tokens": 1,
                            "reported_output_tokens": 1,
                        },
                    }
                )
                proposals.append(
                    {
                        "proposal_id": run_id + "-p1",
                        "study_case_run_id": run_id,
                        "mode": mode,
                        "initial_valid": True,
                        "final_valid": True,
                    }
                )
        groups[mode] = (rows, proposals)
    return groups


def save_groups(destination, groups):
    for mode, (rows, proposals) in groups.items():
        for name, values in (("attempts", rows), ("proposals", proposals)):
            (destination / mode / (name + ".jsonl")).write_text(
                "".join(json.dumps(row) + "\n" for row in values)
            )


def test_overrun_failure_stays_in_complete_table_with_real_cost(tmp_path):
    groups = controlled_study(tmp_path)
    row = groups["original"][0][0]
    row.update(success=False, stop_reason="budget_exhausted")
    row["budget"].update(
        overrun=True, charged_tokens=25001, total_tokens=25001, reported_input_tokens=25000
    )
    save_groups(tmp_path, groups)
    result = build(tmp_path)
    assert result["original"]["cases"] == 21 and result["original"]["task_successes"] == 20
    assert result["original"]["total_tokens"] == 25041
    assert result["original"]["budget_violation_cases"] == 1
    assert not result["budget_checks_passed"]
    assert len((tmp_path / "original/reliability.csv").read_text().splitlines()) == 22


def test_comparison_rejects_mismatched_case_keys(tmp_path):
    groups = controlled_study(tmp_path)
    for row in groups["reflexion"][0]:
        row["repetition"] += 7
    save_groups(tmp_path, groups)
    with pytest.raises(AssertionError):
        build(tmp_path)


def test_proposals_must_reconcile_per_run_not_only_in_aggregate(tmp_path):
    groups = controlled_study(tmp_path)
    rows, proposals = groups["original"]
    rows[0].update(initial_valid=0, final_valid=0)
    proposals[1].update(initial_valid=False, final_valid=False)
    save_groups(tmp_path, groups)
    with pytest.raises(AssertionError):
        build(tmp_path)


def test_independent_audit_counts_claims_outside_parseable_json(tmp_path):
    groups = controlled_study(tmp_path)
    failed = groups["original"][0][0]
    failed.update(
        success=False, stop_reason="human_review", answer="The nonexistent rental is a house."
    )
    save_groups(tmp_path, groups)
    audit = {
        "cases": [
            {
                "run_id": row["run_id"],
                "false_rejection": False,
                "unsupported_final_claims": 1 if row["run_id"] == failed["run_id"] else 0,
            }
            for rows, _ in groups.values()
            for row in rows
        ]
    }
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(audit))
    result = build(tmp_path, path)
    assert result["original"]["unsupported_final_fields"] == 0
    assert result["original"]["unsupported_final_claims_audited"] == 1
