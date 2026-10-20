"""Sanitized service errors with stable HTTP behavior for worker routers."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class HW6Error(RuntimeError):
    status_code = 500
    code = "internal_error"
    public_message = "The request could not be completed."


class StorageUnavailable(HW6Error):
    status_code = 503
    code = "storage_unavailable"
    public_message = "Document storage is unavailable."


class ModelUnavailable(HW6Error):
    status_code = 503
    code = "model_unavailable"
    public_message = "The local model is unavailable."


class ModelOutputLimitExceeded(HW6Error):
    status_code = 503
    code = "model_output_limit_exceeded"
    public_message = "The local model stopped before completing its response."


class ContextLimitExceeded(HW6Error):
    status_code = 422
    code = "context_limit_exceeded"
    public_message = "The prompt exceeds the configured context budget."


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HW6Error)
    async def hw6_error(request: Request, exc: HW6Error):
        return JSONResponse(status_code=exc.status_code, content={
            "detail": exc.public_message, "code": exc.code})
