"""The shared homework service: MySQL API and same-origin React application."""

import sys
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# `code` is also a stdlib module. Use web_application as the package; support
# existing arbitrary-name main.py imports without importing `code` itself.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_application.database import SessionLocal
from web_application.jwt_security import JWTSettings
from web_application.query_metrics import QueryMetricsMiddleware, install_query_counter
from web_application.routers import auth, performance, property_managers, rentals

PORT_BASE = 8702
ROOT = Path(__file__).resolve().parents[2]


def create_app(
    *,
    session_factory=None,
    frontend_dist=None,
    hw6_config=None,
    hw6_window_policy=None,
    hw6_telemetry=None,
    hw6_connection=None,
    hw6_model=None,
    hw6_embedder=None,
    hw6_count_tokens=None,
) -> FastAPI:
    app = FastAPI(title="Rental Housing Listings", version="7.1.0")
    app.state.jwt_settings = JWTSettings.from_env()
    app.state.session_factory = session_factory or SessionLocal

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's `input` can contain a submitted password. Keep useful
        # field locations/messages while never echoing submitted credentials.
        detail = [
            {key: error[key] for key in ("type", "loc", "msg") if key in error}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": detail})

    app.include_router(auth.router)
    # Literal performance paths must precede the dynamic rental-ID routes.
    install_query_counter()
    app.add_middleware(QueryMetricsMiddleware)
    app.include_router(performance.router)
    app.include_router(rentals.router)
    app.include_router(property_managers.router)

    if hw6_config is not None:
        from web_application.routers import chat, doc_rentals

        from src.hw06_shared.errors import install_error_handlers
        from src.hw06_shared.runtime import build_runtime

        runtime = build_runtime(
            hw6_config,
            connection=hw6_connection,
            model=hw6_model,
            embedder=hw6_embedder,
            count_tokens=hw6_count_tokens,
            telemetry=hw6_telemetry,
            window_policy=hw6_window_policy,
        )
        app.state.hw6_runtime = runtime
        app.add_event_handler("shutdown", runtime.close)
        install_error_handlers(app)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(runtime.config.cors_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-HW6-Request-ID",
                "X-HW6-Run-ID",
                "X-HW6-Condition",
                "X-HW6-Turn-ID",
                "X-HW6-Probe-ID",
                "X-HW6-Phase",
            ],
        )
        app.include_router(doc_rentals.create_router(runtime.document_service))
        app.include_router(chat.create_router(runtime.chat_service))

        @app.get("/api/hw06/config", dependencies=[Depends(auth.require_user)])
        def hw6_configuration():
            return {
                "config": runtime.config.public_dict(),
                "source_commit": runtime.config.source_commit,
                "file_memory_enabled": False,
            }

    @app.middleware("http")
    async def no_store_api(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(("/api/", "/auth/")):
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
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})

    for route in ("/", "/login", "/create", "/update", "/delete"):
        app.add_api_route(route, frontend, methods=["GET"], include_in_schema=False)

    @app.get("/dashboard", include_in_schema=False)
    def old_dashboard():
        return RedirectResponse("/", status_code=303)

    return app


app = create_app()
