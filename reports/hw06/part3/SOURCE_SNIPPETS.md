# Part 3 source and real output pairs

All excerpts refer to measured source `4c0bd7c2dd0bedeab73d6a31d9f5c3a83a84e961`; no application source changed for this evidence.

## Whole-message token eviction

`src/hw06_experiments/policy.py:7`

```python
def token_budget_window(messages: Sequence[MessageRecord], *, short_term_n: int,
                        token_budget: int, count_tokens: TokenCounter) -> list[MessageRecord]:
    """Drop oldest whole previous messages until canonical window text fits.

    Count the entire rendered block after each removal: token boundaries need
    not be additive. An oversized newest message leaves an empty window. Never
    truncate a record, mutate an input, or delete persisted memory. The caller
    supplies the model-matching counter and appends the current message later.
    """
    if short_term_n < 0 or token_budget < 0:
        raise ValueError("Window limits must be nonnegative")
    retained = list(messages[-short_term_n:]) if short_term_n else []
    while retained and count_tokens(render_window(retained)) > token_budget:
        retained.pop(0)
    return retained
```

Real audit: every D selection matched recomputation; largest window 157/160 tokens; all 70 final messages persisted.

## Client request timing

`src/hw06_experiments/runner.py:159`

```python
            if isinstance(exc, RequestFailed):
                row["response"] = exc.response
            raise
        finally:
            row["http_latency_ms"] = (self.timer() - started) * 1000
            append_json(directory / "requests.jsonl", row)
```

Real D mean primary HTTP latency: 23392.922 ms over exactly 30 primary requests; individual values are in metrics/per_turn.csv.

## Actual component estimates

`src/hw06_memory_mongo/service.py:162`

```python
                components = TokenComponents(**{name: self.count_tokens(text) if text else 0
                    for name, text in parts.model_dump().items()},
                    tokenizer_identity=getattr(self.count_tokens, 'identity', None))
                result = self._complete(messages)
                counts = self._counts(result)
                if counts['prompt_tokens'] is not None:
                    component_sum = sum(getattr(components, key) for key in type(parts).model_fields)
                    components.template_residual = counts['prompt_tokens'] - component_sum
```

Real audit: all six selected text-block counts and signed residuals recomputed for 140 main request events.

## Assigned-price projection

`src/hw06_experiments/metrics.py:65`

```python
def projected_cost(prompt: int, completion: int) -> Decimal:
    """Assigned hypothetical prices, not current provider pricing.

    10,000 conversations * (P*$1 + O*$5) / 1,000,000 tokens.
    P/O are totals for ONE 30-primary-turn conversation. No probes/warmups.
    """
    if type(prompt) is not int or type(completion) is not int or min(prompt, completion) < 0:
        raise ValueError("Nonnegative integer token totals required")
    return Decimal(10000) * (Decimal(prompt) + Decimal(5) * completion) / Decimal(1000000)
```

Real N4 main-chat projection: (14800 + 5*1135)/100 = $204.75; with generative memory: $479.37.
