#!/usr/bin/env python3
"""Read-only, offline Part 4 verification; writes only the requested receipt.

This is not whole-homework/tagged verification. Semantic judgments remain an
identified evaluator's assessment; checks prove consistency and evidence presence.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag.evaluation import (  # noqa: E402
    REFUSAL, analysis_word_count, check_hash_manifest, evaluation_artifacts,
    evidence_span_coverage, invalid_citations, read_json, read_jsonl, sha256, validate_judgments, validate_matrix,
)


def required_demonstration(responses, document):
    """Check the plan's completion criterion, without changing answer metrics.

    The plan includes the four sweep answers in the 22-answer experiment. A
    supported C answer at any measured k can demonstrate answering; Q5/Q6 exact
    refusals must still be demonstrated by their main comparison responses.
    A successful cited C answer is our plan's completion criterion, not an
    explicit assignment minimum. Its semantic assessment comes from the saved
    evaluator judgments; this function does not independently assess truth.
    """
    judged = validate_judgments(responses, document)
    refusal_rows = [r for r in responses if r["phase"] == "main" and r["configuration"] == "C"
                    and r["question_id"] in ("Q5", "Q6")]
    if (len(refusal_rows) != 2 or {r["question_id"] for r in refusal_rows} != {"Q5", "Q6"}
            or any((r.get("answer") or "").strip() != REFUSAL for r in refusal_rows)):
        raise ValueError("C must demonstrate both exact required refusals in the main comparison")
    correct = [r["response_id"] for r in responses if r["phase"] in ("main", "sweep")
               and r["configuration"] == "C" and r["question_id"] in ("Q1", "Q2", "Q3")
               and judged[r["response_id"]]["correct_answer"] and judged[r["response_id"]]["grounded"]]
    if not correct:
        raise ValueError("Plan completion criterion not met: C has no correct, supported, cited answer to an answerable question in the main comparison or sweep (saved semantic evaluation)")
    return {"exact_refusals": ["Q5", "Q6"], "refusal_scope": "main comparison",
            "refusal_basis": "Assignment refusal goal, exercised by the frozen Q5/Q6 cases and exact refusal protocol",
            "correct_supported_answers": correct, "supported_answer_scope": "main comparison or sweep",
            "supported_answer_basis": "Reviewed implementation plan completion criterion; not an explicit assignment minimum",
            "semantic_basis": "Saved evaluator judgments; not independently proven by this verifier"}


def frozen_question_prompt(path: str | Path, function_name: str):
    """Load only a pure, question-only string builder from the frozen pipeline.

    The whitelist prohibits calls, imports, attribute access, evidence lookups,
    and other module execution. Newer working-tree prompt edits cannot change
    verification of an older frozen run.
    """
    tree = ast.parse(Path(path).read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name]
    if len(functions) != 1:
        raise ValueError(f"Expected one frozen {function_name} function")
    function = functions[0]
    if (len(function.args.args) != 1 or function.args.args[0].arg != "question"
            or function.args.posonlyargs or function.args.kwonlyargs or function.args.defaults
            or function.args.vararg or function.args.kwarg or function.decorator_list):
        raise ValueError(f"{function_name} must accept only the question")
    # Annotations need not be executed to reconstruct these pure string builders.
    function.returns = None
    function.args.args[0].annotation = None
    allowed = (ast.FunctionDef, ast.arguments, ast.arg, ast.Expr, ast.Constant, ast.Return,
               ast.JoinedStr, ast.FormattedValue, ast.Name, ast.Load, ast.BinOp, ast.Add)
    if any(not isinstance(node, allowed) for node in ast.walk(function)):
        raise ValueError(f"{function_name} is not a pure question-only string builder")
    if any(isinstance(node, ast.Name) and node.id != "question" for node in ast.walk(function)):
        raise ValueError(f"{function_name} refers to inputs other than the question")
    namespace = {"__builtins__": {}}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[function_name]


def routing_model_config(config, metadata=None):
    """Resolve the explicitly frozen auxiliary model without changing decoding."""
    overlay = config.get("clarification_model", {})
    if not overlay:
        return config
    allowed = {"generator", "generator_digest", "generator_tokenizer", "model_assets_path", "generator_tokenizer_record"}
    if not isinstance(overlay, dict) or set(overlay) != allowed:
        raise ValueError("Explicit clarification_model must contain only the five model/provenance overrides")
    if (not isinstance(overlay["generator_digest"], str) or len(overlay["generator_digest"]) != 64
            or any(c not in "0123456789abcdef" for c in overlay["generator_digest"])):
        raise ValueError("Auxiliary generator requires a pinned SHA-256 digest")
    tokenizer = overlay["generator_tokenizer"]
    if (not isinstance(tokenizer, dict) or not tokenizer.get("model") or not tokenizer.get("cache")
            or not isinstance(tokenizer.get("revision"), str) or len(tokenizer["revision"]) != 40
            or any(c not in "0123456789abcdef" for c in tokenizer["revision"])):
        raise ValueError("Auxiliary generator requires a pinned tokenizer model/revision/cache")
    for identity_key, expected in (("generator_identity", config), ("clarification_generator_identity", overlay)):
        identity = (metadata or {}).get(identity_key, {})
        if (identity.get("model", identity.get("name")) != expected["generator"]
                or (identity.get("name") is not None and identity["name"] != expected["generator"])
                or identity.get("digest") != expected["generator_digest"]):
            raise ValueError(f"{identity_key} model/digest differs from frozen configuration")
    return dict(config, **overlay)


def validate_question_routing(responses, requests, routed, config, routing_prompt, clarification_prompt, *, metadata=None):
    """Audit auxiliary local calls without judging the meaning of their routes."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    routing_config = routing_model_config(config, metadata)
    c_rows = [row for row in responses if row["configuration"] == "C"]
    expected = {f"{row['response_id']}-routing" for row in c_rows}
    require(len(expected) == len(c_rows) == 8, "Expected eight C auxiliary routing calls")
    by_request = {row["routing_id"]: row for row in requests}
    by_routed = {row["routing_id"]: row for row in routed}
    require(set(by_request) == set(by_routed) == expected and len(requests) == len(routed) == 8,
            "Auxiliary routing request/response inventory differs from the eight C answers")
    for final in responses:
        if final["configuration"] != "C":
            require(final.get("routing_id") is None and final.get("routing_decision") is None
                    and final.get("routing_generation_seconds", 0) == 0, "A/B received auxiliary question routing")
            continue
        routing_id = f"{final['response_id']}-routing"
        route, saved = by_routed[routing_id], by_request[routing_id]
        require(all(route.get(key) == value for key, value in saved.items()), "Saved routing request differs from its response record")
        require(route["question_id"] == final["question_id"] and route["question"] == final["question"], "Routing question differs from final question")
        request, raw = route["request"], route.get("raw_response")
        require(request["model"] == routing_config["generator"] and request["options"] == config["options"]
                and request["think"] == config["think"] and request.get("stream") is False,
                "Auxiliary routing generation settings differ from the frozen configuration")
        require(not any(key in request for key in ("context", "messages", "system")), "Routing received hidden history/system context")
        require(request["prompt"] == routing_prompt(final["question"]), "Routing prompt differs from frozen evidence-free question-only builder")
        require(route.get("status") == "complete" and not route.get("error") and raw
                and raw.get("done") and raw.get("done_reason") == "stop" and raw.get("model") == routing_config["generator"],
                "Auxiliary routing call failed, was truncated, or returned a different model")
        bound, prompt_tokens, output_tokens = route.get("prompt_token_bound"), raw.get("prompt_eval_count"), raw.get("eval_count")
        require(all(type(value) is int and value > 0 for value in (bound, prompt_tokens, output_tokens)),
                "Auxiliary routing must record positive integer prompt/API token counts")
        window, output_limit = config["options"]["num_ctx"], config["options"]["num_predict"]
        require(bound + output_limit + 128 <= window and prompt_tokens <= bound + 128
                and output_tokens <= output_limit and prompt_tokens + output_tokens <= window,
                "Auxiliary routing prompt/output token bounds exceed frozen window or output limit")
        require(route["decision"] in ("CLEAR", "CLARIFY") and raw["response"].strip() == route["decision"],
                "Invalid routing output; no silent fallback is allowed")
        require(route["request_saved_at"] <= route["generation_started_at"] <= route["finished_at"]
                <= final["request_saved_at"] <= final["generation_started_at"], "Auxiliary routing was not saved and completed before the final request")
        elapsed = route["generation_seconds"]
        require(isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool)
                and math.isfinite(elapsed) and elapsed >= 0, "Invalid auxiliary generation timing")
        require(final.get("routing_id") == routing_id and final.get("routing_decision") == route["decision"]
                and final.get("routing_generation_seconds") == elapsed, "Final answer routing provenance/timing differs")
        require(final["end_to_end_seconds"] + 1e-6 >= elapsed + final["generation_seconds"],
                "Final end-to-end timing omits auxiliary routing generation")
        if route["decision"] == "CLARIFY":
            require(not final["context"] and not final["context_hits"] and not final["source_labels"]
                    and final["retained_count"] == 0 and final["evidence_token_bound"] == 0,
                    "Clarification answer received evidence context")
            require(final["prompt"] == clarification_prompt(final["question"]), "Clarification prompt differs from frozen question-only builder")
    return {"final_answer_calls": len(responses), "auxiliary_routing_calls": len(routed),
            "total_local_generation_calls": len(responses) + len(routed),
            "answer_generator": config["generator"], "routing_generator": routing_config["generator"],
            "routing_generator_digest": routing_config.get("generator_digest"),
            "limit": "Route/output integrity is automated; whether clarification was appropriate remains semantic evaluation."}


def validate_development_gate(config, calibration, root):
    """Audit the chronology/integrity of the saved assistant assessment, not truth."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    followup = calibration["followup"]
    gate = followup["gate_assessment"]
    require(followup["selected_development_run"] == config["followup_development_run"], "Frozen development run references differ")
    require(config["followup_gate_sha256"] == followup["gate_assessment_sha256"], "Frozen development gate hashes differ")
    require(gate["gate_passed"] is True and gate.get("evaluator") and gate.get("method"), "Development gate lacks a passing identified assistant assessment")
    require(gate["required_supported_cited_demonstrations"] == 2 and gate["supported_cited_answer_demonstrations"] >= 2
            and gate["required_context_appropriate_behavior_count"] == gate["context_appropriate_behavior_count"] == 8,
            "Development assessment does not meet the two supported/eight appropriate behavior gate")
    root = Path(root).resolve()
    development = (root / config["followup_development_run"]).resolve()
    require(development.is_relative_to(root), "Development evidence path escapes repository")
    require(gate["run_id"] == development.name, "Development gate identifies a different run")
    gate_path = development / "gate_assessment.json"
    if gate_path.exists():
        require(sha256(gate_path) == config["followup_gate_sha256"] and read_json(gate_path) == gate,
                "Development gate file differs from the frozen embedded assessment")
    hashes_path = development / "evidence_hashes.json"
    require(sha256(hashes_path) == followup["generation_hash_manifest_sha256"], "Development evidence hash manifest changed")
    hashes = read_json(hashes_path)
    require({"run_metadata.json", "responses.jsonl", "routing_responses.jsonl"} <= hashes.keys(), "Development hash manifest omits required records")
    failures = check_hash_manifest(development, hashes)
    require(not failures, "; ".join(failures))
    metadata = read_json(development / "run_metadata.json")
    require(metadata["status"] == "recorded" and not metadata["live_input_changes_during_run"], "Development run was not completed with unchanged inputs")
    timestamp = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(timestamp(followup["criteria"]["declared_at"]) <= timestamp(metadata["started_at"])
            <= timestamp(metadata["finished_at"]) <= timestamp(gate["assessed_at"]) <= timestamp(config["frozen_at"]),
            "Development criteria/run/assessment did not precede the scored freeze")
    responses, routed = read_jsonl(development / "responses.jsonl"), read_jsonl(development / "routing_responses.jsonl")
    require(len(responses) == len(routed) == 8 and {r["question_id"] for r in responses} == {f"D{i}" for i in range(1, 9)}
            and len({r["response_id"] for r in responses}) == 8
            and {r["routing_id"] for r in routed} == {r["response_id"] + "-routing" for r in responses},
            "Development run must retain eight distinct answers and eight matching routing calls")
    require(all(r.get("status") == "complete" and not r.get("error") and (r.get("raw_response") or {}).get("done")
                and (r.get("raw_response") or {}).get("done_reason") == "stop" for r in responses + routed),
            "Development run contains failed or truncated calls")
    require(sha256(development / "responses.jsonl") == gate["response_file_sha256"]
            and sha256(development / "routing_responses.jsonl") == gate["routing_response_file_sha256"],
            "Development assessment refers to different answer/routing records")
    return {"run_id": development.name, "assessed_at": gate["assessed_at"], "frozen_at": config["frozen_at"],
            "recorded_supported_cited_answers": gate["supported_cited_answer_demonstrations"],
            "recorded_context_appropriate_behaviors": gate["context_appropriate_behavior_count"],
            "gate_file_present": gate_path.exists(), "local_calls": 16,
            "assessment": "Automated chronology/integrity checks of an assistant semantic assessment; semantic truth is not independently verified."}


def verify(run_dir: str | Path, report: str | Path | None = None, *, root: str | Path = ROOT) -> dict:
    run, root = Path(run_dir).resolve(), Path(root).resolve()
    checks = []
    semantic_evaluation = {"source": str(run / "judgments.json"), "evaluator": None, "method": None,
                           "independently_verified_truth": False}
    generation_call_inventory = {"final_answer_calls": 0, "auxiliary_routing_calls": 0,
                                 "total_local_generation_calls": 0}

    def check(name, callback, *, assessment="automated_evidence_consistency"):
        try:
            detail = callback()
            checks.append({"name": name, "assessment": assessment, "passed": True, "detail": detail or "Verified"})
        except (ValueError, AssertionError, KeyError, TypeError, OSError, IndexError) as exc:
            checks.append({"name": name, "assessment": assessment, "passed": False, "detail": str(exc) or type(exc).__name__})

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def hashes():
        manifest = read_json(run / "evidence_hashes.json")
        required = {"responses.jsonl", "requests.jsonl", "retrievals.jsonl", "retrieved_chunks.txt", "RUN_LOG.txt",
                    "chunks.jsonl", "index_audit.json", "gold_chunk_audit.json", "run_metadata.json", "sweep_references.json"}
        require(required <= manifest.keys(), "Evidence hash manifest omits required generation artifacts")
        failures = check_hash_manifest(run, manifest)
        require(not failures, "; ".join(failures))
        return f"{len(manifest)} retained evidence hashes match"

    check("retained_generation_evidence_hashes", hashes)
    try:
        responses, requests = read_jsonl(run / "responses.jsonl"), read_jsonl(run / "requests.jsonl")
        retrievals, chunks = read_jsonl(run / "retrievals.jsonl"), read_jsonl(run / "chunks.jsonl")
        metadata, index = read_json(run / "run_metadata.json"), read_json(run / "index_audit.json")
        sweep = read_json(run / "sweep_references.json")
        config = read_json(run / "frozen/experiment_config.json")
        manifest = read_json(run / "frozen/reports/hw04/part4/CORPUS_MANIFEST.json")
        questions = read_json(run / "frozen/reports/hw04/part4/questions.yaml")["questions"]
    except (ValueError, KeyError, OSError) as exc:
        checks.append({"name": "required_run_files", "assessment": "automated_evidence_consistency",
                       "passed": False, "detail": str(exc)})
        responses = []
    else:
        generation_call_inventory["final_answer_calls"] = len(responses)
        generation_call_inventory["total_local_generation_calls"] = len(responses)

        def frozen():
            failures = check_hash_manifest(run / "frozen", metadata["code_and_input_hashes"])
            require(not failures, "; ".join(failures))
            require(config == metadata["config"], "Frozen and recorded configuration differ")
            require(not metadata["live_input_changes_during_run"], "Inputs changed during scored generation")
            require(config["frozen_at"] <= metadata["started_at"] <= metadata["finished_at"], "Invalid freeze/run ordering")
            require(config["calibration_status"] == "frozen", "Development calibration was not frozen")
            require(sha256(run / "frozen" / config["calibration_path"]) == config["calibration_sha256"], "Calibration hash mismatch")
            if config.get("followup_development_run"):
                gate = validate_development_gate(config, read_json(run / "frozen" / config["calibration_path"]), root)
                return {"frozen_hashes_match": len(metadata["code_and_input_hashes"]), "development_gate": gate,
                        "current_newer_code_allowed": True}
            return f"{len(metadata['code_and_input_hashes'])} frozen code/input hashes match; current newer code is allowed"

        check("frozen_inputs_and_code", frozen)

        def sources():
            rows = manifest["sources"]
            require(len(rows) == manifest["source_count"] == 5, "Exactly five distinct sources required")
            for field in ("source_id", "url", "path", "sha256", "original_sha256"):
                require(len({s[field] for s in rows}) == 5, f"Duplicate source {field}")
            for source in rows:
                path = source["path"]
                require(path.startswith(("reports/hw03/corpus/text/", "reports/hw04/part4/corpus/text/")), "Source outside corpus allowlist")
                for base in (root, run / "frozen"):
                    require(sha256(base / path) == source["sha256"], f"Source changed: {base / path}")
                require(sha256(root / source["original_path"]) == source["original_sha256"], f"Original source changed: {source['source_id']}")
                require(source.get("title") and source.get("version") and source.get("accessed_at"), "Source provenance incomplete")
            return "Five frozen texts and unchanged repository snapshots/originals verified"

        check("five_source_manifest_originals_and_snapshots", sources)

        def chunk_audit():
            require((config["chunk_size"], config["chunk_overlap"], config["chunk_unit"]) == (500, 50, "characters"), "Expected 500/50 character chunk configuration")
            require(len({c["chunk_id"] for c in chunks}) == len(chunks) > 0, "Chunk IDs missing or duplicate")
            text_by_id = {s["source_id"]: (run / "frozen" / s["path"]).read_text() for s in manifest["sources"]}
            hash_by_id = {s["source_id"]: s["sha256"] for s in manifest["sources"]}
            by_source = defaultdict(list)
            for chunk in chunks:
                text = text_by_id[chunk["source_id"]]
                require(chunk["text"] == text[chunk["start"]:chunk["end"]], f"Chunk offsets disagree: {chunk['chunk_id']}")
                require(0 < len(chunk["text"]) == chunk["characters"] <= 500, "Character limit or count invalid")
                require(0 < chunk["embedding_tokens"] <= 256, "Silent embedding truncation possible")
                require(chunk["source_sha256"] == hash_by_id[chunk["source_id"]] and chunk.get("title") and chunk.get("location"), "Missing source metadata")
                require(chunk["requested_overlap"] == 50, "Overlap request differs")
                by_source[chunk["source_id"]].append(chunk)
            for source_id, group in by_source.items():
                group.sort(key=lambda row: row["start"])
                require(group[0]["start"] == 0 and group[-1]["end"] == len(text_by_id[source_id]), "Incomplete source coverage")
                previous = None
                for chunk in group:
                    overlap = previous["end"] - chunk["start"] if previous else 0
                    require(overlap == chunk["actual_overlap"] and overlap >= 0, "Overlap offset mismatch/gap")
                    require(not previous or overlap == 50 or chunk["overlap_deviation"], "Unrecorded overlap deviation")
                    previous = chunk
            require(index["chunk_count"] == len(chunks) and index["source_count"] == len(by_source) == 5, "Index counts disagree")
            require(index["vector_shape"] == [len(chunks), 384], "Actual vector shape disagrees with MiniLM dimension")
            require(index["silent_truncations"] == 0 and index["max_embedding_tokens"] == max(c["embedding_tokens"] for c in chunks), "Token audit mismatch")
            require(index["fingerprint"] == metadata["index_fingerprint"], "Index fingerprint mismatch")
            return f"{len(chunks)} chunks; actual vector shape {index['vector_shape']}; max {index['max_embedding_tokens']} embedding tokens"

        check("chunks_offsets_overlap_metadata_and_real_index", chunk_audit)
        check("main_matrix_and_sweep_reuse", lambda: validate_matrix(responses, sweep))

        def gold():
            audit = read_json(run / "gold_chunk_audit.json")
            ids = {c["chunk_id"] for c in chunks}
            require(audit["Q1"]["single_complete_chunks"], "Q1 missing single-chunk proof")
            require(not audit["Q2"]["single_complete_chunks"] and len(audit["Q2"]["complete_pair"]) == 2,
                    "Q2 must require a pair with no single complete chunk")
            require(set(audit["Q2"]["complete_pair"]) <= ids, "Q2 pair references missing chunks")
            require(len(questions) == 6 and {q["id"] for q in questions} == {f"Q{i}" for i in range(1, 7)}, "Question freeze incomplete")
            require(all(not q["evidence_groups"] for q in questions if q["id"] in ("Q5", "Q6")), "Refusal questions must lack gold evidence")
            source_text = {s["source_id"]: (run / "frozen" / s["path"]).read_text() for s in manifest["sources"]}
            for q in questions[:3]:
                complete = [c["chunk_id"] for c in chunks if all(evidence_span_coverage(q, [c]).values())]
                require(complete == audit[q["id"]]["single_complete_chunks"], "Full-corpus single-chunk coverage does not reconcile")
                for group in q["evidence_groups"]:
                    for span in group["alternatives"]:
                        require(source_text[span["source_id"]][span["start_character"]:span["end_character"]] == span["quote"], "Gold quote differs from frozen source span")
            pair = [c for c in chunks if c["chunk_id"] in audit["Q2"]["complete_pair"]]
            require(all(evidence_span_coverage(next(q for q in questions if q["id"] == "Q2"), pair).values()), "Claimed Q2 pair does not cover required facts")
            return "Recomputed full-corpus Q1/Q2/Q3 single-chunk coverage and Q2 pair; all gold quotes match frozen source spans"

        check("frozen_question_coverage_proof", gold)

        def raw_contract():
            by_retrieval = {row["retrieval_id"]: row for row in retrievals}
            by_request = {row["response_id"]: row for row in requests}
            require(len(by_request) == len(requests) == 22, "Expected 22 independently saved requests")
            runlog = (run / "RUN_LOG.txt").read_text()
            transcript = (run / "retrieved_chunks.txt").read_text()
            question_text = {q["id"]: q["question"] for q in questions}
            chunk_map = {c["chunk_id"]: c for c in chunks}
            for row in responses:
                rid = row["response_id"]
                require(all(row.get(k) == v for k, v in by_request[rid].items()), f"Saved request differs from response record: {rid}")
                require(row["question"] == question_text[row["question_id"]], "Questions changed across calls")
                request = row["request"]
                require(request["model"] == config["generator"] and request["options"] == config["options"] and request["think"] == config["think"], "Generation settings varied")
                require(not any(k in request for k in ("context", "messages", "system")), "Conversation/history leakage")
                require(request["prompt"] == row["prompt"], "Prompt differs from submitted request")
                content_prompt = row.get("content_prompt", row["prompt"])
                require(row["request_saved_at"] <= row["generation_started_at"] <= row["finished_at"], "Request not saved before generation")
                require(row["prompt_token_bound"] + row["answer_token_reserve"] + row["template_margin"] <= row["window"], "Prompt exceeds conservative window budget")
                raw = row.get("raw_response")
                if raw:
                    require(row["answer"] == raw["response"], "Stored model answer has been edited")
                    require(raw["model"] == config["generator"], "Returned model differs")
                require(row["prompt"] in runlog and (row.get("answer") or "") in runlog, "Prompt/output missing from run transcript")
                if row["configuration"] == "A":
                    require(content_prompt == row["question"] and not row["context"] and not row["context_hits"] and not row["source_labels"] and row["retrieval_id"] is None,
                            "A received corpus content or retrieval instructions")
                    continue
                retrieval = by_retrieval[row["retrieval_id"]]
                require(retrieval["retrieved_at"] <= row["generation_started_at"] and retrieval["index_fingerprint"] == index["fingerprint"], "Retrieval after generation or wrong index")
                require(retrieval["requested_k"] == row["requested_k"] and retrieval["returned_count"] == len(retrieval["hits"]) == row["returned_count"], "Retrieval count differs")
                log_end = runlog.index(f"GENERATION START {rid}")
                marker = f"RETRIEVAL {row['question_id']} requested={row['requested_k']} returned={row['returned_count']}"
                log_start = runlog.rfind(marker, 0, log_end)
                require(log_start >= 0 and marker in transcript, "Retrieval not visibly logged before generation")
                for hit in retrieval["hits"]:
                    require(hit["text"] in runlog[log_start:log_end], "Pre-call log missing retrieved text")
                    require(all(hit[k] == v for k, v in chunk_map[hit["chunk_id"]].items()), "Retrieved chunk differs from indexed text/metadata")
                require(row["retained_count"] == len(row["context_hits"]), "Retained count mismatch")
                require({h["chunk_id"] for h in row["context_hits"]} <= {h["chunk_id"] for h in retrieval["hits"]}, "Hidden additional retrieval")
                if row["configuration"] == "B":
                    require(row["context_hits"] == retrieval["hits"], "B raw chunks filtered/reordered")
                else:
                    require(row["evidence_token_bound"] <= config["evidence_budget"], "C evidence budget exceeded")
                    require(list(row["source_labels"].values()) == row["context_hits"], "Source labels differ from supplied context")
                    require(set(row["source_labels"]) == {str(i) for i in range(1, len(row["context_hits"]) + 1)}, "Source labels are not sequential")
                require(all(hit["text"] in row["context"] for hit in row["context_hits"]), "Supplied chunk omitted from prompt context")
            for q in question_text:
                bc = [r for r in responses if r["phase"] == "main" and r["question_id"] == q and r["configuration"] in "BC"]
                require(len(bc) == 2 and bc[0]["retrieval_id"] == bc[1]["retrieval_id"], "B/C raw retrieval IDs differ")
            return "Fresh fixed-setting requests, unedited answers, raw B/C candidates and pre-call retrieval logs verified"

        check("authentic_records_prompts_retrieval_and_call_order", raw_contract)

        if config.get("clarification_preflight", False):
            def routing():
                evidence_hashes = read_json(run / "evidence_hashes.json")
                require({"routing_requests.jsonl", "routing_responses.jsonl"} <= evidence_hashes.keys(),
                        "Auxiliary routing artifacts are missing from the retained evidence hash manifest")
                routing_requests = read_jsonl(run / "routing_requests.jsonl")
                routing_responses = read_jsonl(run / "routing_responses.jsonl")
                generation_call_inventory.update(auxiliary_routing_calls=len(routing_responses),
                                                 total_local_generation_calls=len(responses) + len(routing_responses))
                routing_config = routing_model_config(config, metadata)
                if config.get("clarification_model"):
                    for field in ("model_assets_path", "generator_tokenizer_record"):
                        require(routing_config[field] in metadata["code_and_input_hashes"],
                                "Auxiliary model/tokenizer provenance omitted from frozen input hashes")
                    assets = read_json(run / "frozen" / routing_config["model_assets_path"])
                    tokenizer = read_json(run / "frozen" / routing_config["generator_tokenizer_record"])
                    identity = assets.get("generator_identity", {})
                    require(identity.get("model", identity.get("name")) == routing_config["generator"]
                            and identity.get("digest") == assets.get("manifest_sha256") == routing_config["generator_digest"]
                            and assets.get("local_only") is True, "Frozen auxiliary model assets differ from pinned local model/digest")
                    require(all(tokenizer.get(field) == routing_config["generator_tokenizer"][field] for field in ("model", "revision"))
                            and tokenizer.get("files", {}).get("tokenizer.json")
                            and assets.get("tokenizer") == tokenizer, "Frozen auxiliary tokenizer differs from the configured pinned tokenizer")
                pipeline = run / "frozen/src/rag/pipeline.py"
                return validate_question_routing(responses, routing_requests, routing_responses, config,
                    frozen_question_prompt(pipeline, "clarification_routing_prompt"),
                    frozen_question_prompt(pipeline, "clarification_prompt"), metadata=metadata)

            check("auxiliary_question_routing_integrity_and_timing", routing)

        def completion():
            failed = [{"response_id": r["response_id"], "status": r.get("status"), "error": r.get("error"),
                       "done_reason": (r.get("raw_response") or {}).get("done_reason")} for r in responses
                      if r.get("status") != "complete" or r.get("error") or not (r.get("raw_response") or {}).get("done")
                      or (r.get("raw_response") or {}).get("done_reason") != "stop"]
            require(not failed, f"Incomplete/truncated model calls preserved: {failed}")
            return "22 final-answer generation calls completed without transport failure or token-limit stop; auxiliary calls audited separately when enabled"

        check("all_required_calls_complete", completion)

        def judgments_and_exports():
            document = read_json(run / "judgments.json")
            require(document["run_id"] == run.name, "Judgments identify wrong run")
            semantic_evaluation.update(evaluator=document.get("evaluator"), method=document.get("method"))
            scores = validate_judgments(responses, document)
            by_retrieval = {r["retrieval_id"]: r for r in retrievals}
            by_question = {q["id"]: q for q in questions}
            for response in responses:
                if response["configuration"] == "A" or response["question_id"] not in ("Q1", "Q2", "Q3"):
                    continue
                q = by_question[response["question_id"]]
                raw = by_retrieval[response["retrieval_id"]]
                raw_coverage = evidence_span_coverage(q, raw["hits"])
                final_coverage = evidence_span_coverage(q, response["context_hits"])
                require(raw["evidence_coverage"] == raw_coverage, "Recorded raw evidence coverage disagrees with frozen fact spans")
                score = scores[response["response_id"]]
                require(score["correct_retrieval"] == all(raw_coverage.values()), "Correct-retrieval judgment disagrees with frozen required evidence groups")
                require(score["final_context_coverage"] == all(final_coverage.values()), "Final-context coverage judgment disagrees with frozen required evidence groups")
            for name, expected in evaluation_artifacts(responses, sweep, document).items():
                require((run / name).read_text() == expected, f"Derived table differs from saved judgments: {name}")
            invalid = {r["response_id"]: sorted(invalid_citations(r)) for r in responses if invalid_citations(r)}
            return {"all_22_judgments_and_exports_reconcile": True, "observed_invalid_citations": invalid,
                    "limit": "Semantic correctness/support is evaluator-authored; automation checks consistency and exact support quotes."}

        check("complete_judgments_citations_and_recomputed_tables", judgments_and_exports)

        check("plan_C_supported_answer_and_required_refusals",
              lambda: required_demonstration(responses, read_json(run / "judgments.json")),
              assessment="plan_completion_using_semantic_judgments")

    def report_check():
        require(report is not None, "Report not supplied; analysis proof incomplete")
        count = analysis_word_count(Path(report).read_text())
        require(300 <= count <= 500, f"Analysis has {count} words; expected 300–500")
        return f"{count} analysis words"

    check("report_analysis_300_to_500_words", report_check)

    def screenshots():
        path = root / "reports/hw04/screenshots/part4" / run.name / "manifest.json"
        capture_manifest = read_json(path)
        require(capture_manifest["run_id"] == run.name, "Screenshot manifest identifies wrong run")
        captured_ids, items = set(), set()
        for capture in capture_manifest["captures"]:
            image = (root / capture["path"]).resolve()
            require(image.is_relative_to(root) and image.is_file(), "Screenshot missing or outside repository")
            require(sha256(image) == capture["sha256"], f"Changed screenshot: {capture['path']}")
            require(image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), "Screenshot is not a PNG capture")
            captured_ids.update(capture.get("response_ids", []))
            items.update(capture.get("items", []))
        require({r["response_id"] for r in responses} <= captured_ids and len(captured_ids) >= 22,
                "Screenshots do not cover all 22 distinct outcomes (k=3 may reuse main)")
        require({"R1", "R2", "R6"} <= items, "Missing corpus/index, retrieval, or evaluation capture")
        return f"{len(capture_manifest['captures'])} hashed PNG captures cover all 22 outcomes and setup/retrieval/evaluation"

    check("genuine_screenshot_inventory", screenshots)
    assessment_summary = {
        kind: {"passed": sum(c["passed"] for c in checks if c["assessment"] == kind),
               "total": sum(c["assessment"] == kind for c in checks)}
        for kind in ("automated_evidence_consistency", "plan_completion_using_semantic_judgments")
    }
    return {"schema_version": 1, "scope": "HW4 Part 4 local verification; not final whole-homework/tagged verification",
            "run_id": run.name, "run_path": str(run), "verified_at": datetime.now(timezone.utc).isoformat(),
            "SID4": 6102, "seed": 6102, "VERIFY_SEED": 266102, "network_calls": 0, "model_calls": 0,
            "database_calls": 0, "checks": checks, "passed": sum(c["passed"] for c in checks),
            "total": len(checks), "overall_pass": all(c["passed"] for c in checks),
            "assessment_summary": assessment_summary, "semantic_evaluation": semantic_evaluation,
            "generation_call_inventory": generation_call_inventory,
            "limitations": ["Semantic judgments were authored by the identified evaluator, not independently proven by this verifier.",
                            "A correct supported cited C answer is the reviewed plan's completion criterion, not an explicit assignment minimum.",
                            "PNG hashes establish retained files; genuine capture provenance/readability is documented in the capture manifest and reviewed separately."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    receipt = verify(args.run, args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
    print(f"Part 4: {receipt['passed']}/{receipt['total']} checks; {'PASS' if receipt['overall_pass'] else 'INCOMPLETE/FAIL'}")
    automated = receipt["assessment_summary"]["automated_evidence_consistency"]
    plan = receipt["assessment_summary"]["plan_completion_using_semantic_judgments"]
    print(f"  Automated evidence consistency: {automated['passed']}/{automated['total']}; "
          f"plan completion using saved semantic judgments: {plan['passed']}/{plan['total']}")
    for check in receipt["checks"]:
        if not check["passed"]:
            print(f"  FAIL {check['name']}: {check['detail']}")
    return 0 if receipt["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
