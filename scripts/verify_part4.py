#!/usr/bin/env python3
"""Verify saved Part 4 evidence offline; never construct an adapter or call a model."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import shlex
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_spec = importlib.util.spec_from_file_location("part4_offline_experiments", REPO_ROOT / "code/agents_experiments.py")
experiments = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(experiments)

from src.agent_graph.contracts import (
    ResponseContractError, parse_planner_response, parse_reviewer_response,
    validate_planner_proposal, validate_reviewer_feedback,
)

CATEGORIES = ("Valid first attempt", "Valid after 1 retry", "Valid after 2+ retries", "Hit turn ceiling")
EXPECTED = {"schema": 30, "ceiling_2": 20, "ceiling_10": 20, "adversarial": 5}
SUPPLEMENT_KEYS = ("schema_failure_count", "runs_with_schema_failures", "planner_retries",
                   "reviewer_issue_count", "reviewer_retry_count", "never_valid_count")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def schema_boundaries():
    """Exercise the current validator with the frozen protocol's boundary values."""
    good = {"tags": ["abc", "x" * 30, " é "], "summary": " ".join(["word"] * 25)}
    require(validate_planner_proposal(good) == good, "Valid boundaries changed or were rewritten")
    invalid = [
        {**good, "tags": [tag, "valid", "valid"]} for tag in ("ab", "x" * 31, "   ", 123, True)
    ] + [
        {**good, "tags": ["valid"] * n} for n in (2, 4)
    ] + [
        {**good, "tags": "valid"}, {**good, "tags": tuple(good["tags"])},
        {**good, "summary": " ".join(["word"] * 26)}, {**good, "summary": "   "},
        {**good, "summary": 123}, {**good, "extra": True}, {"tags": good["tags"]},
    ]
    for proposal in invalid:
        try:
            validate_planner_proposal(proposal)
        except ResponseContractError:
            continue
        raise ValueError(f"Invalid schema boundary accepted: {proposal!r}")
    raw = json.dumps(good)
    for malformed in ("```json\n" + raw + "\n```", raw + " prose", "[]",
                      '{"tags":[],"tags":[],"summary":"x"}', '{"tags":NaN,"summary":"x"}'):
        try:
            parse_planner_response(malformed)
        except ResponseContractError:
            continue
        raise ValueError("Strict JSON boundary accepted invalid response")
    return {"valid_boundary_cases": 1, "invalid_boundary_cases": len(invalid) + 5}


def inspect_trace(raw):
    """Reconstruct routing and counts directly, independently of evaluation.py."""
    trace = raw["trace"]
    ceiling = raw["max_turns"]
    require(type(ceiling) is int and ceiling > 0, "Invalid ceiling")
    require(isinstance(trace, list) and 1 <= len(trace) <= ceiling, "Unbounded or empty measured trace")
    require(raw["turn_count"] == raw["worker_attempts"] == len(trace), "Turn accounting mismatch")
    require(raw["status"] in {"accepted", "turn_limit"}, "Operational error or unknown is not a complete content outcome")
    require(raw.get("error") is None, "Content outcome contains operational error")
    require(raw.get("controlled_reviewer") is False and raw["config"]["controlled_reviewer"] is False,
            "Measured run used controlled Reviewer")
    elapsed = raw["elapsed_ms"]
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, "Invalid application latency")
    next_worker, revision = "planner", 0
    proposal = review = reviewed = None
    planner = reviewer = failures = reviewer_retries = issues = 0
    first_valid = None
    previous = None
    usage = Counter()
    zero_usage = 0
    for index, event in enumerate(trace, 1):
        worker = event["worker"]
        require(worker == next_worker and event["attempt"] == index, "Trace routing/attempt sequence mismatch")
        require(event.get("controlled") is False, "Controlled trace response")
        require(type(event["elapsed_ms"]) in (int, float) and math.isfinite(event["elapsed_ms"])
                and event["elapsed_ms"] >= 0, "Invalid worker latency")
        if worker == "planner":
            planner += 1
            revision += 1
            proposal = review = reviewed = None
        else:
            reviewer += 1
            reviewer_retries += int(previous is not None and previous["worker"] == "reviewer"
                                    and previous["outcome"] == "invalid")
            review = reviewed = None
        require(event["revision"] == revision, "Trace revision mismatch")
        try:
            parsed = (parse_planner_response if worker == "planner" else parse_reviewer_response)(event["raw"])
        except ResponseContractError:
            require(event["outcome"] == "invalid" and bool(event.get("error")), "Raw rejection is mislabeled")
            require(event.get("parsed") is None, "Rejected raw response has parsed output")
            failures += int(worker == "planner")
            next_worker = worker
        else:
            require(event["outcome"] == "valid" and event["parsed"] == parsed, "Parsed output differs from raw response")
            if worker == "planner":
                proposal = parsed
                first_valid = planner if first_valid is None else first_valid
                next_worker = "reviewer"
            else:
                review, reviewed = parsed, revision
                issues += len(review["issues"])
                next_worker = "planner" if review["issues"] else None
        if next_worker is None:
            require(index == len(trace), "Execution continued after approval")
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            count = event["usage"][key]
            require(type(count) is int and count >= 0, "Invalid recorded token count")
            usage[key] += count
        zero_usage += int(all(event["usage"][k] == 0 for k in ("input_tokens", "output_tokens", "total_tokens")))
        previous = event
    require(raw["proposal_revision"] == revision and raw["proposal"] == proposal,
            "Terminal proposal differs from latest Planner attempt")
    require(raw["reviewed_revision"] == reviewed and raw["review"] == review,
            "Terminal review differs from latest current-revision review")
    approval = proposal is not None and review is not None and reviewed == revision and not review["issues"]
    if raw["status"] == "accepted":
        require(approval and raw["final_output"] == proposal, "Acceptance lacks current approval")
        validate_planner_proposal(raw["final_output"])
        validate_reviewer_feedback(review)
        category = CATEGORIES[min(planner - 1, 2)]
    else:
        require(not approval and len(trace) == ceiling and raw["final_output"] is None, "Invalid ceiling exit")
        category = CATEGORIES[3]
    require(raw["adapter_response_count"] == len(trace), "Adapter response count differs from content trace")
    require(all(raw[k] == usage[k] for k in usage), "Token aggregate differs from trace")
    require(elapsed + len(trace) * 0.001 >= sum(event["elapsed_ms"] for event in trace),
            "Application latency is shorter than the worker durations")
    return dict(status=raw["status"], category=category, elapsed_ms=elapsed,
                turn_count=len(trace), max_turns=ceiling, planner_attempts=planner,
                planner_retries=planner - 1, reviewer_attempts=reviewer,
                first_schema_valid_attempt=first_valid, schema_failure_count=failures,
                reviewer_retry_count=reviewer_retries, reviewer_issue_count=issues,
                adapter_response_count=len(trace), zero_usage_response_count=zero_usage, **usage)


def arithmetic(records):
    """Compute table quantities without the production aggregation helper."""
    require(len(records) == 75, "Expected exactly 75 usable measured outcomes")
    counts = Counter(r["cohort"] for r in records)
    require(dict(counts) == EXPECTED, f"Wrong cohort counts: {dict(counts)}")
    require(len({r["trial_id"] for r in records}) == len({r["run_id"] for r in records}) == 75,
            "Duplicate trial or execution IDs")
    require(all(r["status"] in {"accepted", "turn_limit"} for r in records), "Error/unknown trials prevent completion")
    mean = lambda rows: sum(r["elapsed_ms"] for r in rows) / len(rows) if rows else None
    schema = []
    for category in CATEGORIES:
        rows = [r for r in records if r["cohort"] == "schema" and r["category"] == category]
        schema.append({"category": category, "count": len(rows), "mean_elapsed_ms": mean(rows)})
    cohorts = {}
    for name, size in EXPECTED.items():
        rows = [r for r in records if r["cohort"] == name]
        accepted = [r for r in rows if r["status"] == "accepted"]
        cohorts[name] = dict(expected=size, accepted=len(accepted), ceiling=size-len(accepted),
                             completion_rate_pct=len(accepted) / size * 100, mean_elapsed_ms=mean(rows),
                             accepted_mean_elapsed_ms=mean(accepted))
    selected = min((2, 10), key=lambda c: (-cohorts[f"ceiling_{c}"]["completion_rate_pct"],
                                          cohorts[f"ceiling_{c}"]["mean_elapsed_ms"], c))
    ordinary = [r for r in records if r["cohort"] == "schema"]
    first_valid = Counter(r["first_schema_valid_attempt"] for r in ordinary if r["first_schema_valid_attempt"] is not None)
    supplement = dict(observed_terminal_count=30, trace_observed_count=30,
                      attempt_counts={str(k): v for k, v in sorted(first_valid.items())},
                      never_valid_count=sum(r["first_schema_valid_attempt"] is None for r in ordinary),
                      runs_with_schema_failures=sum(r["schema_failure_count"] > 0 for r in ordinary),
                      **{key: sum(r[key] for r in ordinary) for key in
                         ("schema_failure_count", "planner_retries", "reviewer_issue_count", "reviewer_retry_count")})
    return dict(schema_categories=schema, cohorts=cohorts, deployment_max_turns=selected,
                schema_first_valid=supplement,
                adversarial_outcomes=[{key: r[key] for key in ("trial_id", "status", "turn_count", "planner_attempts",
                                                               "schema_failure_count", "elapsed_ms")}
                                      for r in records if r["cohort"] == "adversarial"],
                accepted=sum(r["status"] == "accepted" for r in records),
                ceiling=sum(r["status"] == "turn_limit" for r in records))


def equal_number(actual, expected, label):
    if expected is None:
        require(actual is None, f"{label}: empty mean must be null")
    else:
        require(type(actual) in (int, float) and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9),
                f"{label}: expected {expected}, found {actual}")


def reconcile_summary(summary, computed):
    require(summary["complete"] is True and summary["expected"] == summary["started"] == summary["terminal"] == 75,
            "Summary does not describe 75 complete trials")
    require(summary["error"] == summary["unknown"] == summary["pending"] == 0, "Summary hides errors or pending runs")
    for key in ("accepted", "ceiling"):
        equal_number(summary[key], computed[key], key)
    require(len(summary["schema_categories"]) == 4, "Wrong schema table rows")
    for expected, actual in zip(computed["schema_categories"], summary["schema_categories"]):
        require(actual["category"] == expected["category"], "Wrong schema category ordering")
        for key in ("count", "mean_elapsed_ms"):
            equal_number(actual[key], expected[key], "schema " + key)
    for name, expected in computed["cohorts"].items():
        for key, value in expected.items():
            equal_number(summary["cohorts"][name][key], value, name + " " + key)
    require(summary["schema_first_valid"] == computed["schema_first_valid"], "Supplementary schema counts mismatch")
    require(summary["deployment_choice"]["max_turns"] == computed["deployment_max_turns"], "Deployment rule mismatch")


def derived_files(path, records, summary):
    saved_rows = [json.loads(line) for line in (path / "results.jsonl").read_text().splitlines() if line.strip()]
    require(saved_rows == records, "results.jsonl differs from replayed records")
    fields = sorted({key for row in records for key in row if key != "files_sha256"})
    expected_csv = io.StringIO(newline="")
    writer = csv.DictWriter(expected_csv, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    with (path / "results.csv").open(newline="") as stream:
        require(list(csv.reader(stream)) == list(csv.reader(io.StringIO(expected_csv.getvalue()))),
                "results.csv differs from replayed records")
    require(experiments.read_json(path / "summary.json") == summary, "summary.json differs from replay")
    return {"files": ["results.jsonl", "results.csv", "summary.json"]}


def excluded_warmups(path, manifest, records):
    directory = path / "warmups"
    require(directory.is_dir() and any(directory.iterdir()), "Missing excluded ordinary warm-up evidence")
    measured_ids = {row["run_id"] for row in records if row.get("run_id")}
    checked = []
    for folder in sorted(directory.iterdir()):
        require(folder.is_dir(), "Unexpected warm-up artifact outside a trial directory")
        slot = dict(trial_id=folder.name, cohort="warmup", order=0, max_turns=10, input_key="schema", pair=None)
        record = experiments.read_trial(path, manifest, slot, folder="warmups")
        require(record is not None and record["status"] in {"accepted", "turn_limit"}, "Incomplete excluded warm-up")
        require(record["run_id"] not in measured_ids, "Warm-up execution reused among measured trials")
        inspect_trace(experiments.read_json(experiments.safe_path(path, record["evidence"])))
        checked.append(record["run_id"])
    require(len(set(checked)) == len(checked), "Duplicate warm-up execution IDs")
    return {"excluded_warmup_count": len(checked), "run_ids": checked}


def display_number(text, expected, label):
    text = text.strip().replace("%", "").replace(",", "")
    if expected is None:
        require(text == "N/A", f"{label}: empty table cell must be N/A")
    else:
        require(re.fullmatch(r"\d+(?:\.\d{1,3})?", text) is not None, f"{label}: invalid displayed number")
        # Accept 0–3 printed decimals only when equal to rounding the true value.
        places = len(text.split(".")[1]) if "." in text else 0
        require(float(text) == round(expected, places), f"{label}: displayed {text} does not round from {expected}")


def report_arithmetic(report_dir, computed, summary, campaign, manifest):
    lines = (report_dir / "METRICS.md").read_text().splitlines()
    rows = [[cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
            for line in lines if line.strip().startswith("|")]
    for expected in computed["schema_categories"]:
        matching = [row for row in rows if row[0] == expected["category"]]
        require(len(matching) == 1 and len(matching[0]) >= 3, "Missing/duplicate required schema table row")
        row = matching[0]
        display_number(row[1], expected["count"], row[0] + " count")
        display_number(row[2], expected["mean_elapsed_ms"], row[0] + " latency")
    for ceiling in (2, 10):
        matching = [row for row in rows if row[0] == str(ceiling) and len(row) >= 6]
        require(len(matching) == 1, "Missing/duplicate required ceiling table row")
        expected = computed["cohorts"][f"ceiling_{ceiling}"]
        for cell, key in zip(matching[0][1:6], ("expected", "accepted", "ceiling", "completion_rate_pct", "mean_elapsed_ms")):
            display_number(cell, expected[key], f"ceiling {ceiling} {key}")
    supplement = {key: computed["schema_first_valid"][key] for key in SUPPLEMENT_KEYS}
    supplement["first_schema_valid_attempt_1"] = computed["schema_first_valid"]["attempt_counts"].get("1", 0)
    for key, value in supplement.items():
        matching = [row for row in rows if row[0] == key]
        require(len(matching) == 1 and len(matching[0]) == 2, f"Missing/duplicate supplementary schema row: {key}")
        display_number(matching[0][1], value, key)
    for expected in computed["adversarial_outcomes"]:
        matching = [row for row in rows if row[0] == expected["trial_id"]]
        require(len(matching) == 1 and len(matching[0]) >= 6, "Missing/duplicate adversarial outcome row")
        row = matching[0]
        require(row[1] == expected["status"], f"Wrong adversarial status: {expected['trial_id']}")
        for cell, key in zip(row[2:6], ("turn_count", "planner_attempts", "schema_failure_count", "elapsed_ms")):
            display_number(cell, expected[key], f"{expected['trial_id']} {key}")
    choice = experiments.read_json(report_dir / "deployment_choice.json")
    require(choice["max_turns"] == computed["deployment_max_turns"], "Published deployment ceiling mismatch")
    for key, value in summary["deployment_choice"].items():
        require(key in choice and choice[key] == value, f"Published deployment {key} missing or differs from campaign summary")
    require(choice.get("campaign_id") == manifest["campaign_id"], "Published deployment identifies another campaign")
    require(choice.get("campaign_manifest_sha256") == experiments.digest((campaign / "manifest.json").read_bytes()),
            "Published deployment manifest hash mismatch")
    reference = choice.get("evidence")
    require(isinstance(reference, str) and not Path(reference).is_absolute()
            and (report_dir / reference).resolve() == (campaign / "summary.json").resolve(),
            "Published deployment evidence must reference the verified campaign summary")
    command = choice.get("command")
    require(isinstance(command, str), "Published deployment command is missing")
    arguments = shlex.split(command)
    require(arguments.count("--max-turns") == 1 and "--controlled-reviewer" not in arguments,
            "Published deployment command must select one normal-reviewer ceiling")
    position = arguments.index("--max-turns")
    require(position + 1 < len(arguments) and arguments[position + 1] == str(choice["max_turns"])
            and not any(arg.startswith("--max-turns=") for arg in arguments),
            "Published deployment command ceiling mismatch")
    return {"files": ["METRICS.md", "deployment_choice.json"], "max_turns": choice["max_turns"]}


def verify_campaign(campaign, report_dir=None):
    """Return scoped pass/fail evidence without writing into the saved campaign."""
    path = Path(campaign).resolve()
    checks = {}
    report = dict(assignment="HW2", part=4, SID4=6102, DOMAIN_ID=6, SEED=6102, VERIFY_SEED=266102,
                  seed_note="Assignment identity only; not model RNG seeds and no verification randomness is seeded.",
                  generated_at=datetime.now(timezone.utc).isoformat(),
                  scope="Offline Part 4 evidence verification; not final tagged whole-assignment HW2 verification.json.",
                  offline=True, model_calls=0, campaign=str(path), report_dir=str(Path(report_dir).resolve()) if report_dir else None,
                  checks=checks, passed=False)

    def check(name, action):
        try:
            details = action()
            checks[name] = {"passed": True, "details": details}
            return True
        except (ValueError, KeyError, TypeError, OSError, AttributeError, AssertionError) as exc:
            checks[name] = {"passed": False, "error": str(exc)}
            return False

    check("current_schema_boundaries", schema_boundaries)
    check("verification_git_metadata", lambda: report.update(verification_git=experiments.git_metadata()))
    loaded = {}

    def load():
        manifest, records, summary = experiments.load_campaign(path)
        loaded.update(manifest=manifest, records=records, summary=summary)
        report.update(campaign_id=manifest["campaign_id"], campaign_manifest_sha256=experiments.digest((path / "manifest.json").read_bytes()),
                      campaign_source_fingerprint=manifest["source_fingerprint"], campaign_source_sha256=manifest["source_sha256"],
                      current_code_sha256={name: experiments.digest((REPO_ROOT / name).read_bytes()) for name in experiments.SOURCE_PATHS},
                      config=manifest["config"], config_fingerprint=manifest["config_fingerprint"],
                      model_identity=manifest["model_identity"], execution_git=manifest["git"], environment=manifest["environment"])
        require(manifest["model_identity"]["name"] == manifest["config"]["model"] and bool(manifest["model_identity"]["digest"]),
                "Missing or inconsistent frozen model identity")
        require(manifest["inputs"]["schema"]["sha256"] != manifest["inputs"]["adversarial"]["sha256"],
                "Ordinary and adversarial inputs must be distinct")
        report["measured_counts"] = {"total": len(records), **dict(Counter(r["cohort"] for r in records))}
        return {"records_replayed": len(records), "hashes": "manifest, frozen sources, cases, trial files and raw CLI evidence"}

    if check("campaign_integrity_and_provenance", load):
        records, summary = loaded["records"], loaded["summary"]
        check("excluded_ordinary_warmups", lambda: excluded_warmups(path, loaded["manifest"], records))

        def traces():
            for record in records:
                require(record["status"] in {"accepted", "turn_limit"}, f"Incomplete content outcome: {record['trial_id']}")
                raw = experiments.read_json(experiments.safe_path(path, record["evidence"]))
                computed = inspect_trace(raw)
                require(all(record[key] == value for key, value in computed.items()),
                        f"Independent trace counters differ: {record['trial_id']}")
            return {"traces_checked": len(records), "normal_reviewer": True}

        check("independent_schema_approval_and_turn_accounting", traces)

        def numbers():
            computed = arithmetic(records)
            reconcile_summary(summary, computed)
            report["recomputed"] = computed
            return {"cohort_counts": EXPECTED, "deployment_max_turns": computed["deployment_max_turns"]}

        check("cohort_completeness_and_independent_arithmetic", numbers)
        check("derived_campaign_files", lambda: derived_files(path, records, summary))
        if report_dir is not None:
            if "recomputed" in report:
                check("published_tables_and_deployment_choice", lambda: report_arithmetic(Path(report_dir), report["recomputed"], summary, path, loaded["manifest"]))
            else:
                checks["published_tables_and_deployment_choice"] = {"passed": False, "error": "Complete raw arithmetic required first"}
    report["passed"] = all(item["passed"] for item in checks.values())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--report-dir", type=Path, help="Also require and verify METRICS.md and deployment_choice.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "reports/hw02/verification_part4.json")
    args = parser.parse_args(argv)
    result = verify_campaign(args.campaign, args.report_dir)
    result["command"] = [sys.executable, str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)]
    output = args.output.resolve()
    # Verification must never overwrite original evidence or historical Part 3 reports.
    protected = (args.campaign.resolve(), REPO_ROOT / "src", REPO_ROOT / "code", REPO_ROOT / "scripts", REPO_ROOT / "tests")
    require(not any(output.is_relative_to(p) for p in protected), "Verification output may not overwrite campaign or application files")
    require("part3" not in output.name.lower() and not output.is_relative_to(REPO_ROOT / "reports/hw02/raw/part3"),
            "Verification output may not overwrite historical Part 3 evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(experiments.json_bytes(result))
    print(json.dumps({"passed": result["passed"], "output": str(output), "checks": result["checks"]}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
