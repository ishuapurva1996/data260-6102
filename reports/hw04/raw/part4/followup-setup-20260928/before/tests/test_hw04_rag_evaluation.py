"""Offline evaluation tests; fixtures never count as real experiment evidence."""
import copy
import json

import pytest

from src.rag.evaluation import (
    REFUSAL, analysis_word_count, check_hash_manifest, evaluation_artifacts,
    evidence_span_coverage, invalid_citations, sha256, summarize, validate_judgments, validate_matrix,
)


@pytest.fixture
def dataset():
    responses, scores, sweep = [], [], []
    pairs = [(f"Q{i}", c, 0 if c == "A" else 3, "main") for i in range(1, 7) for c in "ABC"]
    pairs += [("Q2", c, k, "sweep") for c in "BC" for k in (1, 5)]
    for q, c, k, phase in pairs:
        rid = f"{q}-{c}-k{k}"
        response = dict(response_id=rid, question_id=q, configuration=c, requested_k=k, phase=phase,
                        answer=REFUSAL, context_hits=[], source_labels={}, returned_count=k, retained_count=0,
                        evidence_token_bound=0, raw_response={}, status="complete")
        score = dict(response_id=rid, correct_retrieval=False if q in ("Q1", "Q2", "Q3") and c != "A" else None,
                     final_context_coverage=False if q in ("Q1", "Q2", "Q3") and c != "A" else None,
                     correct_answer=q in ("Q5", "Q6"), grounded=None,
                     refused_when_needed=True if q in ("Q5", "Q6") else None,
                     semantic_refusal=True, exact_refusal=True, supported_claims=None if c == "A" else 0,
                     total_claims=None if c == "A" else 0, format_compliance=True, claims=[],
                     reasons={name: "Fixture explanation of applicable score or N/A." for name in ("retrieval", "answer", "grounding", "refusal", "format")})
        if q == "Q4":
            response["answer"] = "What do you want to file?"
            score.update(correct_answer=True, semantic_refusal=False, exact_refusal=False)
        responses.append(response)
        scores.append(score)
    for c in "BC":
        for k in (1, 3, 5):
            sweep.append(dict(question_id="Q2", configuration=c, k=k, response_id=f"Q2-{c}-k{k}", reused_main=k == 3))
    return responses, sweep, dict(schema_version=1, run_id="fixture", evaluator="test fixture", method="manual fixture", responses=scores)


def test_matrix_rejects_missing_duplicate_and_wrong_k3_reference(dataset):
    responses, sweep, _ = dataset
    validate_matrix(responses, sweep)
    with pytest.raises(ValueError, match="22 unique"):
        validate_matrix(responses[:-1], sweep)
    bad = copy.deepcopy(responses)
    bad[1] = bad[0]
    with pytest.raises(ValueError, match="22 unique"):
        validate_matrix(bad, sweep)
    bad = copy.deepcopy(sweep)
    bad[1]["reused_main"] = False
    with pytest.raises(ValueError, match="without regeneration"):
        validate_matrix(responses, bad)


def test_main_pair_cannot_be_replaced_by_an_extra_response(dataset):
    responses, sweep, _ = dataset
    responses[0]["question_id"] = "Q2"
    with pytest.raises(ValueError, match="question/configuration"):
        validate_matrix(responses, sweep)


def test_na_denominators_and_all_refusal_do_not_reward_inability(dataset):
    responses, _, document = dataset
    scores = validate_judgments(responses, document)
    summary = summarize(responses, scores)
    for config in "ABC":
        assert summary[config]["accuracy"]["display"] == "3/6"
        assert summary[config]["answerable_accuracy"]["display"] == "0/3"
        assert summary[config]["faithfulness"]["display"] == "N/A"
        assert summary[config]["faithfulness"]["value"] is None
        assert summary[config]["required_refusal"]["display"] == "2/2"
    assert summary["A"]["correct_retrieval"]["denominator"] == 0
    assert summary["B"]["correct_retrieval"]["denominator"] == 3


def test_unnecessary_refusal_cannot_be_scored_correct(dataset):
    responses, _, document = dataset
    document["responses"][0]["correct_answer"] = True
    with pytest.raises(ValueError, match="Unnecessary refusal"):
        validate_judgments(responses, document)


def test_broken_citations_are_detected_and_cannot_be_scored_grounded(dataset):
    responses, _, document = dataset
    row, score = responses[2], document["responses"][2]
    row["answer"] = "The deadline is 14 days [9]."
    score.update(semantic_refusal=False, exact_refusal=False, grounded=True)
    assert invalid_citations(row) == {"9"}
    with pytest.raises(ValueError, match="Broken source citations"):
        validate_judgments(responses, document)


def test_support_requires_exact_quote_in_actual_context(dataset):
    responses, _, document = dataset
    row, score = responses[2], document["responses"][2]
    hit = dict(chunk_id="fact", text="The deadline is 14 days.")
    row.update(answer="The deadline is 14 days [1].", context_hits=[hit], source_labels={"1": hit})
    score.update(semantic_refusal=False, exact_refusal=False, grounded=True, correct_answer=True,
                 supported_claims=1, total_claims=1, claims=[dict(claim="14-day deadline", supported=True,
                 support=[dict(chunk_id="fact", quote="The deadline is 14 days.")], reason="Exact supplied fact.")])
    validate_judgments(responses, document)
    score["claims"][0]["support"][0]["quote"] = "The deadline is 30 days."
    with pytest.raises(ValueError, match="actual supplied context"):
        validate_judgments(responses, document)


def test_support_faithfulness_counts_claims_and_excludes_sweep(dataset):
    responses, sweep, document = dataset
    for row, score in zip(responses, document["responses"]):
        if row["configuration"] == "C" and row["question_id"] == "Q2":
            hit = dict(chunk_id="fact", text="A supported statement.")
            row.update(answer="A supported statement. An unsupported assertion.", context_hits=[hit])
            score.update(semantic_refusal=False, exact_refusal=False, grounded=False, format_compliance=False,
                         supported_claims=1, total_claims=2, claims=[
                             dict(claim="supported", supported=True, support=[dict(chunk_id="fact", quote="A supported statement.")], reason="Same fact."),
                             dict(claim="unsupported", supported=False, support=[], reason="Missing evidence.")])
    artifacts = evaluation_artifacts(responses, sweep, document)
    summary = json.loads(artifacts["summary.json"])
    assert summary["configurations"]["C"]["faithfulness"]["display"] == "1/2"
    assert len(artifacts) == 5
    assert "N/A" in artifacts["evaluation_summary.csv"]


def test_judgments_require_complete_reasons_and_no_duplicate_rows(dataset):
    responses, _, document = dataset
    document["responses"][0]["reasons"]["answer"] = ""
    with pytest.raises(ValueError, match="reason"):
        validate_judgments(responses, document)
    document["responses"][0] = document["responses"][1]
    with pytest.raises(ValueError, match="one and only one"):
        validate_judgments(responses, document)


def test_na_is_not_false_and_exact_refusal_is_measured(dataset):
    responses, _, document = dataset
    document["responses"][0]["correct_retrieval"] = False
    with pytest.raises(ValueError, match="null otherwise"):
        validate_judgments(responses, document)
    document["responses"][0]["correct_retrieval"] = None
    responses[0]["answer"] += "."
    with pytest.raises(ValueError, match="Exact-refusal"):
        validate_judgments(responses, document)


def test_changed_missing_and_escaped_evidence_are_detected(tmp_path):
    original = tmp_path / "responses.jsonl"
    original.write_text("Unedited evidence")
    hashes = {original.name: sha256(original)}
    assert check_hash_manifest(tmp_path, hashes) == []
    original.write_text("Replacement answer")
    assert "Changed evidence" in check_hash_manifest(tmp_path, hashes)[0]
    original.unlink()
    assert "Missing" in check_hash_manifest(tmp_path, hashes)[0]
    assert "escaped" in check_hash_manifest(tmp_path, {"../elsewhere": "hash"})[0]


def test_analysis_word_count_excludes_other_report_material():
    report = "# Setup\nExtra words here.\n<!-- ANALYSIS_START -->\n" + "word " * 400 + "\n<!-- ANALYSIS_END -->\nOther material."
    assert analysis_word_count(report) == 400
    assert analysis_word_count("## Analysis\nOne two three.\n## Evidence\nNot counted.") == 3
    with pytest.raises(ValueError, match="Analysis"):
        analysis_word_count("No designated section.")


def test_coverage_requires_complete_fact_span_and_can_join_overlapping_chunks():
    q = dict(evidence_groups=[dict(id="fact", alternatives=[dict(source_id="one", start_character=100, end_character=150)])])
    assert evidence_span_coverage(q, [dict(source_id="one", start=0, end=99)]) == {"fact": False}
    assert evidence_span_coverage(q, [dict(source_id="one", start=90, end=120), dict(source_id="one", start=120, end=160)]) == {"fact": True}
    assert evidence_span_coverage(q, [dict(source_id="one", start=90, end=119), dict(source_id="one", start=120, end=160)]) == {"fact": False}


def test_supported_sweep_satisfies_demo_without_changing_main_metrics(dataset):
    from scripts.verify_hw04_part4 import required_demonstration

    responses, _, document = dataset
    row = next(r for r in responses if r["response_id"] == "Q2-C-k5")
    score = next(r for r in document["responses"] if r["response_id"] == row["response_id"])
    hit = dict(chunk_id="fact", text="A supported fact.")
    row.update(answer="A supported fact [1].", context_hits=[hit], source_labels={"1": hit})
    score.update(correct_answer=True, grounded=True, semantic_refusal=False, exact_refusal=False,
                 supported_claims=1, total_claims=1, claims=[dict(claim="A supported fact", supported=True,
                 support=[dict(chunk_id="fact", quote="A supported fact.")], reason="Matches cited evidence.")])
    before = summarize(responses, validate_judgments(responses, document))
    assert required_demonstration(responses, document)["correct_supported_answers"] == ["Q2-C-k5"]
    assert before["C"]["answerable_accuracy"]["display"] == "0/3"
    assert summarize(responses, validate_judgments(responses, document)) == before

    unsupported = copy.deepcopy(document)
    bad = next(r for r in unsupported["responses"] if r["response_id"] == row["response_id"])
    bad.update(grounded=False, supported_claims=0)
    bad["claims"][0].update(supported=False, support=[], reason="Unsupported assertion.")
    with pytest.raises(ValueError, match="no correct, supported, cited answer"):
        required_demonstration(responses, unsupported)

    refusal = next(r for r in responses if r["response_id"] == "Q5-C-k3")
    refusal["answer"] = REFUSAL + "."
    next(r for r in document["responses"] if r["response_id"] == refusal["response_id"]).update(
        exact_refusal=False, format_compliance=False)
    with pytest.raises(ValueError, match="both exact required refusals in the main"):
        required_demonstration(responses, document)
