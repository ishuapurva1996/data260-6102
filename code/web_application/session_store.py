"""Persistent authentication-session helpers using UTC-naive database times.

SQLAlchemy sessions are units of database work; ``SessionToken`` records are
browser logins. The request's database session is supplied by ``get_db``. Nothing
in this module creates an engine, writes seed data, or keeps login state in memory.
"""

from datetime import datetime, timedelta
import secrets

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import SessionToken, User


COOKIE_NAME = "s6102_session"
IDLE_TIMEOUT_SECONDS = 300
ABSOLUTE_TIMEOUT_SECONDS = 3600


def create_session(db: Session, user_id: int, now: datetime) -> SessionToken:
    """Stage an opaque login token; the caller commits its login transaction."""
    token = SessionToken(
        id=secrets.token_urlsafe(32),
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(seconds=ABSOLUTE_TIMEOUT_SECONDS),
        last_activity_at=now,
    )
    db.add(token)
    return token


def revoke_session(db: Session, token_id: str | None) -> None:
    """Stage deletion of a cookie token, including unknown or expired tokens."""
    if token_id:
        db.execute(delete(SessionToken).where(SessionToken.id == token_id))


def authenticate_session(
    db: Session,
    token_id: str | None,
    now: datetime,
    idle_timeout: float = IDLE_TIMEOUT_SECONDS,
) -> User | None:
    """Check one joined login/user lookup and commit accepted activity.

    The activity commit intentionally precedes the endpoint's work: a valid
    authenticated request counts as activity even if its payload is invalid or
    the endpoint later rolls back. ``get_db`` uses ``expire_on_commit=False``,
    keeping the loaded user available without a second user SELECT.
    """
    if not token_id:
        return None
    row = db.execute(
        select(SessionToken, User).join(User, SessionToken.user_id == User.id).where(
            SessionToken.id == token_id
        )
    ).first()
    if row is None:
        return None
    token, user = row
    if (
        now >= token.expires_at
        or now - token.created_at >= timedelta(seconds=ABSOLUTE_TIMEOUT_SECONDS)
        or now - token.last_activity_at >= timedelta(seconds=idle_timeout)
    ):
        db.delete(token)
        db.commit()
        return None
    token.last_activity_at = now
    db.commit()
    return user
