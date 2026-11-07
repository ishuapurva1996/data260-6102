# Part 4 agent code excerpts

Pragya Apurva · DATA 260

## Answering Agent

From `src/hw09_agents.py`, `AnsweringAgent.answer`. The first call receives the input and listing source. Applicable lesson text and the previous answer with feedback are added when present.

```python
payload = {"input": question, "listing_source": source}
if lessons:
    payload["applicable_lessons"] = [lesson.correction for lesson in lessons]
if prior is not None and prior.grade is not None:
    payload["prior_answer"] = prior.answer.raw
    payload["evaluator_feedback"] = prior.grade.feedback
result = self.model.complete([("system", ANSWER_PROMPT), ("user", json.dumps(payload))])
```

## Evaluator Agent

From `src/hw09_agents.py`, `EvaluatorAgent.evaluate`. These selected lines show canonical lookup and scoring. The complete method also handles malformed JSON and returns corrective feedback for missing, wrong or extra claims.

```python
expected = {field: listing["facts"].get(field) for field in question["requested_fields"]}
# After the malformed-answer check
claims = answer.claims
missing = expected.keys() - claims.keys()
extras = claims.keys() - expected.keys()
wrong = {
    field
    for field in expected.keys() & claims.keys()
    if type(claims[field]) is not type(expected[field]) or claims[field] != expected[field]
}
if not (missing or extras or wrong):
    return Evaluation("PASS", "All requested fields agree with the reference.")
```
