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
    demonstration = required_demonstration(responses, document)
    assert demonstration["correct_supported_answers"] == ["Q2-C-k5"]
    assert "plan completion criterion" in demonstration["supported_answer_basis"]
    assert "not an explicit assignment minimum" in demonstration["supported_answer_basis"]
    assert "Assignment refusal goal" in demonstration["refusal_basis"]
    assert "not independently proven" in demonstration["semantic_basis"]
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


@pytest.fixture
def routed_dataset(dataset):
    responses, _, _ = dataset
    config = dict(generator="local-test-model", options={"seed": 6102, "num_predict": 768, "num_ctx": 4096}, think=False)
    requests, routed = [], []
    for final in responses:
        final.update(question="A test question about its named subject?", request_saved_at="2026-09-28T01:00:03Z",
                     generation_started_at="2026-09-28T01:00:04Z", generation_seconds=1.0,
                     end_to_end_seconds=2.0, prompt="Test answer prompt.")
        if final["configuration"] != "C":
            continue
        decision = "CLARIFY" if final["question_id"] == "Q4" else "CLEAR"
        routing_id = final["response_id"] + "-routing"
        request = dict(model=config["generator"], options=config["options"], think=False, stream=False,
                       prompt=f"Classify the question: {final['question']}")
        saved = dict(routing_id=routing_id, question_id=final["question_id"], question=final["question"],
                     request=request, request_saved_at="2026-09-28T01:00:00Z", prompt_token_bound=100)
        requests.append(copy.deepcopy(saved))
        routed.append(dict(**saved, decision=decision, generation_started_at="2026-09-28T01:00:01Z",
                           finished_at="2026-09-28T01:00:02Z", generation_seconds=0.5, status="complete", error=None,
                           raw_response=dict(model=config["generator"], response=decision, done=True, done_reason="stop",
                                             prompt_eval_count=129, eval_count=2)))
        final.update(routing_id=routing_id, routing_decision=decision, routing_generation_seconds=0.5)
        if decision == "CLARIFY":
            final.update(context="", prompt=f"Ask for the missing subject: {final['question']}")
    return (responses, requests, routed, config,
            lambda question: f"Classify the question: {question}",
            lambda question: f"Ask for the missing subject: {question}")


def test_auxiliary_routing_retains_distinct_call_count_and_provenance(routed_dataset):
    from scripts.verify_hw04_part4 import validate_question_routing

    detail = validate_question_routing(*routed_dataset)
    assert detail["final_answer_calls"] == 22
    assert detail["auxiliary_routing_calls"] == 8
    assert detail["total_local_generation_calls"] == 30
    assert "remains semantic evaluation" in detail["limit"]


@pytest.mark.parametrize("corruption,reason", [
    ("invalid_route", "Invalid routing output"),
    ("evidence_in_prompt", "evidence-free question-only"),
    ("hidden_history", "hidden history/system context"),
    ("missing_timing", "omits auxiliary routing"),
    ("late_route", "before the final request"),
    ("clarify_with_evidence", "Clarification answer received evidence"),
])
def test_auxiliary_routing_rejects_corrupted_evidence_and_accounting(routed_dataset, corruption, reason):
    from scripts.verify_hw04_part4 import validate_question_routing

    responses, requests, routed, *_ = routed_dataset
    first = next(row for row in responses if row["configuration"] == "C")
    if corruption == "invalid_route":
        routed[0]["raw_response"]["response"] = "Probably clear"
    elif corruption == "evidence_in_prompt":
        for row in (requests[0], routed[0]):
            row["request"]["prompt"] += "\nInjected document evidence."
    elif corruption == "hidden_history":
        for row in (requests[0], routed[0]):
            row["request"]["context"] = [1, 2]
    elif corruption == "missing_timing":
        first["end_to_end_seconds"] = first["generation_seconds"]
    elif corruption == "late_route":
        routed[0]["finished_at"] = "2026-09-28T01:00:05Z"
    else:
        final = next(row for row in responses if row["question_id"] == "Q4" and row["configuration"] == "C")
        final["context"] = "Evidence suggesting an arbitrary interpretation."
    with pytest.raises(ValueError, match=reason):
        validate_question_routing(*routed_dataset)


def test_frozen_question_prompt_uses_no_working_tree_or_other_inputs(tmp_path):
    from scripts.verify_hw04_part4 import frozen_question_prompt

    pipeline = tmp_path / "pipeline.py"
    pipeline.write_text('raise RuntimeError("Module body must never execute")\n'
                        'def clarification_prompt(question: str) -> str:\n'
                        '    """Pure frozen question prompt."""\n'
                        '    return f"Clarify the subject: {question}"\n')
    assert frozen_question_prompt(pipeline, "clarification_prompt")("How long?") == "Clarify the subject: How long?"
    pipeline.write_text('def clarification_prompt(question):\n    return evidence + question\n')
    with pytest.raises(ValueError, match="inputs other than the question"):
        frozen_question_prompt(pipeline, "clarification_prompt")
    pipeline.write_text('def clarification_prompt(question):\n    return open("gold.txt").read() + question\n')
    with pytest.raises(ValueError, match="not a pure question-only"):
        frozen_question_prompt(pipeline, "clarification_prompt")


@pytest.fixture
def explicit_routed_dataset(routed_dataset):
    responses, requests, routed, config, *_ = routed_dataset
    config["generator_digest"] = "a" * 64
    config["clarification_model"] = dict(generator="local-auxiliary-model", generator_digest="b" * 64,
        generator_tokenizer=dict(model="Test/Auxiliary", revision="c" * 40, cache=".cache/test"),
        model_assets_path="evidence/auxiliary-assets.json", generator_tokenizer_record="evidence/auxiliary-tokenizer.json")
    metadata = dict(generator_identity=dict(model=config["generator"], digest=config["generator_digest"]),
                    clarification_generator_identity=dict(model="local-auxiliary-model", digest="b" * 64))
    for saved, route in zip(requests, routed):
        saved["request"]["model"] = route["request"]["model"] = "local-auxiliary-model"
        route["raw_response"]["model"] = "local-auxiliary-model"
    return routed_dataset, metadata


def test_explicit_auxiliary_model_is_distinct_without_changing_final_model(explicit_routed_dataset):
    from scripts.verify_hw04_part4 import validate_question_routing

    arguments, metadata = explicit_routed_dataset
    detail = validate_question_routing(*arguments, metadata=metadata)
    assert detail["answer_generator"] == "local-test-model"
    assert detail["routing_generator"] == "local-auxiliary-model"
    assert detail["routing_generator_digest"] == "b" * 64
    assert (detail["final_answer_calls"], detail["auxiliary_routing_calls"], detail["total_local_generation_calls"]) == (22, 8, 30)


@pytest.mark.parametrize("corruption,reason", [
    ("request_model", "generation settings differ"),
    ("response_model", "returned a different model"),
    ("auxiliary_digest", "clarification_generator_identity model/digest"),
    ("answer_digest", "generator_identity model/digest"),
    ("unapproved_options_override", "five model/provenance overrides"),
    ("tokenizer_revision", "pinned tokenizer"),
    ("prompt_bound", "token bounds exceed"),
    ("api_prompt_count", "token bounds exceed"),
    ("api_output_count", "token bounds exceed"),
    ("missing_token_counts", "positive integer prompt/API token counts"),
])
def test_explicit_auxiliary_model_and_token_mismatches_fail(explicit_routed_dataset, corruption, reason):
    from scripts.verify_hw04_part4 import validate_question_routing

    arguments, metadata = explicit_routed_dataset
    _, requests, routed, config, *_ = arguments
    if corruption == "request_model":
        requests[0]["request"]["model"] = routed[0]["request"]["model"] = config["generator"]
    elif corruption == "response_model":
        routed[0]["raw_response"]["model"] = config["generator"]
    elif corruption == "auxiliary_digest":
        metadata["clarification_generator_identity"]["digest"] = "d" * 64
    elif corruption == "answer_digest":
        metadata["generator_identity"]["digest"] = "d" * 64
    elif corruption == "unapproved_options_override":
        config["clarification_model"]["options"] = dict(config["options"], num_predict=3)
    elif corruption == "tokenizer_revision":
        config["clarification_model"]["generator_tokenizer"]["revision"] = "main"
    elif corruption == "prompt_bound":
        requests[0]["prompt_token_bound"] = routed[0]["prompt_token_bound"] = 4096
    elif corruption == "api_prompt_count":
        routed[0]["raw_response"]["prompt_eval_count"] = 500
    elif corruption == "api_output_count":
        routed[0]["raw_response"]["eval_count"] = 769
    else:
        routed[0]["raw_response"].pop("prompt_eval_count")
    with pytest.raises(ValueError, match=reason):
        validate_question_routing(*arguments, metadata=metadata)


@pytest.fixture
def development_gate_dataset(tmp_path):
    development = tmp_path / "development-run"
    development.mkdir()
    def write_json(path, value):
        path.write_text(json.dumps(value, indent=2) + "\n")
    answers, routed = [], []
    for i in range(1, 9):
        common = dict(question_id=f"D{i}", status="complete", error=None, raw_response=dict(done=True, done_reason="stop"))
        answers.append(dict(**common, response_id=f"D{i}-C-k3"))
        routed.append(dict(**common, routing_id=f"D{i}-C-k3-routing"))
    for filename, rows in (("responses.jsonl", answers), ("routing_responses.jsonl", routed)):
        (development / filename).write_text("".join(json.dumps(r) + "\n" for r in rows))
    write_json(development / "run_metadata.json", dict(status="recorded", live_input_changes_during_run=[],
        started_at="2026-09-28T01:00:01Z", finished_at="2026-09-28T01:00:02Z"))
    hashes = {p.name: sha256(p) for p in development.iterdir()}
    write_json(development / "evidence_hashes.json", hashes)
    gate = dict(run_id=development.name, assessed_at="2026-09-28T01:00:03Z", evaluator="Fixture assistant",
        method="Semantic fixture assessment", gate_passed=True, required_supported_cited_demonstrations=2,
        supported_cited_answer_demonstrations=2, required_context_appropriate_behavior_count=8,
        context_appropriate_behavior_count=8, response_file_sha256=sha256(development / "responses.jsonl"),
        routing_response_file_sha256=sha256(development / "routing_responses.jsonl"))
    write_json(development / "gate_assessment.json", gate)
    gate_hash = sha256(development / "gate_assessment.json")
    config = dict(followup_development_run=development.name, followup_gate_sha256=gate_hash,
                  frozen_at="2026-09-28T01:00:04Z")
    calibration = dict(followup=dict(selected_development_run=development.name, gate_assessment=gate,
        gate_assessment_sha256=gate_hash, generation_hash_manifest_sha256=sha256(development / "evidence_hashes.json"),
        criteria=dict(declared_at="2026-09-28T01:00:00Z")))
    return config, calibration, tmp_path


def test_development_gate_checks_saved_assessment_before_freeze_not_semantic_truth(development_gate_dataset):
    from scripts.verify_hw04_part4 import validate_development_gate

    detail = validate_development_gate(*development_gate_dataset)
    assert detail["local_calls"] == 16 and detail["recorded_supported_cited_answers"] == 2
    assert detail["recorded_context_appropriate_behaviors"] == 8
    assert "semantic truth is not independently verified" in detail["assessment"]
    config, _, root = development_gate_dataset
    (root / config["followup_development_run"] / "gate_assessment.json").unlink()
    assert validate_development_gate(*development_gate_dataset)["gate_file_present"] is False


@pytest.mark.parametrize("corruption,reason", [
    ("frozen_before_assessment", "did not precede the scored freeze"),
    ("failed_gate", "passing identified assistant assessment"),
    ("missing_supported_answer", "two supported/eight appropriate"),
    ("different_gate_hash", "gate hashes differ"),
    ("changed_development_answer", "Changed evidence"),
])
def test_development_gate_rejects_changed_failed_or_late_proof(development_gate_dataset, corruption, reason):
    from scripts.verify_hw04_part4 import validate_development_gate

    config, calibration, root = development_gate_dataset
    development = root / config["followup_development_run"]
    if corruption == "frozen_before_assessment":
        config["frozen_at"] = "2026-09-28T01:00:02Z"
    elif corruption == "failed_gate":
        calibration["followup"]["gate_assessment"]["gate_passed"] = False
    elif corruption == "missing_supported_answer":
        calibration["followup"]["gate_assessment"]["supported_cited_answer_demonstrations"] = 1
    elif corruption == "different_gate_hash":
        config["followup_gate_sha256"] = "changed"
    else:
        with (development / "responses.jsonl").open("a") as stream:
            stream.write("{}\n")
    with pytest.raises(ValueError, match=reason):
        validate_development_gate(*development_gate_dataset)
