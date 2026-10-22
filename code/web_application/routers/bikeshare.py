"""Authenticate before multipart parsing and bound the entire incoming body."""

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from multipart.exceptions import MultipartParseError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from src.bikeshare.service import ServiceBusy
from src.bikeshare.trips import MAX_BYTES

from .auth import require_user

MAX_REQUEST_BYTES = MAX_BYTES + 65536


class BodyLimitExceeded(MultiPartException):
    pass


class BodyTimeout(MultiPartException):
    pass


async def bounded_parts(request):
    length = request.headers.get("content-length")
    if length is not None:
        if not length.isdecimal() or len(length) > 12:
            raise HTTPException(400, "Invalid upload length.")
        if int(length) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "The complete multipart upload exceeds its size limit.")
    if request.headers.get("content-type", "").split(";")[0].lower() != "multipart/form-data":
        raise HTTPException(422, "Supply one CSV file and one pricing URL as multipart form data.")
    deadline = time.monotonic() + 15

    async def stream():
        size = 0
        iterator = request.stream().__aiter__()
        while True:
            try:
                chunk = await asyncio.wait_for(
                    anext(iterator), timeout=max(0.001, deadline - time.monotonic())
                )
            except StopAsyncIteration:
                break
            except TimeoutError:
                raise BodyTimeout("Upload timed out.") from None
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                raise BodyLimitExceeded("The complete multipart upload exceeds its size limit.")
            yield chunk

    parser = MultiPartParser(request.headers, stream(), max_files=1, max_fields=1)
    try:
        try:
            return await parser.parse()
        except BaseException:
            # Pinned Starlette closes these only for MultiPartException, not malformed bytes or cancellation.
            for spool in parser._files_to_close_on_error:
                spool.close()
            raise
    except BodyLimitExceeded as exc:
        raise HTTPException(413, exc.message) from None
    except BodyTimeout as exc:
        raise HTTPException(408, exc.message) from None
    except (MultiPartException, MultipartParseError):
        raise HTTPException(422, "Supply exactly one CSV file and one pricing URL.") from None


def create_router(service):
    router = APIRouter(prefix="/api/bikeshare", tags=["Bike-share"])

    @router.post(
        "/runs",
        status_code=202,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string", "format": "binary"},
                                "pricing_url": {"type": "string", "format": "uri"},
                            },
                            "required": ["file", "pricing_url"],
                            "additionalProperties": False,
                        }
                    }
                },
            }
        },
    )
    async def create_run(request: Request, user=Depends(require_user)):
        form = await bounded_parts(request)
        try:
            file, pricing_url = form.get("file"), form.get("pricing_url")
            if not isinstance(file, UploadFile) or not isinstance(pricing_url, str):
                raise HTTPException(422, "Supply exactly one CSV file and one pricing URL.")
            contents = await file.read(MAX_BYTES + 1)
            if len(contents) > MAX_BYTES:
                raise HTTPException(413, "The CSV exceeds 5 MiB.")
            try:
                return await run_in_threadpool(service.submit, user.id, contents, pricing_url)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            except ServiceBusy as exc:
                raise HTTPException(429, str(exc)) from None
        finally:
            await form.close()

    @router.get("/runs/{run_id}")
    def get_run(run_id: str, user=Depends(require_user)):
        try:
            return service.get(user.id, run_id)
        except FileNotFoundError:
            raise HTTPException(404, "Run not found.") from None

    return router
