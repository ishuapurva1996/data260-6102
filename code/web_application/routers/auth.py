"""JSON username/password login and MySQL-backed JWT bearer authorization."""

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..jwt_security import ROLES, issue_token, token_subject
from ..models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])
PASSWORD_HASHER = PasswordHasher()
_DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("not-an-account-hw7")
bearer_scheme = HTTPBearer(auto_error=False)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PublicUser(BaseModel):
    id: int
    username: str
    role: str
    name: str
    email: str


class UserResponse(BaseModel):
    user: PublicUser


def unauthorized(detail="Authentication required."):
    return HTTPException(
        401, detail, headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"}
    )


def require_user(
    request: Request,
    credential: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credential is None:
        raise unauthorized()
    try:
        user_id = token_subject(credential.credentials, request.app.state.jwt_settings)
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
        raise unauthorized("Invalid or expired access token.") from None
    user = db.get(User, user_id)
    if user is None or user.role not in ROLES:
        raise unauthorized("Account is unavailable.")
    return user


def require_roles(*allowed_roles, user_dependency=require_user):
    def check_role(user=Depends(user_dependency)):
        if user.role not in allowed_roles:
            raise HTTPException(403, "Your role does not permit this action.")
        return user

    return check_role


can_write = require_roles("writer", "moderator")
can_delete = require_roles("moderator")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    try:
        verified = PASSWORD_HASHER.verify(password_hash, payload.password)
    except (VerificationError, InvalidHashError):
        verified = False
    if user is None or not verified or user.role not in ROLES:
        raise unauthorized("Invalid username or password.")
    settings = request.app.state.jwt_settings
    return TokenResponse(
        access_token=issue_token(user.id, settings), expires_in=settings.ttl_seconds
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(require_user)):
    return UserResponse(user=PublicUser(**{k: getattr(user, k) for k in PublicUser.model_fields}))
