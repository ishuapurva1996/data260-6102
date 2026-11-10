"""Offline contract tests with synthetic Kafka records and a simulated judge."""

import csv
import hashlib
import json
import subprocess
import time

import pytest

from scripts.hw10 import evaluate
from scripts.hw10 import evaluation_validation as validation
from scripts.hw10.evaluation_evidence import EvaluationError
from scripts.hw10.evaluation_judge import score_on_five
from scripts.hw10.evaluation_validation import compare_scores

QUESTION = "How many units are available at S6102-R-9101?"
FACTS = {"listing_id": "S6102-R-9101", "available_units": 2}
PLAN = "Find the listing and read available_units."
DRAFT = "One unit is available."
FINAL = "Two units are available."


def linked_case():
    original = {
        "correlation_id": "trace-1",
        "run_id": "pipeline-run",
        "question": QUESTION,
        "rental_context": FACTS,
    }
    payloads = [
        {"from_stage": "planner", "plan": PLAN},
        {"from_stage": "writer", "plan": PLAN, "draft": DRAFT},
        {
            "from_stage": "reviewer",
            "plan": PLAN,
            "draft": DRAFT,
            "answer": FINAL,
            "status": "approved",
        },
    ]
    messages = {"inbox": {"topic": "s6102_inbox", "partition": 0, "offset": 0, "payload": original}}
    previous = messages["inbox"]
    for offset, (topic, payload) in enumerate(zip(("tasks", "drafts", "final"), payloads), 1):
        source = {key: previous[key] for key in ("topic", "partition", "offset")}
        previous = {
            "topic": f"s6102_{topic}",
            "partition": 0,
            "offset": offset,
            "payload": {**original, **payload, "input_source": source},
        }
        messages[payload["from_stage"]] = previous
    return {
        "case_id": "case-1",
        "trace_id": "trace-1",
        "correlation_id": "trace-1",
        "question": QUESTION,
        "reference_facts": FACTS,
        "plan": PLAN,
        "draft": DRAFT,
        "final_answer": FINAL,
        "messages": messages,
    }


class SimulatedJudge:
    metadata = {"model": "synthetic-judge"}

    def __init__(self, scores=()):
        self.scores = iter(scores)
        self.inputs = []

    def measure(self, criterion, question, facts, text):
        self.inputs.append((criterion, question, facts, text))
        return next(self.scores), "Synthetic reason for " + text


def write_linked(root, *rows):
    path = root / "tracing" / "linked_cases.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def read_rows(root, name):
    return [
        json.loads(line)
        for line in (root / "evaluation" / name).read_text(encoding="utf-8").splitlines()
    ]


def pipeline(root, judge, *args):
    return evaluate.main(
        ["pipeline", "--evidence-root", str(root), "--link-timeout", "0.05", *args],
        judge_factory=lambda _: judge,
    )


def test_scores_exact_linked_outputs_and_logs_evaluation_span(tmp_path):
    case = linked_case()
    write_linked(tmp_path, case, case)
    judge = SimulatedJudge([0.75, 0.25, 1])
    assert pipeline(tmp_path, judge, "--trace-id", "trace-1") == 0
    assert [entry[-1] for entry in judge.inputs] == [PLAN, DRAFT, FINAL]
    assert judge.inputs[1][:-1] == judge.inputs[2][:-1]
    (score,) = read_rows(tmp_path, "pipeline_scores.jsonl")
    (span,) = read_rows(tmp_path, "spans.jsonl")
    assert score["messages"] == case["messages"]
    assert score["final_answer"] == FINAL
    assert [score["scores"][stage]["score"] for stage in ("planner", "writer", "reviewer")] == [
        4,
        2,
        5,
    ]
    assert score["scores"]["writer"]["normalized_score"] == 0.25
    assert score["final_minus_draft"] == 3
    assert "One" in score["interpretation"] and "Two" in score["interpretation"]
    assert score["trace_id"] == span["trace_id"] == "trace-1"
    assert score["evaluation_id"] == span["evaluation_id"]
    assert (span["stage"], span["status"], span["error"]) == ("evaluation", "ok", None)
    assert span["end_time"] >= span["start_time"]
    assert span["duration_ms"] >= 0


@pytest.mark.parametrize(
    ("modify", "error_code"),
    [
        (lambda case: case["messages"].pop("writer"), "missing_evidence"),
        (lambda case: case["messages"]["writer"]["payload"].update(draft=[]), "malformed_evidence"),
        (
            lambda case: case["messages"]["writer"]["payload"].update(correlation_id="other"),
            "conflicting_evidence",
        ),
        (lambda case: case.update(final_answer="Reconstructed text"), "conflicting_evidence"),
        (
            lambda case: case["messages"]["reviewer"]["payload"]["input_source"].update(offset=40),
            "conflicting_evidence",
        ),
    ],
)
def test_rejects_bad_evidence_without_judging(tmp_path, modify, error_code):
    case = linked_case()
    modify(case)
    write_linked(tmp_path, case)
    judge = SimulatedJudge()
    assert pipeline(tmp_path, judge, "--trace-id", "trace-1") == 1
    (failure,) = read_rows(tmp_path, "pipeline_failures.jsonl")
    (span,) = read_rows(tmp_path, "spans.jsonl")
    assert failure["error_code"] == error_code
    assert span["status"] == "error" and span["trace_id"] == "trace-1"
    assert not judge.inputs
    assert not (tmp_path / "evaluation" / "pipeline_scores.jsonl").exists()


def test_rejects_two_different_linked_rows_for_same_correlation(tmp_path):
    case = linked_case()
    other = linked_case()
    other["messages"]["reviewer"]["offset"] += 1
    other["messages"]["reviewer"]["payload"]["answer"] = other["final_answer"] = DRAFT
    write_linked(tmp_path, case, other)
    assert pipeline(tmp_path, SimulatedJudge(), "--case-id", "case-1") == 1
    (failure,) = read_rows(tmp_path, "pipeline_failures.jsonl")
    assert failure["error_code"] == "conflicting_evidence"
    assert failure["trace_id"] == "trace-1"


def test_case_selector_checks_the_complete_correlation_group(tmp_path):
    case = linked_case()
    write_linked(tmp_path, case, {**case, "case_id": "case-2"})
    assert pipeline(tmp_path, SimulatedJudge(), "--case-id", "case-1") == 1
    (failure,) = read_rows(tmp_path, "pipeline_failures.jsonl")
    assert failure["error_code"] == "conflicting_evidence"
    assert failure["trace_id"] == "trace-1"


def test_missing_and_malformed_json_have_bounded_failures(tmp_path):
    started = time.monotonic()
    assert pipeline(tmp_path, SimulatedJudge(), "--trace-id", "trace-1") == 1
    assert time.monotonic() - started < 1
    path = write_linked(tmp_path)
    path.write_text('{"trace_id":"trace-1",broken}\n', encoding="utf-8")
    assert pipeline(tmp_path, SimulatedJudge(), "--trace-id", "trace-1") == 1
    assert [row["error_code"] for row in read_rows(tmp_path, "pipeline_failures.jsonl")] == [
        "missing_evidence",
        "malformed_evidence",
    ]


def test_case_deadline_interrupts_stalled_judge(tmp_path):
    class StalledJudge(SimulatedJudge):
        def measure(self, *args):
            time.sleep(3)

    write_linked(tmp_path, linked_case())
    started = time.monotonic()
    assert pipeline(tmp_path, StalledJudge(), "--trace-id", "trace-1", "--case-timeout", "0.1") == 1
    assert time.monotonic() - started < 1
    (failure,) = read_rows(tmp_path, "pipeline_failures.jsonl")
    assert failure["error_code"] == "case_timeout"


def test_judge_failure_retries_once_and_keeps_failure_separate(tmp_path):
    class UnavailableJudge(SimulatedJudge):
        def measure(self, *args):
            self.inputs.append(args)
            raise EvaluationError("judge_unavailable", "Simulated connection refused")

    write_linked(tmp_path, linked_case())
    judge = UnavailableJudge()
    assert pipeline(tmp_path, judge, "--trace-id", "trace-1") == 1
    assert len(judge.inputs) == 2
    (failure,) = read_rows(tmp_path, "pipeline_failures.jsonl")
    assert failure["error_code"] == "judge_unavailable"
    assert failure["failed_metric"] == "planner"
    assert not (tmp_path / "evaluation" / "pipeline_scores.jsonl").exists()


@pytest.mark.parametrize(
    ("normalized", "score"),
    [(0, 1), (0.124, 1), (0.125, 2), (0.375, 3), (0.625, 4), (0.875, 5), (1, 5)],
)
def test_rounds_half_up_and_preserves_endpoints(normalized, score):
    assert score_on_five(normalized) == score


def test_validation_statistics_join_by_id_and_use_tied_ranks():
    labels = {"a": 1, "b": 2, "c": 2, "d": 4}
    passes = [
        {"d": 4, "c": 2, "b": 3, "a": 1},
        {"c": 2, "a": 2, "d": 4, "b": 1},
        {"a": 1, "b": 2, "c": 2, "d": 4},
    ]
    result = compare_scores(labels, passes)
    assert result["spearman"] == pytest.approx(0.9486832980505138)
    assert result["mean_absolute_difference"] == 0.25
    assert result["repeatability"] == {
        "changed_count": 2,
        "changed_rate": 0.5,
        "mean_score_change": 0.75,
        "max_score_change": 2,
    }
    assert compare_scores(dict.fromkeys(labels, 1), passes)["spearman"] is None


@pytest.fixture
def frozen_synthetic_study(tmp_path, monkeypatch):
    repo = tmp_path / "synthetic-repo"
    repo.mkdir()
    monkeypatch.setattr(validation, "REPO_ROOT", repo)

    def git(*args):
        return subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "-q")
    git("commit", "--allow-empty", "-qm", "Synthetic A1")
    tracing_sha = git("rev-parse", "HEAD")
    cases_path = repo / validation.CASES
    labels_path = repo / validation.LABELS
    cases_path.parent.mkdir(parents=True)
    cases = [
        {
            "case_id": f"case-{i}",
            "trace_id": f"trace-{i}",
            "question": QUESTION,
            "reference_facts": FACTS,
            "draft": f"Original draft {i}",
        }
        for i in range(20)
    ]
    cases_path.write_text(json.dumps(cases), encoding="utf-8")
    labels_path.write_text(
        "case_id,helpfulness\n" + "".join(f"case-{i},{i % 5 + 1}\n" for i in reversed(range(20))),
        encoding="utf-8",
    )
    git("add", validation.CASES, validation.LABELS)
    git("commit", "-qm", "Synthetic A2")
    freeze_sha = git("rev-parse", "HEAD")
    args = [
        "validate",
        "--evidence-root",
        str(tmp_path),
        "--tracing-sha",
        tracing_sha,
        "--freeze-sha",
        freeze_sha,
        "--cases-sha256",
        hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "--labels-sha256",
        hashlib.sha256(labels_path.read_bytes()).hexdigest(),
    ]
    return args, cases, labels_path


def test_frozen_study_scores_all_drafts_three_times(tmp_path, frozen_synthetic_study):
    args, cases, _ = frozen_synthetic_study
    judge = SimulatedJudge([i % 5 / 4 for i in range(20)] * 3)
    assert evaluate.main(args, judge_factory=lambda _: judge) == 0
    expected = [("helpfulness", QUESTION, FACTS, case["draft"]) for case in cases]
    assert judge.inputs == expected * 3
    output = tmp_path / "evaluation"
    with (output / "judge_scores.csv").open(encoding="utf-8", newline="") as source:
        scores = list(csv.DictReader(source))
    assert len(scores) == 60 and len({row["run_id"] for row in scores}) == 3
    assert {row["pass"] for row in scores} == {"1", "2", "3"}
    assert all(row["status"] == "ok" and row["reason"] for row in scores)
    summary = json.loads((output / "judge_validation.json").read_text(encoding="utf-8"))
    assert summary["freeze_sha"] == args[args.index("--freeze-sha") + 1]
    assert summary["spearman"] == pytest.approx(1)
    assert summary["mean_absolute_difference"] == 0
    assert summary["repeatability"]["changed_count"] == 0


def test_modified_freeze_stops_before_judge(frozen_synthetic_study):
    args, _, labels_path = frozen_synthetic_study
    labels_path.write_text("case_id,helpfulness\ncase-0,1\n", encoding="utf-8")

    def unexpected_judge(_):
        pytest.fail("Modified freeze must stop before creating a judge")

    assert evaluate.main(args, judge_factory=unexpected_judge) == 1


def test_incomplete_study_keeps_failure_and_omits_aggregate_scores(
    tmp_path, frozen_synthetic_study
):
    args, _, _ = frozen_synthetic_study

    class FailingFirstCase(SimulatedJudge):
        def __init__(self):
            super().__init__([0.5] * 59)
            self.remaining_errors = 2

        def measure(self, *args):
            if self.remaining_errors:
                self.remaining_errors -= 1
                raise EvaluationError("judge_unavailable", "Simulated connection refused")
            return super().measure(*args)

    judge = FailingFirstCase()
    assert evaluate.main(args, judge_factory=lambda _: judge) == 1
    (failure,) = read_rows(tmp_path, "judge_failures.jsonl")
    assert (failure["case_id"], failure["pass"], failure["status"]) == ("case-0", 1, "error")
    summary = json.loads(
        (tmp_path / "evaluation" / "judge_validation.json").read_text(encoding="utf-8")
    )
    assert summary["scored_count"] == 59
    assert summary["passes"][0]["status"] == "incomplete"
    assert summary["mean_absolute_difference"] is None
    assert summary["repeatability"] is None
