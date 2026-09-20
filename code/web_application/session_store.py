"""App-local, revocable sessions for the single-worker homework demonstration."""

from collections.abc import Callable
import math
import secrets
from time import monotonic


class SessionStore:
    """Keep the authoritative user and last activity outside the signed cookie.

    A process restart drops this registry, so previously issued cookies cannot
    restore a login. Auth routes are its only callers: rental API requests and
    static assets deliberately do not extend the idle deadline.
    """

    def __init__(self, idle_timeout: float = 300, clock: Callable[[], float] = monotonic):
        if not math.isfinite(idle_timeout) or idle_timeout <= 0:
            raise ValueError("idle timeout must be a positive, finite number of seconds")
        self.idle_timeout = idle_timeout
        self.clock = clock
        self._sessions: dict[str, tuple[str, float]] = {}

    def __len__(self) -> int:
        return len(self._sessions)

    def cleanup(self, now: float | None = None) -> None:
        """Expire at the boundary, before any request can renew activity."""
        now = self.clock() if now is None else now
        expired = [
            sid for sid, (_, last_activity) in self._sessions.items()
            if now - last_activity >= self.idle_timeout
        ]
        for sid in expired:
            del self._sessions[sid]

    def create(self, user: str) -> str:
        now = self.clock()
        self.cleanup(now)
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = (user, now)
        return sid

    def authenticate(self, sid: object, user: object) -> str | None:
        now = self.clock()
        self.cleanup(now)
        if not isinstance(sid, str) or not isinstance(user, str):
            return None
        session = self._sessions.get(sid)
        if session is None or session[0] != user:
            return None
        self._sessions[sid] = (user, now)
        return user

    def revoke(self, sid: object) -> None:
        self.cleanup()
        if isinstance(sid, str):
            self._sessions.pop(sid, None)
