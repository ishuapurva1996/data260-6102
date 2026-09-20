#!/usr/bin/env python3
"""Prove saved-evidence corruption is rejected using isolated temporary copies.

Run from any working directory with the retrieval environment's Python. This
script never loads a model, retrieves, edits the source run, or writes Git state.
Only the requested JSON report is written outside its temporary directory.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location(
    "verify_hw03_part2", ROOT / "scripts/verify_hw03_part2.py"
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(run_dir, name):
    return json.loads((run_dir / name).read_text())


def write(run_dir, name, data):
    (run_dir / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def file_inventory(run_dir):
    return {
        str(path.relative_to(run_dir)): sha256(path)
        for path in sorted(run_dir.rglob("*")) if path.is_file()
    }


def regenerate_summary(run_dir):
    summary = verifier.summarize(
        read(run_dir, "run.json"), read(run_dir, "records.json"),
        read(run_dir, "annotations.json"),
    )
    write(run_dir, "summary.json", summary)


def corrupt(run_dir, case):
    """Return exact mutation details without touching source or METRICS.md."""
    if case == "missing_baseline_record":
        records = read(run_dir, "records.json")
        removed = records.pop()
        write(run_dir, "records.json", records)
        return {"removed": [removed["question_id"], removed["technique"]]}
    if case == "missing_annotation":
        labels = read(run_dir, "annotations.json")
        removed = labels["annotations"].pop(0)
        write(run_dir, "annotations.json", labels)
        return {"removed": [removed[k] for k in ("question_id", "technique", "node_id")]}
    if case == "changed_saved_vector":
        record = read(run_dir, "records.json")[0]
        filename = record["vectors_file"]
        vectors = read(run_dir, filename)
        vectors["documents"][0] = [-value for value in vectors["documents"][0]]
        write(run_dir, filename, vectors)
        return {"file": filename, "change": "Negate first document vector; preserve unit norm and dimensions; leave saved cosine unchanged."}
    if case == "changed_summary":
        summary = read(run_dir, "summary.json")
        summary["baseline"]["question_count"] += 1
        write(run_dir, "summary.json", summary)
        return {"change": "Increment summary.baseline.question_count by one."}
    if case == "changed_run_config":
        run = read(run_dir, "run.json")
        run["config"]["k"] += 1
        write(run_dir, "run.json", run)
        return {"change": "Increment run.config.k by one; frozen experiment config unchanged."}
    if case in ("changed_question_across_three_techniques", "changed_gold_across_three_techniques"):
        records = read(run_dir, "records.json")
        question_id = records[0]["question_id"]
        changed = []
        for record in records:
            if record["question_id"] == question_id:
                if case == "changed_question_across_three_techniques":
                    record["question"] += " [corrupted question]"
                else:
                    record["expected_source_ids"] = ["CORRUPTED_GOLD_SOURCE"]
                changed.append(record["technique"])
        if len(changed) != 3:
            raise ValueError("Expected three technique records for the corruption control")
        write(run_dir, "records.json", records)
        return {"question_id": question_id, "techniques": changed,
                "change": "Mutate the same field consistently across techniques; frozen questions remain unchanged."}
    run = read(run_dir, "run.json")
    if case == "empty_code_hash_inventory":
        run["code_hashes"] = {}
        write(run_dir, "run.json", run)
        return {"change": "Replace run.code_hashes with an empty object."}
    stats = run["techniques"]["token"]["stats"]
    if case == "changed_chunk_count_with_regenerated_summary":
        stats["chunk_count"] += 1
        mutation = "Increment token chunk_count by one; regenerate summary from altered run."
    elif case == "changed_character_average_with_regenerated_summary":
        stats["average_character_length"] += 10
        mutation = "Increase token average_character_length by ten; regenerate summary from altered run."
    elif case == "changed_character_audit_with_regenerated_summary":
        stats["node_lengths"][0]["character_length"] += 1
        stats["average_character_length"] = sum(
            row["character_length"] for row in stats["node_lengths"]
        ) / len(stats["node_lengths"])
        mutation = "Increment first token node's audited character length; recompute its mean and regenerate summary. Saved node text unchanged."
    else:
        raise ValueError(f"Unknown corruption case: {case}")
    write(run_dir, "run.json", run)
    regenerate_summary(run_dir)
    return {"change": mutation, "summary_regenerated": True,
            "METRICS_md_modified": False}


CASES = [
    ("missing_baseline_record", ValueError, "Missing or duplicate baseline combination"),
    ("missing_annotation", KeyError, None),
    ("changed_saved_vector", ValueError, "Saved cosine or rank differs from independently recomputed vectors"),
    ("changed_summary", ValueError, "Saved summary differs from raw regeneration"),
    ("changed_run_config", ValueError, "Run config differs from frozen config"),
    ("changed_question_across_three_techniques", ValueError, "Record query/gold sources differ from frozen question"),
    ("changed_gold_across_three_techniques", ValueError, "Record query/gold sources differ from frozen question"),
    ("empty_code_hash_inventory", ValueError, "Recorded code hash inventory is incomplete"),
    ("changed_chunk_count_with_regenerated_summary", ValueError, "Chunk count differs from saved nodes"),
    ("changed_character_average_with_regenerated_summary", ValueError, "Node average length mismatch"),
    ("changed_character_audit_with_regenerated_summary", ValueError, "Node character/source audit mismatch"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "reports/hw03/raw/part2/baseline-20260920")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("OFFLINE_NEGATIVE_CHECKS.json"))
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    output = args.output.resolve()
    started = now()
    original_inventory = file_inventory(run_dir)
    metrics_path = ROOT / "reports/hw03/METRICS.md"
    metrics_before = sha256(metrics_path)
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="hw3-part2-corruption-", dir="/tmp") as temporary:
        scratch = Path(temporary)
        control_dir = scratch / "unmodified_control"
        shutil.copytree(run_dir, control_dir)
        control = verifier.verify_run(control_dir, root=ROOT)
        control_result = {key: control[key] for key in (
            "status", "verified_at", "run_id", "verifier_commit", "code_commit",
            "freeze_commit", "baseline_combinations", "vector_checks",
        )}
        for case, expected_type, expected_message in CASES:
            case_dir = scratch / case
            shutil.copytree(run_dir, case_dir)
            case_started = now()
            details = corrupt(case_dir, case)
            modified = file_inventory(case_dir)
            changed_files = [name for name, value in modified.items()
                             if original_inventory.get(name) != value]
            result = {"case": case, "started_at": case_started, "mutation": details,
                      "changed_files": changed_files,
                      "expected_exception_type": expected_type.__name__,
                      "expected_exception_message": expected_message}
            try:
                verifier.verify_run(case_dir, root=ROOT)
            except (ValueError, KeyError) as error:
                result.update({"rejected": True, "exception_type": type(error).__name__,
                               "exception_message": str(error)})
                matched = type(error) is expected_type and (
                    expected_message is None or str(error) == expected_message
                )
                if case == "missing_annotation":
                    matched = matched and error.args[0] == tuple(details["removed"])
                result["status"] = "pass" if matched else "unexpected_rejection"
            else:
                result.update({"status": "fail", "rejected": False,
                               "exception_type": None, "exception_message": None})
            result["finished_at"] = now()
            outcomes.append(result)
    originals_unchanged = file_inventory(run_dir) == original_inventory
    metrics_unchanged = sha256(metrics_path) == metrics_before
    passed = sum(row["status"] == "pass" for row in outcomes)
    result = {
        "schema_version": 1,
        "status": "pass" if passed == len(CASES) and originals_unchanged and metrics_unchanged else "fail",
        "started_at": started, "finished_at": now(),
        "command": ".venv-retrieval/bin/python reports/hw03/part2/check_evidence_corruption.py",
        "root": str(ROOT), "source_run_directory": str(run_dir),
        "python_executable": sys.executable, "python_version": sys.version,
        "git_head": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "verifier_sha256": sha256(ROOT / "scripts/verify_hw03_part2.py"),
        "check_script_sha256": sha256(Path(__file__)),
        "input_run_json_sha256": original_inventory["run.json"],
        "input_run_files_sha256": original_inventory,
        "input_METRICS_md_sha256": metrics_before,
        "original_run_files_unchanged": originals_unchanged,
        "original_METRICS_md_unchanged": metrics_unchanged,
        "unmodified_copy_control": control_result,
        "negative_case_count": len(CASES), "expected_rejection_count": passed,
        "cases": outcomes,
        "scope": "Offline artifact consistency and provenance checks. No model, retrieval, network, Git writes, or modifications to source evidence. Each case starts from an independent temporary copy. These checks do not establish semantic truth of manual answer-support labels.",
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "control": control_result["status"],
                      "negative_case_count": len(CASES), "expected_rejection_count": passed,
                      "original_run_files_unchanged": originals_unchanged,
                      "original_METRICS_md_unchanged": metrics_unchanged,
                      "output": str(output)}, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
