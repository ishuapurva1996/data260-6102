"""Authenticated HW9 Q&A at the existing Kafka ingress."""

import asyncio
from time import perf_counter

import httpx
from aiokafka.errors import KafkaError
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.hw09.semantic_cache import (
    DIMENSION,
    MODEL,
    MODEL_DIGEST,
    MODEL_INPUT_PREFIX,
    VECTOR,
    CacheSettings,
    SemanticCache,
    build_embedder,
    verify_embedding_model,
)
from src.kafka_agents.question_client import send_question
from src.kafka_service.logging import event, timed_span

from ..database import get_db
from ..rental_facts import rental_fact_snapshot, rental_version
from .auth import require_user


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)


class QuestionResponse(BaseModel):
    answer: str
    is_cached: bool
    similarity: float | None
    latency_ms: float
    request_id: str


def create_router(session_factory):
    settings = CacheSettings.from_env()
    cache = SemanticCache(settings)
    embed = build_embedder()
    router = APIRouter(prefix="/api/kafka", tags=["HW9 semantic cache"])

    @router.on_event("startup")
    def start():
        verify_embedding_model(embed)
        with session_factory() as db:
            rental_version(db)
        cache.create_index()
        event(
            "semantic_cache_ready",
            namespace=settings.namespace,
            threshold=settings.threshold,
            allow_stale=settings.allow_stale,
            index=cache.index,
            embedding_model=MODEL,
            embedding_digest=MODEL_DIGEST,
            embedding_dimension=DIMENSION,
        )

    @router.on_event("shutdown")
    def stop():
        cache.close()
        embed.close()

    def lookup(vector, user_id, timings):
        started = perf_counter()
        with session_factory() as db:
            dataset_id, version = rental_version(db, lock=True)
            timings["version_ms"] = elapsed(started)
            started = perf_counter()
            candidate = cache.closest(vector, dataset_id, version, user_id)
            timings["lookup_ms"] = elapsed(started)
        return (dataset_id, version), candidate

    def store_if_current(vector, question, answer, facts, user_id, request_id):
        # Keep the version row locked through HSET. A competing SQL rental
        # write either committed already or advances the version after HSET.
        with session_factory() as db:
            marker = facts["dataset_id"], facts["data_version"]
            if rental_version(db, lock=True) != marker:
                return "skipped_version_changed"
            cache.save(
                vector,
                question=question,
                answer=answer,
                dataset_id=marker[0],
                data_version=marker[1],
                user_id=user_id,
                request_id=request_id,
            )
            return "stored"

    @router.post("/questions", response_model=QuestionResponse)
    async def question_endpoint(
        payload: QuestionInput,
        request: Request,
        user=Depends(require_user),
        auth_db: Session = Depends(get_db),
    ):
        user_id = user.id
        # Release the shared authentication session before borrowing connections
        # for independent, short-lived fact snapshots and version locks.
        await asyncio.to_thread(auth_db.close)
        start_time = request.state.hw9_question_started
        question = payload.question
        request_id = request.state.question_request_id
        api_span = request.state.question_span
        timings = {}
        candidate = None
        marker = (None, None)
        cache_write = None
        pipeline_attempted = False
        is_cached = False
        error = None
        try:
            with timed_span(request_id, "cache_lookup", cache_outcome=None) as cache_span:
                started = perf_counter()
                vector = await asyncio.to_thread(
                    lambda: VECTOR.pack(*embed(MODEL_INPUT_PREFIX + question))
                )
                timings["embed_ms"] = elapsed(started)
                marker, candidate = await asyncio.to_thread(lookup, vector, user_id, timings)
                is_cached = candidate is not None and candidate["similarity"] >= settings.threshold
                cache_outcome = "hit" if is_cached else "miss"
                cache_span["cache_outcome"] = api_span["cache_outcome"] = cache_outcome
                if is_cached:
                    cache_span["source_request_id"] = candidate["source_request_id"]
            if is_cached:
                answer = candidate["answer"]
            else:
                started = perf_counter()
                facts = await asyncio.to_thread(rental_fact_snapshot, session_factory, question)
                timings["facts_ms"] = elapsed(started)
                fact_marker = facts["dataset_id"], facts["data_version"]
                if marker != fact_marker:
                    candidate = None
                    marker = fact_marker
                started = perf_counter()
                pipeline_attempted = True
                try:
                    async with asyncio.timeout(180):
                        result = await send_question(
                            question,
                            correlation_id=request_id,
                            rental_context=facts,
                        )
                finally:
                    timings["kafka_agent_ms"] = elapsed(started)
                final = result["final"]
                if final["status"] != "approved" or final.get("from_stage") != "reviewer":
                    raise ValueError("Question pipeline did not return an approved final answer.")
                answer = final["answer"]
                started = perf_counter()
                try:
                    cache_write = await asyncio.to_thread(
                        store_if_current,
                        vector,
                        question,
                        answer,
                        facts,
                        user_id,
                        request_id,
                    )
                except (RedisError, SQLAlchemyError) as exc:
                    cache_write = f"failed_{type(exc).__name__}"
                timings["cache_write_ms"] = elapsed(started)
        except TimeoutError as exc:
            error = type(exc).__name__
            api_span["error"] = error
            raise HTTPException(504, "The question pipeline timed out.") from exc
        except (KafkaError, RedisError, SQLAlchemyError, httpx.HTTPError, ValueError) as exc:
            error = type(exc).__name__
            api_span["error"] = error
            raise HTTPException(503, "The question service is temporarily unavailable.") from exc
        finally:
            latency_ms = elapsed(start_time)
            similarity = candidate["similarity"] if candidate else None
            event(
                "semantic_cache_result",
                correlation_id=request_id,
                request_id=request_id,
                namespace=settings.namespace,
                threshold=settings.threshold,
                question=question,
                is_cached=is_cached,
                similarity=similarity,
                dataset_id=marker[0],
                data_version=marker[1],
                matched_question=candidate["question"] if candidate else None,
                matched_data_version=candidate["data_version"] if candidate else None,
                matched_request_id=candidate["source_request_id"] if candidate else None,
                version_enforced=not settings.allow_stale,
                pipeline_attempted=pipeline_attempted,
                cache_write=cache_write,
                latency_ms=latency_ms,
                timings_ms=timings,
                error=error,
            )
        return QuestionResponse(
            answer=answer,
            is_cached=is_cached,
            similarity=similarity,
            latency_ms=latency_ms,
            request_id=request_id,
        )

    return router


def elapsed(started):
    return round((perf_counter() - started) * 1000, 3)
