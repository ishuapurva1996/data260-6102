"""Bounded retries for completed read operations, before service sanitization."""
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pymysql import err as mysql_errors
from sqlalchemy import exc as sqlalchemy_errors

from .reader import RentalReader


class InjectedTransientError(Exception):
    """Explicit controlled failure used by the separately labeled experiment."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_s: float = 0.1
    backoff_multiplier: float = 2.0
    max_backoff_s: float = 0.2

    def __post_init__(self):
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be an integer from 1 to 10.")
        for name in ("initial_backoff_s", "backoff_multiplier", "max_backoff_s"):
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number.")
        if not 0 <= self.initial_backoff_s <= self.max_backoff_s <= 60:
            raise ValueError("Backoff delays must satisfy 0 <= initial <= maximum <= 60 seconds.")
        if not 1 <= self.backoff_multiplier <= 100:
            raise ValueError("backoff_multiplier must be from 1 to 100.")


def is_transient(error: Exception) -> bool:
    """Small type/code allowlist; never inspect exception strings or SQL.

    1205/1213: lock wait/deadlock; 2006/2013: lost connection (including
    PyMySQL read timeout); 3024: SELECT execution timeout. Code 2003 is excluded
    because connection setup failure alone does not establish a transient cause.
    """
    if isinstance(error, sqlalchemy_errors.DBAPIError):
        error = error.orig
    if isinstance(error, (InjectedTransientError, TimeoutError, ConnectionResetError,
                          ConnectionAbortedError, BrokenPipeError, sqlalchemy_errors.TimeoutError)):
        return True
    return (isinstance(error, mysql_errors.OperationalError)
            and bool(error.args) and type(error.args[0]) is int
            and error.args[0] in {1205, 1213, 2006, 2013, 3024})


class RetryingRentalReader:
    """One policy across all reads. Caller owns closing this wrapper.

    Observer dictionaries contain only operation, one-based attempt, outcome,
    attempt elapsed seconds and next sleep seconds. An observer cannot alter
    retry decisions; ordinary observer exceptions are ignored without logging
    potentially sensitive exception text.
    """
    def __init__(self, reader: RentalReader, policy: RetryPolicy | None = None,
                 attempt_observer: Callable[[dict[str, Any]], None] | None = None,
                 *, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.perf_counter):
        if isinstance(reader, RetryingRentalReader):
            raise ValueError("A retrying reader cannot wrap another retrying reader.")
        if policy is not None and not isinstance(policy, RetryPolicy):
            raise TypeError("policy must be a RetryPolicy.")
        if attempt_observer is not None and not callable(attempt_observer):
            raise TypeError("attempt_observer must be callable.")
        self.reader = reader
        self.policy = policy if policy is not None else RetryPolicy()
        self.attempt_observer = attempt_observer
        self._sleep, self._clock = sleep, clock
        self._closed = False

    def _observe(self, operation, attempt, outcome, elapsed, delay):
        if self.attempt_observer is not None:
            try:
                self.attempt_observer({"operation": operation, "attempt": attempt,
                    "outcome": outcome, "elapsed_s": elapsed, "sleep_s": delay})
            except Exception:
                pass

    def _read(self, operation, call, *args):
        if self._closed:
            raise RuntimeError("The rental reader is closed.")
        delay = self.policy.initial_backoff_s
        for attempt in range(1, self.policy.max_attempts + 1):
            started = self._clock()
            try:
                result = call(*args)
            except Exception as error:
                elapsed = self._clock() - started
                transient = is_transient(error)
                retry = transient and attempt < self.policy.max_attempts
                self._observe(operation, attempt, "transient_error" if transient else "permanent_error",
                              elapsed, delay if retry else 0)
                if not retry:
                    raise
                self._sleep(delay)
                delay = min(delay * self.policy.backoff_multiplier, self.policy.max_backoff_s)
            else:
                self._observe(operation, attempt, "success", self._clock() - started, 0)
                return result

    def search_rentals(self, query: str, limit: int):
        return self._read("search_rentals", self.reader.search_rentals, query, limit)

    def get_rental(self, rental_id: int):
        return self._read("get_rental", self.reader.get_rental, rental_id)

    def count_rentals(self, manager_id: int):
        return self._read("count_rentals", self.reader.count_rentals, manager_id)

    def close(self) -> None:
        if not self._closed:
            # Mark first so an underlying cleanup failure cannot cause a second close.
            self._closed = True
            close = getattr(self.reader, "close", None)
            if callable(close):
                close()
