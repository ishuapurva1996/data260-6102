"""One pure policy. Persistent storage and the current message are outside it."""
from collections.abc import Sequence

from src.hw06_shared.contracts import MessageRecord, TokenCounter, render_window


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
