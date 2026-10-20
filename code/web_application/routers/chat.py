"""Mountable authenticated memory routes; shared main.py owns final wiring."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from src.hw06_shared.contracts import (
    AggregateResponse, ChatRequest, ChatResponse, MemorySnapshot, authorize_memory_user)
from src.hw06_shared.telemetry import request_context_from_headers
from .auth import require_user


def create_router(service, *, current_user_dependency=require_user):
    router = APIRouter(prefix='/api', tags=['conversation memory'])
    config = getattr(service, 'config', None)

    @router.post('/chat', response_model=ChatResponse)
    def chat(payload: ChatRequest, request: Request, response: Response,
             principal=Depends(current_user_dependency)):
        authorize_memory_user(payload.user_id, principal)
        try:
            context = request_context_from_headers(request.headers,
                source_commit=getattr(config, 'source_commit', None))
        except ValidationError:
            raise HTTPException(422, 'Invalid HW6 experiment headers.') from None
        response.headers['Cache-Control'] = 'no-store'
        return service.chat(payload, context=context)

    @router.get('/memory/{user_id}', response_model=MemorySnapshot,
                description='Latest 16 records in the selected/latest session, latest summaries '
                            'and last 20 user episodes. Lists oldest first.')
    def memory(user_id: str, response: Response,
               session_id: str | None = Query(None, min_length=1, max_length=200),
               principal=Depends(current_user_dependency)):
        authorize_memory_user(user_id, principal)
        response.headers['Cache-Control'] = 'no-store'
        return service.memory(user_id, session_id=session_id)

    @router.get('/aggregate/{user_id}', response_model=AggregateResponse,
                description='UTC daily counts of stored user AND assistant messages across '
                            'all user sessions; latest 10 summaries newest first.')
    def aggregate(user_id: str, response: Response, principal=Depends(current_user_dependency)):
        authorize_memory_user(user_id, principal)
        response.headers['Cache-Control'] = 'no-store'
        return service.aggregate(user_id)

    return router
