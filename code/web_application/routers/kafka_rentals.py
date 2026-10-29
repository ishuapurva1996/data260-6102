"""Authenticated Kafka delegation within the existing rental application."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from .auth import require_user


def create_router(rpc):
    router = APIRouter(prefix="/api/kafka", tags=["HW8 Kafka rentals"])

    @router.post("/rentals")
    async def rental_operation(payload: dict, user=Depends(require_user)):
        if payload.get("operation") == "CREATE_RENTAL" and user.role not in {"writer", "moderator"}:
            raise HTTPException(403, "Your role does not permit this action.")
        response = await rpc.make_request(payload)
        return JSONResponse(
            status_code=503 if response.get("transport_error") else 200, content=response
        )

    return router
