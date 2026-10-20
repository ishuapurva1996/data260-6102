"""Deliberate small offline fixtures; no measured model results or result tables."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.hw06_experiments.design import CONDITIONS, load_design
from src.hw06_experiments.metrics import (calculate_metrics, export_metrics,
    export_scoring_template, projected_cost, scoring_template)
from src.hw06_experiments.runner import RequestFailed, StudyRunner, read_jsonl
from src.hw06_experiments.validation import validate_study
from src.hw06_shared.config import HW6Config
from src.hw06_shared.telemetry import CallEvent, JsonlTelemetry, TokenComponents, PromptText


class FixtureEndpoint:
    def __init__(self, config, directory, *, fail=False):
        self.config, self.sink, self.fail = config, JsonlTelemetry(directory / "events.jsonl"), fail
        self.requests = []

    def configuration(self):
        return self.config.public_dict()

    def chat(self, request, context):
        if self.fail:
            raise RequestFailed(503, {"code": "model_unavailable"}, "model_unavailable")
        self.requests.append((request, context))
        common = dict(context=context, started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                      user_id=request.user_id, session_id=request.session_id, latency_ms=5,
                      config=self.config.public_dict())
        self.sink.emit(CallEvent(**common, kind="embedding", operation="query",
                                 embedding_dimension=768, input_count=1, usage_source="not_applicable"))
        self.sink.emit(CallEvent(**common, kind="generation", operation="extraction",
                                 prompt_tokens=10, completion_tokens=2, usage_source="model_reported"))
        if context.phase == "primary" and context.turn_id % 5 == 0:
            self.sink.emit(CallEvent(**common, kind="generation", operation="session_summary",
                                     prompt_tokens=20, completion_tokens=3, usage_source="model_reported"))
        prompt = {"A": 100, "B": 200, "C": 300, "D": 120}[context.condition]
        self.sink.emit(CallEvent(**common, kind="request", operation="chat", prompt_tokens=prompt,
                                 completion_tokens=20, total_tokens=prompt+20, usage_source="model_reported",
                                 components=TokenComponents(current_message=len(request.message),
                                 template_residual=prompt-len(request.message), tokenizer_identity="fixture-counter"),
                                 component_text=PromptText(current_message=request.message)))
        probes = load_design()[1]["probes"]
        answer = next((p["expected_answer"] for p in probes if p["id"] == context.probe_id),
                      "Offline fixture reply; no model was called.")
        return dict(user_id=request.user_id, session_id=request.session_id, request_id=context.request_id,
                    reply=answer, memory_used=dict(short_term_count=0, short_term_messages=[],
                    session_summary=None, lifetime_summary=None, episodes=[], policy=self.config.policy))


def factory(endpoints, *, fail=False):
    @contextmanager
    def create(config, directory):
        endpoint = FixtureEndpoint(config, directory, fail=fail)
        endpoints.append(endpoint)
        yield endpoint
    return create


@pytest.fixture
def study(tmp_path):
    endpoints = []
    ticks = iter(i / 500 for i in range(1000))
    path = tmp_path / "offline-study"
    runner = StudyRunner(base_config=HW6Config(source_commit="offline-fixture-revision"), owner_id="7",
                         endpoint_factory=factory(endpoints), output=path, timer=lambda: next(ticks))
    manifest = runner.run()
    return path, manifest, endpoints


def scored(manifest, probes, joined):
    template = scoring_template(manifest, probes, joined)
    for row in template["rows"]:
        row.update(score=5, explanation="Deliberate fixture matches every frozen criterion.",
                   scorer="Offline test fixture", scored_at="2026-10-20T00:00:00+00:00")
        for group in ("essential", "full_credit"):
            for criterion in row[group]:
                criterion.update(assessment="correct", explanation="Exact expected-answer fixture.")
    return template


def test_frozen_design_is_complete_and_provenance_matches_actual_messages():
    conversation, probes, hashes = load_design()
    assert len(conversation["messages"]) == 30 and len(probes["probes"]) == 5
    assert "30 submitted user" in conversation["counting_convention"]
    assert set(hashes) == {"scripts/hw06/part3/conversation.json", "memory_probes.yaml"}
    assert "$2,200" in conversation["messages"][0] and "$2,400" in conversation["messages"][11]
    assert all(word not in " ".join(conversation["messages"][-5:])
               for word in ("Willow Glen", "Juniper", "2027", "$2,400", "elevator"))


def test_runner_configures_four_apps_fresh_namespaces_and_140_correlated_calls(study):
    path, manifest, endpoints = study
    restored, probes, joined = validate_study(path, count_tokens=len)
    assert restored == manifest
    assert [(e.config.short_term_n, e.config.policy) for e in endpoints] == [(4,"baseline"),(12,"baseline"),(30,"baseline"),(12,"token_budget")]
    assert len({e.requests[0][0].user_id for e in endpoints}) == 4
    assert len({e.requests[0][0].session_id for e in endpoints}) == 4
    assert sum(len(e.requests) for e in endpoints) == 140
    assert all(e.requests[0][0].user_id.startswith("7:hw6:D:") for e in endpoints)
    assert manifest["probe_isolation"] == "sequential_fixed_order"
    assert "persist" in manifest["sequential_probe_effects"]
    assert all(len(records[:30]) == 30 and len(records[30:]) == 5 for records in joined.values())
    with pytest.raises(FileExistsError):
        StudyRunner(base_config=HW6Config(), owner_id="7", endpoint_factory=factory([]), output=path).run()


def test_failed_attempt_remains_incomplete_with_real_sanitized_error(tmp_path):
    path = tmp_path / "failed"
    with pytest.raises(RequestFailed):
        StudyRunner(base_config=HW6Config(), owner_id="7", endpoint_factory=factory([], fail=True), output=path).run()
    assert json.loads((path / "manifest.json").read_text())["status"] == "incomplete"
    assert len(read_jsonl(path / "A/attempts.jsonl")) == 1
    row = read_jsonl(path / "A/requests.jsonl")[0]
    assert (row["status"], row["http_status"], row["error_code"]) == ("error", 503, "model_unavailable")
    assert row["response"] == {"code": "model_unavailable"}
    with pytest.raises(ValueError, match="incomplete"):
        validate_study(path)


@pytest.mark.parametrize("fault", ["missing_usage", "duplicate_event", "wrong_context", "wrong_config", "bad_residual", "aux_error", "orphan", "missing_summary"])
def test_event_validation_rejects_corrupt_or_incomplete_records(study, fault):
    path, _, _ = study
    file = path / "A/events.jsonl"
    events = read_jsonl(file)
    main = next(e for e in events if e["kind"] == "request")
    if fault == "missing_usage":
        main.update(usage_source="missing", prompt_tokens=None, completion_tokens=None, total_tokens=None)
    elif fault == "duplicate_event":
        events.append(deepcopy(events[0]))
    elif fault == "wrong_context":
        main["context"]["turn_id"] = 99
    elif fault == "wrong_config":
        main["config"]["short_term_n"] = 12
    elif fault == "bad_residual":
        main["components"]["template_residual"] = 999
    elif fault == "aux_error":
        events[1].update(status="error", error_code="model_unavailable")
    elif fault == "orphan":
        events[0]["context"]["request_id"] = "orphan"
    elif fault == "missing_summary":
        events = [e for e in events if e["operation"] != "session_summary"]
    file.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    with pytest.raises(ValueError):
        validate_study(path)


def test_scoring_export_is_unfilled_and_preserves_answers_and_rules(study, tmp_path):
    path, _, _ = study
    target = tmp_path / "unfilled-scores.json"
    export_scoring_template(path, target)
    sheet = json.loads(target.read_text())
    assert len(sheet["rows"]) == 20
    assert all(r["score"] is None and r["explanation"] == "" for r in sheet["rows"])
    assert sheet["rows"][0]["answer"].startswith("Current maximum monthly base rent is $2,400")
    assert sheet["rows"][0]["essential"]
    with pytest.raises(ValueError, match="Offline fixtures"):
        export_metrics(path, target, tmp_path / "forbidden-table")
    assert not (tmp_path / "forbidden-table").exists()


def test_public_export_reproduces_saved_measured_results_from_json(tmp_path):
    """The saved scored JSON must work through the ordinary exporter, without an adapter."""
    root = Path(__file__).resolve().parents[1]
    study = root / "reports/hw06/raw/part3/measured-study"
    scores = root / "reports/hw06/raw/part3/scores.json"
    expected = root / "reports/hw06/part3/metrics"
    output = tmp_path / "exported"
    result = export_metrics(study, scores, output)
    assert result["source_commit"] == "4c0bd7c2dd0bedeab73d6a31d9f5c3a83a84e961"
    names = {"metrics.json", "memory_cost.csv", "memory_cost.md", "per_turn.csv",
             "scores.json", "auxiliary_generation.json", "embeddings.json"}
    assert {p.name for p in output.iterdir()} == names
    assert all((output / name).read_bytes() == (expected / name).read_bytes() for name in names)


def test_json_rubric_key_normalization_does_not_accept_changed_values(study):
    path, _, _ = study
    manifest, probes, joined = validate_study(path)
    scores = json.loads(json.dumps(scored(manifest, probes, joined)))
    scores["rubric"]["1"] = "changed scoring rule"
    with pytest.raises(ValueError, match="Scoring design changed"):
        calculate_metrics(manifest, probes, joined, scores)


def test_arithmetic_excludes_probes_and_auxiliary_is_separate(study):
    path, _, _ = study
    manifest, probes, joined = validate_study(path)
    for records in joined.values():
        for record in records[30:]:
            record["client"]["http_latency_ms"] = 999999
            record["main"].prompt_tokens = 999999
    result = calculate_metrics(manifest, probes, joined, scored(manifest, probes, joined))
    baseline = result["conditions"][1]
    assert baseline["prompt_total"] == 6000 and baseline["completion_total"] == 600
    assert baseline["mean_prompt_tokens"] == 200 and baseline["mean_completion_tokens"] == 20
    assert baseline["mean_http_latency_ms"] == pytest.approx(2)
    assert Decimal(baseline["main_chat_cost_10000_usd"]) == Decimal("90")
    assert Decimal(baseline["main_plus_generative_memory_cost_10000_usd"]) == Decimal("98.1")
    assert baseline["auxiliary_prompt_total"] == 420 and baseline["auxiliary_completion_total"] == 78
    assert baseline["embedding_calls"] == 30 and baseline["embedding_cost_usd"] is None
    assert result["policy_comparison"] == dict(baseline="B", policy="D", prompt_savings_percent=40,
                                             savings_undefined_reason=None, quality_change=0)
    assert result["selection"]["best_qualifying"] == "A"
    assert result["selection"]["worst_by_cost"] == "C"
    assert projected_cost(6000, 600) == Decimal("90")


def test_no_qualifier_and_incorrect_essential_fact_disqualifies(study):
    path, _, _ = study
    manifest, probes, joined = validate_study(path)
    scores = scored(manifest, probes, joined)
    for row in scores["rows"]:
        row["score"] = 3
    result = calculate_metrics(manifest, probes, joined, scores)
    assert result["selection"]["best_qualifying"] is None
    assert result["selection"]["no_qualifying_setting"]
    scores = scored(manifest, probes, joined)
    for condition in CONDITIONS:
        row = next(r for r in scores["rows"] if r["condition"] == condition.id)
        row["score"] = 2  # mean 4.4, but one incorrect essential fact
        row["essential"][0]["assessment"] = "incorrect"
    result = calculate_metrics(manifest, probes, joined, scores)
    assert all(r["mean_quality"] == 4.4 for r in result["conditions"])
    assert result["selection"]["no_qualifying_setting"]


def test_policy_quality_change_is_signed_and_zero_prompt_baseline_is_explicit(study):
    path, _, _ = study
    manifest, probes, joined = validate_study(path)
    scores = scored(manifest, probes, joined)
    row = next(r for r in scores["rows"] if r["condition"] == "B")
    row["score"] = 3
    row["essential"][0].update(assessment="missing", explanation="Deliberate partial-recall fixture.")
    for record in joined["B"][:30]:
        record["main"].prompt_tokens = 0
    comparison = calculate_metrics(manifest, probes, joined, scores)["policy_comparison"]
    assert comparison["quality_change"] == pytest.approx(0.4)
    assert comparison["prompt_savings_percent"] is None
    assert comparison["savings_undefined_reason"] == "zero baseline prompt total"


@pytest.mark.parametrize("fault", ["score_missing", "answer_changed", "criteria_changed", "unexplained", "wrong_score"])
def test_scoring_cannot_change_frozen_answers_or_contradict_rubric(study, fault):
    path, _, _ = study
    manifest, probes, joined = validate_study(path)
    scores = scored(manifest, probes, joined)
    row = scores["rows"][0]
    if fault == "score_missing": row["score"] = None
    if fault == "answer_changed": row["answer"] = "edited"
    if fault == "criteria_changed": row["essential"][0]["criterion"] = "different"
    if fault == "unexplained": row["explanation"] = ""
    if fault == "wrong_score": row["essential"][0]["assessment"] = "incorrect"
    with pytest.raises(ValueError):
        calculate_metrics(manifest, probes, joined, scores)


def test_clone_isolation_allocates_fresh_ids_and_leaves_base_requests_alone(tmp_path):
    endpoints, clones, snapshots = [], [], []
    class Isolation:
        def snapshot(self, endpoint, user, session):
            assert len(endpoint.requests) == 30
            snapshots.append((user, session))
            return "snapshot-" + user
        @contextmanager
        def clone(self, snapshot, user, session):
            clones.append((snapshot, user, session))
            yield
    path = tmp_path / "cloned"
    manifest = StudyRunner(base_config=HW6Config(source_commit="fixture"), owner_id="7",
                endpoint_factory=factory(endpoints), output=path, isolation=Isolation()).run()
    validate_study(path)
    assert manifest["probe_isolation"] == "snapshot_clone"
    assert len(snapshots) == 4 and len(clones) == 20
    assert len({user for _, user, _ in clones}) == 20
    for endpoint in endpoints:
        base = endpoint.requests[0][0].user_id
        assert sum(r.user_id == base for r, _ in endpoint.requests) == 30
