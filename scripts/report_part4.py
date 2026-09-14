#!/usr/bin/env python3
"""Format verified Part 4 results as submission tables; strictly offline."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("part4_presentation_runner", ROOT/"code/agents_experiments.py")
experiments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiments)


def render(campaign, report_dir):
    campaign, report_dir = Path(campaign).resolve(), Path(report_dir).resolve()
    summary = experiments.write_report(campaign)
    if not summary["complete"]:
        raise ValueError("Preserved incomplete results; complete submission tables require 75 usable outcomes")
    manifest, rows, _ = experiments.load_campaign(campaign)
    relative = Path(os.path.relpath(campaign, report_dir)).as_posix()
    number = lambda value: "N/A" if value is None else f"{value:.2f}"
    choice = summary["deployment_choice"]
    ceiling = choice["max_turns"]
    warmup_count = len(list((campaign/"warmups").iterdir()))
    lines = [
        "<!-- PART4:START -->", "# Part 4: output schema and loop safety", "",
        f"Campaign `{manifest['campaign_id']}`: **75/75** terminal content outcomes; "
        f"{summary['accepted']} accepted, {summary['ceiling']} ceiling exits, "
        f"{summary['error']} operational errors, {summary['unknown']} unknown, {summary['pending']} pending.", "",
        f"Frozen execution HEAD `{manifest['git']['commit']}` (dirty working tree). "
        f"Prepared {manifest['prepared_at']}. [Manifest]({relative}/manifest.json), "
        f"[rows]({relative}/results.csv), [unrounded summary]({relative}/summary.json).", "",
        "Model `qwen3:1.7b`, temperature 0, JSON mode, reasoning disabled, 120-second per-call timeout, "
        "4096-token context in the shared adapter. Fresh process, state and adapter per trial; normal Reviewer throughout. "
        f"Sequential execution retained normal Ollama caching/residency. {warmup_count} ordinary warm-up(s) were excluded; no pilots. "
        "HW2 / SID4 6102 / DOMAIN_ID 6 / SEED 6102 / VERIFY_SEED 266102. These identity seeds were not passed to the model.", "",
        "## Thirty frozen-input trials", "",
        "A run is a complete graph execution; a turn is one Planner or Reviewer execution. "
        "Accepted runs are grouped by Planner attempts: one, two, or three-plus. A ceiling exit takes precedence "
        "over a valid but unapproved draft. Reviewer retries do not count as Planner retries. "
        "`schema_failure_count` counts rejected Planner responses, including JSON parsing and schema errors.", "",
        "Latency is **application-run latency** from the CLI's `elapsed_ms`: Git inspection, adapter/graph construction, "
        "execution and trace handling; process startup/imports and evidence writing are excluded. "
        "Means use stored values without intermediate rounding. Empty buckets are N/A.", "",
        "| Outcome over 30 runs | Count | Mean latency (ms) |", "|---|---:|---:|",
    ]
    for row in summary["schema_categories"]:
        lines.append(f"| {row['category']} | {row['count']} | {number(row['mean_elapsed_ms'])} |")
    supplement = summary["schema_first_valid"]
    lines += ["", "Schema-first validity distinguishes structural repair from semantic revision:", "",
              "| Metric | Value |", "|---|---:|"]
    for key in ("schema_failure_count", "runs_with_schema_failures", "planner_retries", "reviewer_issue_count", "reviewer_retry_count", "never_valid_count"):
        lines.append(f"| {key} | {supplement[key]} |")
    lines.append(f"| first_schema_valid_attempt_1 | {supplement['attempt_counts'].get('1', 0)} |")
    lines += ["", f"First valid Planner attempt distribution: `{json.dumps(supplement['attempt_counts'], sort_keys=True)}`. "
              "A schema-valid proposal still requires current Reviewer approval.", "",
              "## Ceiling comparison and deployment choice", "",
              "Twenty distinct runs per ceiling use the same frozen ordinary input and model settings. "
              "Pairs alternate order (2 then 10, 10 then 2). Completion is accepted/20; "
              "the latency mean includes every run, including ceiling exits.", "",
              "| Ceiling | n | Accepted | Ceiling exits | Completion % | Mean latency (ms) |",
              "|---:|---:|---:|---:|---:|---:|"]
    for c in (2, 10):
        stats = summary["cohorts"][f"ceiling_{c}"]
        lines.append(f"| {c} | {stats['expected']} | {stats['accepted']} | {stats['ceiling']} | {number(stats['completion_rate_pct'])} | {number(stats['mean_elapsed_ms'])} |")
    if all(r["turn_count"] == 2 for r in rows if r["cohort"].startswith("ceiling_")):
        lines += ["", "Every comparison run completed in two turns under either ceiling. The small observed latency "
                  "difference determines the prescribed tie-break; it does not establish that a larger ceiling causes faster execution."]
    lines += ["", f"**Choose ceiling {ceiling}**: {choice['reason']}. Rule: {choice['rule']} "
              "This choice applies to this model, input, configuration, and sample; it does not establish general deployment readiness. "
              "The graph's default remains 10. [Machine-readable choice](deployment_choice.json).", "",
              "```sh", f".venv-agents/bin/python code/agents_graph.py --input-json reports/hw02/cases/schema_input.json --max-turns {ceiling}",
              "```", "", "## Five adversarial trials", "",
              "The frozen listing contains conflicting pet, parking and laundry claims, plus embedded instructions "
              "to use two short tags and a 40-word fenced response. Both workers are instructed to treat listing text as data. "
              "The ordinary input and this case were selected before measurement; the adversarial input was never retuned.", "",
              "| Trial | Status | Turns | Planner attempts | Schema failures | Latency ms |", "|---|---|---:|---:|---:|---:|"]
    adversarial = [r for r in rows if r["cohort"] == "adversarial"]
    adversarial_raw = {r["trial_id"]:experiments.read_json(campaign/r["evidence"]) for r in adversarial}
    for row in adversarial:
        lines.append(f"| {row['trial_id']} | {row['status']} | {row['turn_count']} | {row['planner_attempts']} | {row['schema_failure_count']} | {number(row['elapsed_ms'])} |")
    stats = summary["cohorts"]["adversarial"]
    lines += ["", f"Observed ceiling rate: **{stats['ceiling']}/5 ({stats['ceiling']/5*100:.0f}%)**. "
              "Five observations do not establish deterministic behavior."]
    if stats["accepted"] == 5:
        lines += ["The attempted case did not reliably trouble this graph: all five runs were accepted. "
                  "Its intended challenge was resolving conflicting listing claims while ignoring instructions embedded in the data. "
                  "No failure mechanism is inferred from these successful runs."]
    elif all(r["reviewer_attempts"] == 0 and r["schema_failure_count"] == r["turn_count"] for r in adversarial):
        lines += ["All five traces consist entirely of schema-invalid Planner attempts, with no Reviewer execution. "
                  "The Planner repeats the embedded instruction's two-character tags `AI` and `SJ` despite the "
                  "field-specific minimum-length errors. The first response also has only two tags; later responses "
                  "add a third tag while retaining the invalid short tags. This is an observed failure to ignore "
                  "instructions embedded in listing data, not a Reviewer rejection or transport failure. "
                  "The source's amenity contradictions were not the demonstrated stopping cause."]
    else:
        lines += ["The traces below show the actual objections or validation failures. "
                  "Repeated invalid outputs or unresolved review feedback consumed the available turns. "
                  "The observed rate is a sample result, not a deterministic guarantee."]
    lines += ["", "Proposed follow-up fix: strengthen the trusted Planner retry prompt to identify the rejected "
              "short tags explicitly, instruct it to discard embedded formatting demands, and request new "
              "topical tags of 3–30 characters. Keep schema rejection and the turn ceiling; do not pad or "
              "replace tags in Python. Evaluate this prompt change in a separately frozen follow-up campaign; "
              "it was not applied to this baseline.", "", "Actual trace excerpts:", ""]
    for row in adversarial:
        raw = adversarial_raw[row["trial_id"]]
        lines += [f"### {row['trial_id']}", "", f"Run `{raw['run_id']}`; [complete evidence]({relative}/{row['evidence']}).", "", "```json"]
        relevant = [e for e in raw["trace"] if e["outcome"] == "invalid" or e["worker"] == "reviewer"]
        excerpt = [{k:e[k] for k in ("worker","attempt","revision","outcome","raw","error") if k in e}
                   for e in (relevant[:2]+relevant[-1:] if len(relevant)>3 else relevant)]
        lines += [json.dumps(excerpt,ensure_ascii=False,indent=2), "```", ""]
    lines += ["## Evidence and limits", "",
              "All model requests passed through `src/model_client.py`; no measured trial used controlled feedback or scripted output. "
              "Raw responses, validation feedback, terminal JSON, streamed events, stdout/stderr, timestamps, start markers, "
              "exit status, and hashes are retained. Reported token counts may be zero when usage metadata is absent.", "",
              "[Verification](verification_part4.json), [reproduction commands](REPRODUCIBLE_RUN_INSTRUCTIONS.md), "
              "[Part 4 transcript](RUN_LOG_PART4.txt), and [screenshots](screenshots/part4/). "
              "Part 3 evidence remains historical. Final report PDF, personal AI-use answers, combined tagged smoke "
              "verification, collaborator access, and the HW2 submission tag remain whole-assignment tasks.",
              "<!-- PART4:END -->", ""]
    report_dir.mkdir(parents=True,exist_ok=True)
    metrics = report_dir/"METRICS.md"
    section = "\n".join(lines)
    if metrics.exists():
        existing = metrics.read_text()
        if "<!-- PART4:START -->" in existing:
            start = existing.index("<!-- PART4:START -->")
            end = existing.index("<!-- PART4:END -->",start)+len("<!-- PART4:END -->")
            section = existing[:start]+section+existing[end:].lstrip("\n")
        else:
            section = existing.rstrip()+"\n\n"+section
    metrics.write_text(section)
    choice_record = {**choice, "campaign_id":manifest["campaign_id"], "campaign_manifest_sha256":experiments.digest((campaign/"manifest.json").read_bytes()),
                     "evidence":relative+"/summary.json", "command":f".venv-agents/bin/python code/agents_graph.py --input-json reports/hw02/cases/schema_input.json --max-turns {ceiling}"}
    (report_dir/"deployment_choice.json").write_bytes(experiments.json_bytes(choice_record))
    provenance = dict(generated_at=experiments.utc_now(), model_calls=0,
                      calculation_source_fingerprint=manifest["source_fingerprint"],
                      presentation_source="scripts/report_part4.py",
                      presentation_source_sha256=experiments.digest(Path(__file__).read_bytes()),
                      note="Presentation was produced after measurement from verified saved calculations; it does not alter the frozen execution sources.")
    (report_dir/"presentation-provenance.json").write_bytes(experiments.json_bytes(provenance))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign",required=True,type=Path)
    parser.add_argument("--report-dir",default=ROOT/"reports/hw02",type=Path)
    args=parser.parse_args()
    summary=render(args.campaign,args.report_dir)
    print(f"Offline tables: {summary['started']} trials; ceiling {summary['deployment_choice']['max_turns']}")


if __name__ == "__main__":
    main()
