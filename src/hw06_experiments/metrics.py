"""Manual scoring records and reproducible arithmetic; no model judge."""
import csv
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path

from .design import CONDITIONS, digest, file_hash
from .runner import write_json
from .validation import require, validate_study


def scoring_template(manifest, probes, joined):
    """Copy actual answers and frozen criteria; leave every human score blank."""
    rows = []
    for condition in CONDITIONS:
        answers = joined[condition.id][30:]
        for probe, record in zip(probes["probes"], answers, strict=True):
            client = record["client"]
            answer = client["response"]["reply"]
            rows.append(dict(condition=condition.id, probe_id=probe["id"],
                             request_id=client["context"]["request_id"], answer=answer,
                             answer_sha256=digest(answer), expected_answer=probe["expected_answer"],
                             essential=[dict(criterion=c, assessment=None, explanation="")
                                        for c in probe["essential_criteria"]],
                             full_credit=[dict(criterion=c, assessment=None, explanation="")
                                          for c in probe["full_credit_criteria"]],
                             score=None, explanation="", scorer="", scored_at=None))
    return dict(schema_version="hw06.scores.v1", run_id=manifest["run_id"],
                evidence_kind=manifest["evidence_kind"], input_hashes=manifest["input_hashes"],
                rubric=probes["rubric"], essential_fact_rule=probes["essential_fact_rule"], rows=rows)


def validate_scores(scores, template, probes):
    score_design = {k: v for k, v in scores.items() if k != "rows"}
    frozen_design = {k: v for k, v in template.items() if k != "rows"}
    rubric = score_design.get("rubric")
    frozen_rubric = frozen_design.get("rubric")
    # JSON permits only string object keys; YAML preserves the frozen 1..5 integers.
    if (isinstance(rubric, dict) and isinstance(frozen_rubric, dict)
            and all(type(key) is int for key in frozen_rubric)
            and set(rubric) == {str(key) for key in frozen_rubric}):
        score_design["rubric"] = {int(key): value for key, value in rubric.items()}
    require(score_design == frozen_design, "Scoring design changed")
    require(len(scores["rows"]) == 20, "Need exactly 20 scored probe answers")
    for row, frozen in zip(scores["rows"], template["rows"], strict=True):
        for key in ("condition", "probe_id", "request_id", "answer", "answer_sha256", "expected_answer"):
            require(row[key] == frozen[key], "Answer or scoring identity changed")
        score = row["score"]
        require(type(score) is int and 1 <= score <= 5, "Missing or invalid score")
        require(bool(row["explanation"].strip()) and bool(row["scorer"].strip()), "Human scoring explanation/identity required")
        require(isinstance(row["scored_at"], str) and
                datetime.fromisoformat(row["scored_at"]).utcoffset() is not None, "Aware scoring timestamp required")
        for group in ("essential", "full_credit"):
            require(len(row[group]) == len(frozen[group]), "Criteria count changed")
            for actual, expected in zip(row[group], frozen[group], strict=True):
                require(actual["criterion"] == expected["criterion"], "Criteria changed")
                require(actual["assessment"] in {"correct", "missing", "incorrect"} and
                        bool(actual["explanation"].strip()), "Each criterion needs an assessment and reason")
        essential = [a["assessment"] for a in row["essential"]]
        if "incorrect" in essential:
            require(score <= 2, "Incorrect essential fact scores at most 2")
        if "missing" in essential:
            require(score <= 3, "Missing essential fact scores at most 3")
        if score == 5:
            require(all(a["assessment"] == "correct" for group in ("essential", "full_credit")
                        for a in row[group]), "Full credit requires all criteria")
        if row["probe_id"] == "move_in":
            require(score != 4, "Exact-date probe has no score-4 minor omission")
    return scores["rows"]


def projected_cost(prompt: int, completion: int) -> Decimal:
    """Assigned hypothetical prices, not current provider pricing.

    10,000 conversations * (P*$1 + O*$5) / 1,000,000 tokens.
    P/O are totals for ONE 30-primary-turn conversation. No probes/warmups.
    """
    if type(prompt) is not int or type(completion) is not int or min(prompt, completion) < 0:
        raise ValueError("Nonnegative integer token totals required")
    return Decimal(10000) * (Decimal(prompt) + Decimal(5) * completion) / Decimal(1000000)


def calculate_metrics(manifest, probes, joined, scores):
    template = scoring_template(manifest, probes, joined)
    scored = validate_scores(scores, template, probes)
    rows = []
    for condition in CONDITIONS:
        primary = joined[condition.id][:30]
        require(len(primary) == 30, "30 primary turns required")
        prompt = sum(r["main"].prompt_tokens for r in primary)
        completion = sum(r["main"].completion_tokens for r in primary)
        auxiliary = [event for r in primary for event in r["auxiliary"]]
        embeddings = [event for r in primary for event in r["embeddings"]]
        aux_prompt = sum(e.prompt_tokens for e in auxiliary)
        aux_completion = sum(e.completion_tokens for e in auxiliary)
        quality = [s for s in scored if s["condition"] == condition.id]
        require(len(quality) == 5, "Five scored probes required")
        main_cost = projected_cost(prompt, completion)
        total_cost = projected_cost(prompt + aux_prompt, completion + aux_completion)
        rows.append(dict(condition=condition.id, setting=condition.label,
                         primary_count=30, probe_count=5,
                         prompt_total=prompt, completion_total=completion,
                         mean_prompt_tokens=prompt / 30, mean_completion_tokens=completion / 30,
                         mean_http_latency_ms=sum(r["client"]["http_latency_ms"] for r in primary) / 30,
                         mean_quality=sum(s["score"] for s in quality) / 5,
                         incorrect_essential_fact=any(a["assessment"] == "incorrect" for s in quality for a in s["essential"]),
                         auxiliary_generation_calls=len(auxiliary), auxiliary_prompt_total=aux_prompt,
                         auxiliary_completion_total=aux_completion,
                         main_chat_cost_10000_usd=str(main_cost),
                         main_plus_generative_memory_cost_10000_usd=str(total_cost),
                         embedding_calls=len(embeddings), embedding_input_count=sum(e.input_count for e in embeddings),
                         embedding_latency_ms=sum(e.latency_ms for e in embeddings), embedding_cost_usd=None))
    qualifying = [r for r in rows if r["mean_quality"] >= 4 and not r["incorrect_essential_fact"]]
    by_cost = lambda r: Decimal(r["main_plus_generative_memory_cost_10000_usd"])
    best = min(qualifying, key=by_cost)["condition"] if qualifying else None
    worst = max(rows, key=by_cost)["condition"]
    baseline, policy = rows[1], rows[3]
    savings = (100 * (baseline["prompt_total"] - policy["prompt_total"]) / baseline["prompt_total"]
               if baseline["prompt_total"] else None)
    return dict(schema_version="hw06.metrics.v1", evidence_kind=manifest["evidence_kind"],
                run_id=manifest["run_id"], source_commit=manifest["source_commit"],
                input_hashes=manifest["input_hashes"], pricing=dict(input_usd_per_million=1,
                output_usd_per_million=5, conversations=10000, primary_turns_per_conversation=30,
                excludes=["warmups", "probes", "embedding price (unassigned)"]),
                conditions=rows, policy_comparison=dict(baseline="B", policy="D",
                prompt_savings_percent=savings,
                savings_undefined_reason="zero baseline prompt total" if savings is None else None,
                quality_change=policy["mean_quality"] - baseline["mean_quality"]),
                selection=dict(rule=probes["selection"], best_qualifying=best,
                no_qualifying_setting=best is None, worst_by_cost=worst,
                lowest_quality=min(rows, key=lambda r: r["mean_quality"])["condition"]))


def export_scoring_template(directory: Path, destination: Path, *, count_tokens=None):
    manifest, probes, joined = validate_study(directory, count_tokens=count_tokens)
    with Path(destination).open("x", encoding="utf-8") as stream:
        json.dump(scoring_template(manifest, probes, joined), stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def export_metrics(directory: Path, scores_path: Path, output: Path, *, count_tokens=None):
    manifest, probes, joined = validate_study(directory, count_tokens=count_tokens)
    require(manifest["evidence_kind"] == "measured_http", "Offline fixtures cannot produce measured result tables")
    scores = json.loads(Path(scores_path).read_text())
    result = calculate_metrics(manifest, probes, joined, scores)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result["scores_sha256"] = file_hash(Path(scores_path))
    result["raw_hashes"] = {str(p.relative_to(directory)): file_hash(p) for p in sorted(Path(directory).rglob("*")) if p.is_file()}
    write_json(output / "metrics.json", result)
    write_json(output / "scores.json", scores)
    rows = result["conditions"]
    _csv(output / "memory_cost.csv", rows)
    text = "| Setting | Mean prompt tokens/turn | Mean completion tokens/turn | Mean HTTP latency (ms) | Probe quality (1-5) |\n|---|---:|---:|---:|---:|\n"
    for row in rows:
        text += (f"| {row['setting']} | {row['mean_prompt_tokens']:.3f} | {row['mean_completion_tokens']:.3f} | "
                 f"{row['mean_http_latency_ms']:.3f} | {row['mean_quality']:.2f} |\n")
    (output / "memory_cost.md").write_text(text)
    turns, auxiliary, embeddings = [], [], []
    for records in joined.values():
        for record in records:
            event = record["main"]
            turns.append(dict(**event.context.model_dump(mode="json"),
                              user_id=event.user_id, session_id=event.session_id,
                              http_latency_ms=record["client"]["http_latency_ms"],
                              service_latency_ms=event.latency_ms, prompt_tokens=event.prompt_tokens,
                              completion_tokens=event.completion_tokens, **event.components.model_dump()))
            auxiliary.extend(e.model_dump(mode="json") for e in record["auxiliary"])
            embeddings.extend(e.model_dump(mode="json") for e in record["embeddings"])
    _csv(output / "per_turn.csv", turns)
    write_json(output / "auxiliary_generation.json", auxiliary)
    write_json(output / "embeddings.json", embeddings)
    return result


def _csv(path, rows):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
