"""HTML authentication routes for the Rental Housing Listings teaching app."""

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
NO_STORE = {"Cache-Control": "no-store"}


def current_user(request: Request) -> str | None:
    """Trust a signed cookie only while its matching server session is active."""
    session = request.session
    sid = session.get("sid") if isinstance(session, dict) else None
    user = session.get("user") if isinstance(session, dict) else None
    user = request.app.state.session_store.authenticate(sid, user)
    if user is None:
        request.scope["session"] = {}
    return user


def revoke_session(request: Request) -> None:
    session = request.session
    sid = session.get("sid") if isinstance(session, dict) else None
    request.app.state.session_store.revoke(sid)
    request.scope["session"] = {}


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={"user": current_user(request)}, headers=NO_STORE,
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"user": current_user(request), "error": None}, headers=NO_STORE,
    )


@router.post(
    "/login", response_class=RedirectResponse, status_code=303,
    response_description="Redirect to the dashboard after successful login.",
    responses={401: {
        "description": "Invalid credentials; display the login form with an error.",
        "content": {"text/html": {"schema": {"type": "string"}}},
    }},
)
async def login(request: Request, username: str = Form(""), password: str = Form("")):
    # Replacement and unsuccessful login attempts both discard the old login.
    revoke_session(request)
    if username != "admin" or password != "password":
        return templates.TemplateResponse(
            request=request, name="login.html",
            context={"user": None, "error": "Invalid username or password."},
            status_code=401, headers=NO_STORE,
        )
    sid = request.app.state.session_store.create(username)
    request.session.update({"user": username, "sid": sid})
    return RedirectResponse("/dashboard", status_code=303, headers=NO_STORE)


@router.get(
    "/dashboard", response_class=HTMLResponse,
    responses={303: {"description": "Redirect to login when no active session exists."}},
)
async def dashboard(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303, headers=NO_STORE)
    return templates.TemplateResponse(
        request=request, name="dashboard.html",
        context={"user": user, "idle_timeout": request.app.state.session_store.idle_timeout},
        headers=NO_STORE,
    )


@router.get(
    "/logout", response_class=RedirectResponse, status_code=303,
    response_description="Redirect home after revoking the session.",
)
async def logout(request: Request):
    revoke_session(request)
    return RedirectResponse("/", status_code=303, headers=NO_STORE)
