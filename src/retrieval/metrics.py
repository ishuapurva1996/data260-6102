"""Recompute retrieval metrics from saved records and explicit manual labels.

This module deliberately imports no model, vector-store, or network dependency.
Source recall and manually judged answer support measure different properties.
"""

from collections import defaultdict
import math
from statistics import fmean


METRIC_FIELDS = (
    "top1_cosine", "mean_at_k_cosine", "source_recall_at_k",
    "central_support_at_k", "context_support_at_k", "mean_search_latency_ms",
)
CONFIDENT_COSINE_THRESHOLD = 0.50


def _nonempty_string(value, description):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{description} must be a nonempty string")
    return value


def _finite_number(value, description, *, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{description} must be a finite number")
    if nonnegative and value < 0:
        raise ValueError(f"{description} must be nonnegative")
    return value


def _integer(value, description, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{description} must be an integer >= {minimum}")
    return value


def _label_key(label):
    return tuple(_nonempty_string(label.get(name), f"annotation {name}")
                 for name in ("question_id", "technique", "node_id"))


def _annotation_map(annotations):
    if not isinstance(annotations, dict) or not isinstance(annotations.get("annotations"), list):
        raise ValueError("annotations must contain an annotations list")
    result = {}
    for label in annotations["annotations"]:
        if not isinstance(label, dict):
            raise ValueError("each annotation must be an object")
        key = _label_key(label)
        if key in result:
            raise ValueError(f"duplicate annotation: {key}")
        for field in ("central_support", "context_support"):
            if type(label.get(field)) is not bool:
                raise ValueError(f"annotation {key}: {field} must be a boolean")
        for field in ("evidence", "rationale"):
            _nonempty_string(label.get(field), f"annotation {key}: {field}")
        result[key] = label
    return result


def _technique_stats(run):
    techniques = run.get("techniques")
    if not isinstance(techniques, dict) or not techniques:
        raise ValueError("run.techniques must contain at least one technique")
    stats = {}
    for technique, details in techniques.items():
        _nonempty_string(technique, "technique name")
        if not isinstance(details, dict) or not isinstance(details.get("stats"), dict):
            raise ValueError(f"technique {technique} requires stats")
        item = details["stats"]
        _integer(item.get("chunk_count"), f"{technique} chunk_count")
        _finite_number(item.get("average_character_length"),
                       f"{technique} average_character_length", nonnegative=True)
        for field in ("average_token_length", "average_context_character_length",
                      "average_context_token_length", "indexed_truncation_fraction"):
            if field in item:
                _finite_number(item[field], f"{technique} {field}", nonnegative=True)
        stats[technique] = item.copy()
    return stats


def _aggregate(rows, stats):
    question_ids = sorted({row["question_id"] for row in rows})
    techniques = {}
    for technique in sorted(stats):
        selected = [row for row in rows if row["technique"] == technique]
        if not selected:
            continue
        aggregate = {
            "question_count": len(selected),
            "cosine_question_count": sum(row["top1_cosine"] is not None for row in selected),
            "empty_retrieval_count": sum(row["returned_k"] == 0 for row in selected),
            "chunk_count": stats[technique]["chunk_count"],
            "average_character_length": stats[technique]["average_character_length"],
        }
        for field in METRIC_FIELDS:
            values = [row[field] for row in selected if row[field] is not None]
            aggregate[field] = fmean(values) if values else None
        techniques[technique] = aggregate
    return {"question_ids": question_ids, "question_count": len(question_ids), "techniques": techniques}


def summarize(run, records, annotations):
    """Return deterministic per-question and macro metrics; reject incomplete labels.

    ``run`` is run.json, ``records`` is the records.json list, and ``annotations``
    is {"annotations": [...]}. The baseline and diagnostic tables are separate.
    Null cosine values from empty retrieval are omitted from cosine averages;
    ``cosine_question_count`` exposes that denominator. Recall/support still
    include those questions as zero, and latency includes every question.
    """
    if not isinstance(run, dict):
        raise ValueError("run must be an object")
    run_id = _nonempty_string(run.get("run_id"), "run_id")
    stats = _technique_stats(run)
    if not isinstance(records, list) or not records:
        raise ValueError("records must be a nonempty list")
    labels = _annotation_map(annotations)
    seen_labels = set()
    seen_records = set()
    question_contracts = {}
    combinations = defaultdict(set)
    rows, diagnostics, failures = [], [], []

    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each record must be an object")
        question_id = _nonempty_string(record.get("question_id"), "question_id")
        technique = _nonempty_string(record.get("technique"), "technique")
        if technique not in stats:
            raise ValueError(f"unknown technique: {technique}")
        record_key = (question_id, technique)
        if record_key in seen_records:
            raise ValueError(f"duplicate question/technique record: {record_key}")
        seen_records.add(record_key)
        designation = record.get("designation")
        if designation not in ("baseline", "diagnostic"):
            raise ValueError(f"{record_key}: designation must be baseline or diagnostic")
        question = _nonempty_string(record.get("question"), f"{record_key}: question")
        gold_list = record.get("expected_source_ids")
        if not isinstance(gold_list, list) or not gold_list:
            raise ValueError(f"{record_key}: expected_source_ids must be a nonempty list")
        gold = {_nonempty_string(value, f"{record_key}: expected source ID") for value in gold_list}
        if len(gold) != len(gold_list):
            raise ValueError(f"{record_key}: duplicate expected source IDs")
        contract = (question, designation, tuple(sorted(gold)))
        if question_id in question_contracts and question_contracts[question_id] != contract:
            raise ValueError(f"inconsistent question or gold sources across techniques: {question_id}")
        question_contracts[question_id] = contract
        combinations[(designation, question_id)].add(technique)
        requested_k = _integer(record.get("requested_k"), f"{record_key}: requested_k", 1)
        returned_k = _integer(record.get("returned_k"), f"{record_key}: returned_k")
        hits = record.get("hits")
        if not isinstance(hits, list) or returned_k != len(hits) or returned_k > requested_k:
            raise ValueError(f"{record_key}: hits and requested/returned k are inconsistent")
        seconds = record.get("search_seconds")
        if not isinstance(seconds, list) or not seconds:
            raise ValueError(f"{record_key}: search_seconds must contain measured durations")
        for value in seconds:
            _finite_number(value, f"{record_key}: search duration", nonnegative=True)

        cosines, sources, hit_labels, node_ids = [], set(), [], set()
        for position, hit in enumerate(hits, start=1):
            if not isinstance(hit, dict):
                raise ValueError(f"{record_key}: each hit must be an object")
            node_id = _nonempty_string(hit.get("node_id"), f"{record_key}: node_id")
            if node_id in node_ids:
                raise ValueError(f"{record_key}: duplicate returned node_id {node_id}")
            node_ids.add(node_id)
            rank = _integer(hit.get("rank"), f"{record_key}: hit rank", 1)
            if rank != position:
                raise ValueError(f"{record_key}: hit ranks must preserve consecutive store order")
            sources.add(_nonempty_string(hit.get("source_id"), f"{record_key}: source_id"))
            cosine = _finite_number(hit.get("cosine"), f"{record_key}/{node_id}: cosine")
            if cosine < -1.000001 or cosine > 1.000001:
                raise ValueError(f"{record_key}/{node_id}: cosine is outside [-1, 1]")
            if hit.get("store_score") is not None:
                _finite_number(hit["store_score"], f"{record_key}/{node_id}: store_score")
            cosines.append(cosine)
            key = (question_id, technique, node_id)
            if key not in labels:
                raise ValueError(f"missing manual annotation: {key}")
            label = labels[key]
            seen_labels.add(key)
            hit_labels.append(label)
            if hit.get("store_rank", position) == 1 and cosine >= CONFIDENT_COSINE_THRESHOLD and not label["central_support"] and not label["context_support"]:
                failures.append({
                    "question_id": question_id, "question": question, "technique": technique,
                    "designation": designation, "node_id": node_id, "source_id": hit["source_id"],
                    "rank": rank, "store_rank": hit.get("store_rank", position), "cosine": cosine,
                    "retrieved_text": hit.get("retrieved_text", ""),
                    "context_text": hit.get("context_text"),
                    "evidence": label["evidence"], "rationale": label["rationale"],
                })
        if returned_k == 0:
            diagnostics.append(f"{question_id}/{technique}: empty retrieval; cosine undefined, recall/support zero.")
        elif returned_k < requested_k:
            diagnostics.append(f"{question_id}/{technique}: returned {returned_k} of requested {requested_k}; means use actual hits.")
        rows.append({
            "question_id": question_id, "question": question, "technique": technique,
            "designation": designation, "expected_source_ids": sorted(gold),
            "retrieved_gold_source_ids": sorted(sources & gold),
            "requested_k": requested_k, "returned_k": returned_k,
            "top1_cosine": max(cosines) if cosines else None,
            "store_rank1_cosine": next((h["cosine"] for h in hits if h.get("store_rank", h["rank"]) == 1), None),
            "mean_at_k_cosine": fmean(cosines) if cosines else None,
            "source_recall_at_k": len(sources & gold) / len(gold),
            "central_support_at_k": int(any(label["central_support"] for label in hit_labels)),
            "context_support_at_k": int(any(label["context_support"] for label in hit_labels)),
            "mean_search_latency_ms": fmean(seconds) * 1000,
            "search_sample_count": len(seconds),
        })

    orphan_labels = sorted(set(labels) - seen_labels)
    if orphan_labels:
        raise ValueError(f"annotations refer to unreturned nodes: {orphan_labels}")
    for (designation, question_id), actual in sorted(combinations.items()):
        if actual != set(stats):
            raise ValueError(f"{designation} question {question_id}: missing technique records {sorted(set(stats) - actual)}")
    rows.sort(key=lambda row: (row["designation"] != "baseline", row["question_id"], row["technique"]))
    failures.sort(key=lambda row: (row["designation"] != "baseline", row["question_id"], row["technique"]))
    return {
        "schema_version": 1, "run_id": run_id,
        "confidence_threshold": CONFIDENT_COSINE_THRESHOLD,
        "technique_stats": stats,
        "baseline": _aggregate([row for row in rows if row["designation"] == "baseline"], stats),
        "diagnostic": _aggregate([row for row in rows if row["designation"] == "diagnostic"], stats),
        "per_query": rows, "high_score_failures": failures, "diagnostics": sorted(diagnostics),
        "aggregation_note": "Question-level macro averages; diagnostics excluded from baseline. "
                            "Null cosine values are excluded only from cosine averages and their denominator is explicit. "
                            "Empty retrieval counts as zero source recall and answer support.",
    }


def _format(value, digits=4):
    return "n/a" if value is None else f"{value:.{digits}f}"


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_summary(summary):
    """Render the deterministic assignment tables from a summary dictionary."""
    lines = [
        "# HW3 Part 2 retrieval metrics", "", f"Run: `{_cell(summary['run_id'])}`", "",
        "Top-1 cosine means the **maximum explicit cosine among returned hits**, as defined in the assignment; "
        "it may differ from the store's rank-1 cosine. Mean@k uses the actual returned hits. "
        "Source Recall@k counts unique expected source IDs, not chunks. "
        "Central and context answer support are manual judgments; a source hit alone does not prove an answer.", "",
        summary["aggregation_note"], "",
        "Retrieval latency includes only searches with a precomputed query vector; query embedding, "
        "index building, document re-embedding, and printing are excluded.", "",
    ]
    for designation, title in (("baseline", "Baseline questions"), ("diagnostic", "Diagnostic questions")):
        group = summary[designation]
        lines.extend([f"## {title}", "", f"Questions: {group['question_count']}.", ""])
        if not group["question_count"]:
            lines.extend(["No saved questions in this group.", ""])
            continue
        lines.extend([
            "| Technique | Chunks | Avg central chars | Top-1 cosine | Mean@k cosine | Source Recall@k | Central support@k | Context support@k | Search ms | Cosine n |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for technique, row in group["techniques"].items():
            values = [_cell(technique), str(row["chunk_count"]), _format(row["average_character_length"], 1)]
            values.extend(_format(row[field], 4 if field != "mean_search_latency_ms" else 3) for field in METRIC_FIELDS)
            values.append(str(row["cosine_question_count"]))
            lines.append("| " + " | ".join(values) + " |")
        lines.extend(["", "### Per-question results", "",
                      "| Question | Technique | Returned/requested k | Top-1 cosine | Store rank-1 cosine | Mean@k cosine | Source Recall@k | Central support@k | Context support@k | Search ms | Samples |",
                      "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
        for row in summary["per_query"]:
            if row["designation"] != designation:
                continue
            values = [_cell(row["question_id"]), _cell(row["technique"]), f"{row['returned_k']}/{row['requested_k']}",
                      _format(row["top1_cosine"]), _format(row["store_rank1_cosine"]), _format(row["mean_at_k_cosine"]),
                      _format(row["source_recall_at_k"]), str(row["central_support_at_k"]), str(row["context_support_at_k"]),
                      _format(row["mean_search_latency_ms"], 3), str(row["search_sample_count"])]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    lines.extend(["## Confident rank-1 failures", "",
                  f"Predeclared criterion: store rank 1, explicit cosine ≥ {summary['confidence_threshold']:.2f}, "
                  "and manual answer support false in both central text and available context.", ""])
    if summary["high_score_failures"]:
        for failure in summary["high_score_failures"]:
            lines.extend([
                f"- **{_cell(failure['question_id'])} / {_cell(failure['technique'])}** "
                f"({failure['designation']}): cosine {_format(failure['cosine'])}; "
                f"source `{_cell(failure['source_id'])}`, node `{_cell(failure['node_id'])}`. "
                f"Evidence: {_cell(failure['evidence'])} Rationale: {_cell(failure['rationale'])}",
            ])
    else:
        lines.append("No qualifying failure is saved. The required failure example remains incomplete.")
    lines.extend(["", "## Retrieval diagnostics", ""])
    lines.extend(f"- {_cell(note)}" for note in summary["diagnostics"])
    if not summary["diagnostics"]:
        lines.append("All recorded queries returned the requested k.")
    lines.extend(["", "Full chunk lengths, token lengths, truncation audit, manual annotations, and raw result texts "
                  "remain in the run artifacts. These tables are regenerated offline with `code/retrieval_summarize.py`.", ""])
    return "\n".join(lines)
