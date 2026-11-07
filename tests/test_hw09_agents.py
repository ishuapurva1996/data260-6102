import json
from dataclasses import replace
from types import SimpleNamespace

from src.hw09_agents import (
    AnsweringAgent,
    EvaluatorAgent,
    Lesson,
    run_question,
    validate_lesson,
)


class ScriptedModel:
    def __init__(self, *answers):
        self.answers = iter(answers)
        self.messages = []

    def complete(self, messages):
        self.messages.append(messages)
        return SimpleNamespace(content=next(self.answers))


QUESTION = {
    "listing_id": "S6102-R-9401",
    "question": "What is the rent and how many units are ready now?",
    "requested_fields": ["rent_usd", "available_units"],
}
LISTING = {
    "source": {"rent_usd": 1950, "inventory_export": {"bucket_a": 5, "bucket_b": 2}},
    "facts": {"rent_usd": 1950, "available_units": 2},
}
GOOD = '{"rent_usd":1950,"available_units":2}'
INCOMPLETE = '{"rent_usd":1950}'
LESSON = Lesson(
    lesson_id="ready-now",
    failure_pattern="Answers omit or misstate ready-now availability.",
    correction="Use inventory_export.bucket_b for available_units.",
    created_at="2026-11-07T03:00:00+00:00",
    use_count=0,
    scope={"requested_field": "available_units", "source_field": "inventory_export"},
)


def test_repair_uses_evaluator_feedback_and_passes():
    model = ScriptedModel(INCOMPLETE, GOOD)
    run = run_question(QUESTION, LISTING, AnsweringAgent(model), EvaluatorAgent())
    assert [a.grade.result for a in run.attempts] == ["REVISE", "PASS"]
    assert "available_units" in run.attempts[0].grade.feedback
    assert (
        json.loads(model.messages[1][-1][1])["evaluator_feedback"] == run.attempts[0].grade.feedback
    )
    assert run.attempts[-1].answer.claims == {"rent_usd": 1950, "available_units": 2}


def test_second_revise_ends_loop():
    model = ScriptedModel(INCOMPLETE, INCOMPLETE)
    run = run_question(QUESTION, LISTING, AnsweringAgent(model), EvaluatorAgent())
    assert len(model.messages) == len(run.attempts) == 2
    assert run.attempts[-1].grade.result == "REVISE"


def test_baseline_offline_grading_does_not_trigger_an_answer():
    run = run_question(QUESTION, LISTING, AnsweringAgent(ScriptedModel(INCOMPLETE)), None)
    assert len(run.attempts) == 1
    assert run.attempts[0].grade is None
    assert EvaluatorAgent().evaluate(QUESTION, LISTING, run.attempts[0].answer).result == "REVISE"


def test_lesson_loaded_once_per_question_and_scoped_to_requested_field():
    model = ScriptedModel(INCOMPLETE, GOOD, '{"rent_usd":1950}')
    agent = AnsweringAgent(model, (LESSON,))
    targeted = run_question(QUESTION, LISTING, agent, EvaluatorAgent())
    unrelated = run_question(
        {**QUESTION, "question": "What is the rent?", "requested_fields": ["rent_usd"]},
        LISTING,
        agent,
        EvaluatorAgent(),
    )
    assert targeted.lesson_ids == (LESSON.lesson_id,)
    assert unrelated.lesson_ids == ()
    assert agent.use_counts == {LESSON.lesson_id: 1}
    assert all(LESSON.correction in messages[-1][1] for messages in model.messages[:2])
    assert LESSON.correction not in model.messages[2][-1][1]
    assert LESSON.use_count == 0


def test_validation_retention_checks_reject_regressions_independently():
    evaluator = EvaluatorAgent()
    rent_question = {**QUESTION, "requested_fields": ["rent_usd"]}
    reference = {QUESTION["listing_id"]: LISTING}
    rent = '{"rent_usd":1950}'

    def simulate(question, *answers, lessons=()):
        return run_question(
            question, LISTING, AnsweringAgent(ScriptedModel(*answers), lessons), evaluator
        )

    target_ok = simulate(QUESTION, GOOD)
    target_repaired = simulate(QUESTION, INCOMPLETE, GOOD)
    after_ok = simulate(QUESTION, GOOD, lessons=(LESSON,))
    after_repaired = simulate(QUESTION, INCOMPLETE, GOOD, lessons=(LESSON,))
    after_failed = simulate(QUESTION, INCOMPLETE, INCOMPLETE, lessons=(LESSON,))
    unrelated = simulate(rent_question, rent)
    unsupported = simulate(rent_question, '{"rent_usd":1950,"pets":"yes"}', rent)
    out_of_scope = replace(unrelated, lesson_ids=(LESSON.lesson_id,))

    scenarios = (
        (target_ok, after_ok, unrelated, None),
        (target_ok, after_repaired, unrelated, "target_maintained"),
        (target_repaired, after_failed, unrelated, "previously_correct_preserved"),
        (target_ok, after_ok, unsupported, "no_new_unsupported_claims"),
        (target_ok, after_ok, out_of_scope, "scope_preserved"),
    )
    for before, after, after_unrelated, failed_check in scenarios:
        accepted, pairs = validate_lesson(
            (before, unrelated), (after, after_unrelated), LESSON, reference
        )
        assert accepted is (failed_check is None)
        if failed_check:
            assert not all(pair[failed_check] for pair in pairs)


def test_explicit_unknown_and_false_are_distinct_from_missing_or_numeric():
    question = {**QUESTION, "requested_fields": ["parking_included", "elevator"]}
    listing = {"source": {}, "facts": {"parking_included": False}}
    evaluator = EvaluatorAgent()
    agent = AnsweringAgent(ScriptedModel('{"parking_included":false,"elevator":null}'))
    run = run_question(question, listing, agent, evaluator)
    answer = run.attempts[0].answer
    assert run.attempts[0].grade.result == "PASS"
    wrong = replace(answer, claims={"parking_included": 0})
    grade = evaluator.evaluate(question, listing, wrong)
    assert grade.result == "REVISE"
    assert grade.incorrect_fields == ("elevator", "parking_included")
