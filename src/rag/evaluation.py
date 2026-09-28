"""Offline HW4 scoring exports and integrity checks.

Semantic scores are supplied by an identified human/assistant evaluator. This
module never infers correctness from a source name, calls a model, or changes a
saved response. A zero factual-claim denominator is N/A, not perfect faithfulness.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from src.rag.pipeline import REFUSAL

QUESTIONS = tuple(f"Q{i}" for i in range(1, 7))
ANSWERABLE = frozenset(QUESTIONS[:3])
REFUSAL_QUESTIONS = frozenset(QUESTIONS[4:])
JUDGMENT_FIELDS = (
    "correct_retrieval", "final_context_coverage", "correct_answer", "grounded",
    "refused_when_needed", "semantic_refusal", "exact_refusal", "supported_claims",
    "total_claims", "format_compliance", "reasons", "claims",
)


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def citation_numbers(answer: str) -> set[str]:
    """Accept [1], [1, 2] and [1][2]; prose numbers are not citations."""
    return {number for group in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", answer or "")
            for number in re.findall(r"\d+", group)}


def invalid_citations(response: Mapping) -> set[str]:
    return citation_numbers(response.get("answer") or "") - set(response.get("source_labels", {}))


def evidence_span_coverage(question: Mapping, hits: Sequence[Mapping]) -> dict[str, bool]:
    """Independently check frozen fact spans, with AND groups and OR alternatives."""
    def covered(span):
        cursor, end = span["start_character"], span["end_character"]
        intervals = sorted((h["start"], h["end"]) for h in hits if h["source_id"] == span["source_id"])
        for start, stop in intervals:
            if start <= cursor < stop:
                cursor = stop
            if cursor >= end:
                return True
        return False
    return {group["id"]: any(covered(span) for span in group["alternatives"])
            for group in question["evidence_groups"]}


def validate_matrix(responses: Sequence[Mapping], sweep: Sequence[Mapping]) -> None:
    ids = [row["response_id"] for row in responses]
    if len(ids) != 22 or len(set(ids)) != 22:
        raise ValueError("Expected exactly 22 unique responses (18 main and four sweep)")
    main = [row for row in responses if row["phase"] == "main"]
    pairs = [(row["question_id"], row["configuration"]) for row in main]
    expected = {(q, c) for q in QUESTIONS for c in "ABC"}
    if len(main) != 18 or set(pairs) != expected or len(set(pairs)) != 18:
        raise ValueError("Missing or duplicate main question/configuration pair")
    for row in main:
        if row["requested_k"] != (0 if row["configuration"] == "A" else 3):
            raise ValueError("Main matrix requires A k=0 and B/C k=3")
    extras = [row for row in responses if row["phase"] == "sweep"]
    if {(r["question_id"], r["configuration"], r["requested_k"]) for r in extras} != {
        ("Q2", c, k) for c in "BC" for k in (1, 5)
    } or len(extras) != 4:
        raise ValueError("Expected four additional Q2 B/C k=1,5 responses")
    if len(sweep) != 6 or {(r["question_id"], r["configuration"], r["k"]) for r in sweep} != {
        ("Q2", c, k) for c in "BC" for k in (1, 3, 5)
    }:
        raise ValueError("Expected exactly six Q2 B/C sweep references")
    lookup = {r["response_id"]: r for r in responses}
    for ref in sweep:
        row = lookup.get(ref["response_id"])
        if not row or (row["question_id"], row["configuration"], row["requested_k"]) != (
            ref["question_id"], ref["configuration"], ref["k"]
        ) or ref["reused_main"] is not (ref["k"] == 3) or (row["phase"] == "main") is not ref["reused_main"]:
            raise ValueError("Sweep must reference existing k=3 main responses without regeneration")


def validate_judgments(responses: Sequence[Mapping], document: Mapping) -> dict[str, dict]:
    if document.get("schema_version") != 1 or not document.get("evaluator") or not document.get("method"):
        raise ValueError("Judgments require schema_version=1, evaluator, and method")
    rows = document.get("responses", [])
    ids = [row.get("response_id") for row in rows]
    if len(ids) != len(responses) or len(ids) != len(set(ids)) or set(ids) != {r["response_id"] for r in responses}:
        raise ValueError("Every response must have one and only one semantic judgment")
    lookup = {row["response_id"]: dict(row) for row in rows}
    for response in responses:
        row = lookup[response["response_id"]]
        missing = set(JUDGMENT_FIELDS) - row.keys()
        if missing:
            raise ValueError(f"{response['response_id']}: missing judgments {sorted(missing)}")
        reasons = row["reasons"]
        if not isinstance(reasons, dict) or any(not isinstance(reasons.get(k), str) or not reasons[k].strip()
                                                for k in ("retrieval", "answer", "grounding", "refusal", "format")):
            raise ValueError("Every required judgment needs a substantive reason, including N/A")
        config, question = response["configuration"], response["question_id"]
        for field in ("correct_answer", "semantic_refusal", "exact_refusal", "format_compliance"):
            if type(row[field]) is not bool:
                raise ValueError(f"{field} must be a boolean")
        for field in ("correct_retrieval", "final_context_coverage"):
            applicable = config != "A" and question in ANSWERABLE
            if (type(row[field]) is not bool) if applicable else (row[field] is not None):
                raise ValueError(f"{field} must be bool for answerable B/C and null otherwise")
        if question in REFUSAL_QUESTIONS:
            if type(row["refused_when_needed"]) is not bool or row["refused_when_needed"] != row["semantic_refusal"]:
                raise ValueError("Required refusal judgment must equal semantic refusal")
            if row["correct_answer"] != row["semantic_refusal"]:
                raise ValueError("Q5/Q6 accuracy must reflect refusal, not recalled facts")
            if row["format_compliance"] and not row["exact_refusal"]:
                raise ValueError("Q5/Q6 format compliance requires the exact refusal")
        elif row["refused_when_needed"] is not None:
            raise ValueError("Refused-when-needed is null for Q1-Q4")
        exact = (response.get("answer") or "").strip() == REFUSAL
        if row["exact_refusal"] != exact or (exact and not row["semantic_refusal"]):
            raise ValueError("Exact-refusal judgment disagrees with unedited response")
        if question in ANSWERABLE and row["semantic_refusal"] and row["correct_answer"]:
            raise ValueError("Unnecessary refusal cannot be a correct answer to an answerable question")
        if invalid_citations(response) and (row["grounded"] is True or row["format_compliance"]):
            raise ValueError("Broken source citations cannot be grounded or format-compliant")
        claims = row["claims"]
        if not isinstance(claims, list):
            raise ValueError("claims must be an explicit list")
        if config == "A":
            if row["grounded"] is not None and row["grounded"] is not False:
                raise ValueError("A cannot demonstrate corpus grounding without supplied evidence")
            if any(row[f] is not None for f in ("supported_claims", "total_claims")) or claims:
                raise ValueError("A has no supplied context: claim faithfulness must be N/A")
            continue
        if type(row["total_claims"]) is not int or type(row["supported_claims"]) is not int:
            raise ValueError("B/C require explicit factual claim counts, including 0/0")
        if row["total_claims"] != len(claims) or not 0 <= row["supported_claims"] <= row["total_claims"]:
            raise ValueError("Factual claim counts do not match claim audit")
        supplied = {hit["chunk_id"]: hit["text"] for hit in response.get("context_hits", [])}
        for claim in claims:
            if type(claim.get("supported")) is not bool or not claim.get("claim") or not claim.get("reason"):
                raise ValueError("Each factual claim needs supported, claim, and reason")
            supports = claim.get("support", [])
            if claim["supported"] and not supports:
                raise ValueError("Supported claims require exact supplied evidence quotes")
            for support in supports:
                if not support.get("quote") or support["quote"] not in supplied.get(support.get("chunk_id"), ""):
                    raise ValueError("Claim support quote is absent from the actual supplied context")
        if sum(c["supported"] for c in claims) != row["supported_claims"]:
            raise ValueError("Supported claim count does not match claim audit")
        if not claims:
            if row["grounded"] is not None:
                raise ValueError("A refusal/clarification with no factual claims has N/A grounding")
        elif type(row["grounded"]) is not bool:
            raise ValueError("Substantive B/C answers need a grounding judgment")
        if row["grounded"] and (not citation_numbers(response.get("answer") or "") or
                                row["supported_claims"] != row["total_claims"]):
            raise ValueError("Grounded answers require valid citations and support for every claim")
        if claims and row["format_compliance"] and not citation_numbers(response.get("answer") or ""):
            raise ValueError("Factual answer format requires source-number citations")
        if row["grounded"]:
            cited_chunks = {response["source_labels"][label]["chunk_id"]
                            for label in citation_numbers(response.get("answer") or "")}
            if any(not any(support["chunk_id"] in cited_chunks for support in claim["support"]) for claim in claims):
                raise ValueError("Grounded claims must be supported by a chunk actually cited")
    return lookup


def fraction(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator if denominator else None, "denominator": denominator,
            "value": numerator / denominator if denominator else None,
            "display": f"{numerator}/{denominator}" if denominator else "N/A"}


def summarize(responses: Sequence[Mapping], judgments: Mapping[str, Mapping]) -> dict:
    """Summarize only the 18 main rows; a repeated sweep reference adds no weight."""
    result = {}
    for config in "ABC":
        rows = [r for r in responses if r["phase"] == "main" and r["configuration"] == config]
        scores = [judgments[r["response_id"]] for r in rows]
        def metric(field, questions=None):
            vals = [judgments[r["response_id"]][field] for r in rows
                    if questions is None or r["question_id"] in questions]
            vals = [v for v in vals if v is not None]
            return fraction(sum(vals), len(vals))
        factual = [s for s in scores if s["total_claims"] is not None]
        result[config] = {
            "correct_retrieval": metric("correct_retrieval", ANSWERABLE),
            "final_context_coverage": metric("final_context_coverage", ANSWERABLE),
            "accuracy": metric("correct_answer"),
            "answerable_accuracy": metric("correct_answer", ANSWERABLE),
            "faithfulness": fraction(sum(s["supported_claims"] for s in factual), sum(s["total_claims"] for s in factual)),
            "format_compliance": metric("format_compliance"),
            "robustness": metric("correct_answer", set(QUESTIONS[3:])),
            "required_refusal": metric("refused_when_needed", REFUSAL_QUESTIONS),
            "exact_required_refusal": metric("exact_refusal", REFUSAL_QUESTIONS),
        }
    return result


def _csv(rows: Sequence[Mapping]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list))
                         else "N/A" if value is None else value for key, value in row.items()})
    return stream.getvalue()


def evaluation_artifacts(responses: Sequence[Mapping], sweep: Sequence[Mapping], document: Mapping) -> dict[str, str]:
    validate_matrix(responses, sweep)
    judgments = validate_judgments(responses, document)
    summary = {"schema_version": 1, "run_id": document.get("run_id"), "evaluator": document["evaluator"],
               "method": document["method"], "main_response_count": 18, "distinct_response_count": 22,
               "sweep_reference_count": 6, "configurations": summarize(responses, judgments)}
    evaluation = []
    lookup = {r["response_id"]: r for r in responses}
    for row in responses:
        evaluation.append({"response_id": row["response_id"], "phase": row["phase"],
                           "question_id": row["question_id"], "configuration": row["configuration"],
                           "k": row["requested_k"], **judgments[row["response_id"]],
                           "invalid_citations": sorted(invalid_citations(row)), "status": row.get("status")})
    comparison = []
    for question in QUESTIONS:
        item = {"question_id": question}
        for config in "ABC":
            row = next(r for r in responses if r["phase"] == "main" and r["question_id"] == question and r["configuration"] == config)
            item.update({f"{config}_response_id": row["response_id"], f"{config}_answer": row.get("answer"),
                         f"{config}_correct": judgments[row["response_id"]]["correct_answer"],
                         f"{config}_grounded": judgments[row["response_id"]]["grounded"]})
        comparison.append(item)
    sweep_rows = []
    for ref in sweep:
        row, score = lookup[ref["response_id"]], judgments[ref["response_id"]]
        sweep_rows.append({**ref, "returned_count": row["returned_count"], "retained_count": row["retained_count"],
                           "context_chunk_ids": [h["chunk_id"] for h in row["context_hits"]],
                           "evidence_token_bound": row["evidence_token_bound"],
                           "prompt_eval_tokens": (row.get("raw_response") or {}).get("prompt_eval_count"),
                           "output_tokens": (row.get("raw_response") or {}).get("eval_count"),
                           "generation_seconds": row.get("generation_seconds"), "answer": row.get("answer"),
                           **{k: score[k] for k in JUDGMENT_FIELDS if k not in ("claims",)}})
    summary_rows = []
    for config, metrics in summary["configurations"].items():
        row = {"configuration": config}
        for metric, values in metrics.items():
            row[metric] = values["display"]
            row[f"{metric}_numerator"] = values["numerator"]
            row[f"{metric}_denominator"] = values["denominator"]
        summary_rows.append(row)
    return {"evaluation.csv": _csv(evaluation), "comparison.csv": _csv(comparison),
            "k_sweep.csv": _csv(sweep_rows), "evaluation_summary.csv": _csv(summary_rows),
            "summary.json": json.dumps(summary, ensure_ascii=False, indent=2) + "\n"}


def write_evaluation(run_dir: str | Path, judgments_path: str | Path | None = None) -> dict:
    run = Path(run_dir)
    artifacts = evaluation_artifacts(read_jsonl(run / "responses.jsonl"), read_json(run / "sweep_references.json"),
                                     read_json(judgments_path or run / "judgments.json"))
    for name, content in artifacts.items():
        (run / name).write_text(content, encoding="utf-8")
    return json.loads(artifacts["summary.json"])


def check_hash_manifest(directory: str | Path, hashes: Mapping[str, str]) -> list[str]:
    root = Path(directory).resolve()
    failures = []
    for relative, expected in hashes.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            failures.append(f"Missing or escaped evidence: {relative}")
        elif sha256(path) != expected:
            failures.append(f"Changed evidence: {relative}")
    return failures


def analysis_word_count(report_text: str) -> int:
    """Count only the explicitly delimited analysis prose, not tables/code."""
    marked = re.search(r"<!--\s*ANALYSIS_START\s*-->(.*?)<!--\s*ANALYSIS_END\s*-->", report_text, re.S | re.I)
    if marked:
        prose = marked.group(1)
    else:
        section = re.search(r"^#{1,6}\s+[^\n]*\banalysis\b[^\n]*\n(.*?)(?=^#{1,6}\s|\Z)", report_text, re.S | re.M | re.I)
        if not section:
            raise ValueError("Report needs an Analysis heading or ANALYSIS_START/ANALYSIS_END comments")
        prose = section.group(1)
    prose = re.sub(r"```.*?```|<!--.*?-->", "", prose, flags=re.S)
    prose = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", prose)
    return len(prose.split())
