"""Private signing configuration and a fixed JWT verification contract."""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import jwt

ALGORITHM = "HS256"
ISSUER = "s6102"
AUDIENCE = "s6102-rentals"
ROLES = {"reader", "writer", "moderator"}


@dataclass(frozen=True)
class JWTSettings:
    secret: str = field(repr=False)
    ttl_seconds: int = 900

    def __post_init__(self):
        if len(self.secret.encode()) < 32:
            raise ValueError("HW7_JWT_SECRET must contain at least 32 private bytes.")
        if not 1 <= self.ttl_seconds <= 3600:
            raise ValueError("HW7_JWT_TTL_SECONDS must be between 1 and 3600.")

    @classmethod
    def from_env(cls):
        return cls(
            os.environ.get("HW7_JWT_SECRET", ""), int(os.environ.get("HW7_JWT_TTL_SECONDS", "900"))
        )


def issue_token(user_id: int, settings: JWTSettings) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(seconds=settings.ttl_seconds),
            "iss": ISSUER,
            "aud": AUDIENCE,
        },
        settings.secret,
        algorithm=ALGORITHM,
    )


def token_subject(token: str, settings: JWTSettings) -> int:
    claims = jwt.decode(
        token,
        settings.secret,
        algorithms=[ALGORITHM],
        issuer=ISSUER,
        audience=AUDIENCE,
        options={"require": ["sub", "exp", "iat", "iss", "aud"]},
    )
    subject = claims["sub"]
    if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal():
        raise jwt.InvalidTokenError("Invalid subject")
    if len(subject) > 10 or not 0 < int(subject) <= 2147483647:
        raise jwt.InvalidTokenError("Invalid subject")
    if any(type(claims[k]) is not int for k in ("iat", "exp")):
        raise jwt.InvalidTokenError("Invalid timestamps")
    if claims["exp"] <= claims["iat"]:
        raise jwt.InvalidTokenError("Invalid lifetime")
    return int(subject)
