"""JSON authentication endpoints backed by revocable MySQL login records."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..session_store import (
    ABSOLUTE_TIMEOUT_SECONDS,
    COOKIE_NAME,
    authenticate_session,
    create_session,
    revoke_session,
)


router = APIRouter(prefix="/api/auth", tags=["Authentication"])
NO_STORE = {"Cache-Control": "no-store"}
PASSWORD_HASHER = PasswordHasher()
# This hash belongs to no account. Unknown emails still perform Argon2 work,
# instead of revealing account existence through a fast password-check path.
_DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("hw4-dummy-password-not-an-account")


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class PublicUser(BaseModel):
    id: int
    name: str
    email: str


class UserResponse(BaseModel):
    user: PublicUser


def public_user(user: User) -> UserResponse:
    """Select public attributes explicitly, excluding password/session material."""
    return UserResponse(user=PublicUser(id=user.id, name=user.name, email=user.email))


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax"
    )


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = authenticate_session(
        db,
        request.cookies.get(COOKIE_NAME),
        request.app.state.clock(),
        request.app.state.idle_timeout,
    )
    if user is None:
        raise HTTPException(
            status_code=401, detail="Authentication required.", headers=NO_STORE
        )
    return user


@router.post("/login", response_model=UserResponse)
def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email)))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    try:
        verified = PASSWORD_HASHER.verify(password_hash, payload.password)
    except (VerificationError, InvalidHashError):
        verified = False

    # Replacing a login also revokes its old token server-side. Failed credentials
    # discard that existing login as well, matching the prior application's flow.
    revoke_session(db, request.cookies.get(COOKIE_NAME))
    if user is None or not verified:
        db.commit()
        failure = JSONResponse(
            status_code=401,
            content={"detail": "Invalid email or password."},
            headers=NO_STORE,
        )
        clear_session_cookie(failure)
        return failure

    token = create_session(db, user.id, request.app.state.clock())
    db.commit()
    response.headers.update(NO_STORE)
    response.set_cookie(
        COOKIE_NAME,
        token.id,
        max_age=ABSOLUTE_TIMEOUT_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return public_user(user)


@router.get("/me", response_model=UserResponse)
def me(response: Response, user: User = Depends(require_user)):
    response.headers.update(NO_STORE)
    return public_user(user)


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    revoke_session(db, request.cookies.get(COOKIE_NAME))
    db.commit()
    response = Response(status_code=204, headers=NO_STORE)
    clear_session_cookie(response)
    return response
