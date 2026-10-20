"""Offline engineering checks, never assignment measurements."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from src.hw06_experiments.policy import token_budget_window
from src.hw06_shared.contracts import render_window


def messages(*contents):
    return [dict(id=str(i), user_id="fixture", session_id="fixture", role="user",
                 content=text, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            for i, text in enumerate(contents)]


def test_evicts_oldest_whole_records_and_keeps_order_without_mutation():
    previous = messages("old", "middle", "new")
    original = deepcopy(previous)
    retained = token_budget_window(previous, short_term_n=3, token_budget=23,
                                   count_tokens=len)
    assert [m["content"] for m in retained] == ["middle", "new"]
    assert previous == original
    assert len(render_window(retained)) <= 23


def test_n_applies_before_budget_and_current_message_is_outside_contract():
    previous = messages("a", "b", "c")
    assert token_budget_window(previous, short_term_n=1, token_budget=160,
                               count_tokens=len) == previous[-1:]
    assert token_budget_window(previous, short_term_n=0, token_budget=160,
                               count_tokens=len) == []


def test_oversized_latest_record_evicts_entire_window():
    assert token_budget_window(messages("small", "x" * 161), short_term_n=12,
                               token_budget=160, count_tokens=len) == []


def test_counter_sees_canonical_full_window_not_summed_message_estimates():
    seen = []
    def counter(text):
        seen.append(text)
        return 161 if "\n" in text else (0 if not text else 160)
    records = messages("one", "two")
    assert token_budget_window(records, short_term_n=12, token_budget=160,
                               count_tokens=counter) == records[-1:]
    assert seen == ["user: one\nuser: two", "user: two"]


@pytest.mark.parametrize("n,budget", [(-1, 160), (12, -1)])
def test_negative_limits_are_rejected(n, budget):
    with pytest.raises(ValueError):
        token_budget_window([], short_term_n=n, token_budget=budget, count_tokens=len)
