"""The shared HW4 service: MySQL API and same-origin React application."""
from datetime import datetime, timezone
import math
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# `code` is also a stdlib module. Use web_application as the package; support
# existing arbitrary-name main.py imports without importing `code` itself.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_application.database import SessionLocal
from web_application.routers import auth, rentals

PORT_BASE = 8702
ROOT = Path(__file__).resolve().parents[2]


def utc_now():
    """MySQL DATETIME values represent UTC without a timezone suffix."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_app(*, session_factory=None, clock=utc_now, idle_timeout=300,
               frontend_dist=None) -> FastAPI:
    if not math.isfinite(idle_timeout) or idle_timeout <= 0:
        raise ValueError("idle timeout must be positive and finite")
    app = FastAPI(title="Rental Housing Listings", version="4.0.0")
    app.state.session_factory = session_factory or SessionLocal
    app.state.clock = clock
    app.state.idle_timeout = idle_timeout

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's `input` can contain a submitted password. Keep useful
        # field locations/messages while never echoing submitted credentials.
        detail = [{key: error[key] for key in ("type", "loc", "msg") if key in error}
                  for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": detail})

    app.include_router(auth.router)
    # Part 3 registers its literal /naive and /fixed paths here, BEFORE rentals.
    app.include_router(rentals.router)

    @app.middleware("http")
    async def no_store_api(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "Rental Housing Listings"}

    dist = Path(frontend_dist) if frontend_dist is not None else ROOT / "frontend/dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    def frontend():
        if not (dist / "index.html").is_file():
            return HTMLResponse(
                "<h1>React build is missing</h1><p>Run npm ci and npm run build "
                "inside frontend/, then restart the server. The API is available at /docs.</p>",
                status_code=503, headers={"Cache-Control": "no-store"})
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})

    for route in ("/", "/login", "/create", "/update", "/delete"):
        app.add_api_route(route, frontend, methods=["GET"], include_in_schema=False)

    @app.get("/dashboard", include_in_schema=False)
    def old_dashboard():
        return RedirectResponse("/", status_code=303)

    return app


app = create_app()
