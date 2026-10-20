"""One complete instrumented chat turn; main counts stay separate from memory work."""
from copy import deepcopy
from dataclasses import asdict
import json
from threading import RLock
from time import perf_counter

from pymongo.errors import PyMongoError

from src.hw06_shared.contracts import (
    AggregateResponse, ChatResponse, MemorySnapshot, MemoryUsed)
from src.hw06_shared.errors import (
    ContextLimitExceeded, HW6Error, ModelUnavailable, StorageUnavailable)
from src.hw06_shared.models import usage_counts
from src.hw06_shared.serialization import new_id, utc_now, json_value
from src.hw06_shared.telemetry import CallEvent, NullTelemetry, RequestContext, TokenComponents
from .logic import (EXTRACTION_PRIMER, SESSION_PRIMER, LIFETIME_PRIMER,
                    assemble_prompt, extract_facts, rank_episodes, valid_vector)


class MongoMemoryService:
    def __init__(self, *, model, embedder, storage, config, count_tokens,
                 clock=utc_now, telemetry=None, window_policy=None):
        if config.policy != 'baseline' and window_policy is None:
            raise ValueError('Configured window policy must be injected')
        self.model, self.embedder, self.storage = model, embedder, storage
        self.config, self.count_tokens, self.clock = config, count_tokens, clock
        self.telemetry = telemetry if telemetry is not None else NullTelemetry()
        self.window_policy = window_policy
        # The local adapter and a session's summary cadence require ordered turns.
        # This lock covers one service process; deployments with multiple workers
        # need a shared per-user queue/lock rather than concurrent writes.
        self._turn_lock = RLock()

    def _event(self, context, user_id, session_id, kind, operation, started_at,
               timer, *, error=None, **fields):
        self.telemetry.emit(CallEvent(context=context, kind=kind, operation=operation,
            started_at=started_at, user_id=user_id, session_id=session_id,
            latency_ms=(perf_counter() - timer) * 1000,
            status='error' if error else 'ok', error_code=error.code if error else None,
            config=self.config.public_dict(), **fields))

    def _check_context(self, messages):
        # Qwen's chat delimiters are counted only for a preflight estimate. The
        # reported model count, not this estimate, is the measured prompt total.
        rendered = ''.join(f'<|im_start|>{role}\n{text}<|im_end|>\n'
                           for role, text in messages) + '<|im_start|>assistant\n'
        if self.count_tokens(rendered) + self.config.output_limit > self.config.context_window:
            raise ContextLimitExceeded()

    def _complete(self, messages):
        self._check_context(messages)
        try:
            result = self.model.complete(messages)
        except Exception:
            raise ModelUnavailable() from None
        return result

    def _validate_result(self, result, counts):
        if not isinstance(result.content, str) or not result.content.strip():
            raise ModelUnavailable()
        if counts.get('prompt_tokens') is not None and (
                counts['prompt_tokens'] + self.config.output_limit > self.config.context_window):
            raise ContextLimitExceeded()

    def _auxiliary(self, operation, system, data, context, user_id, session_id):
        started_at, timer, counts, error = self.clock(), perf_counter(), {}, None
        try:
            result = self._complete([('system', system),
                                     ('user', json.dumps(json_value(data), ensure_ascii=False))])
            counts = asdict(usage_counts(result))
            self._validate_result(result, counts)
            return result.content.strip()
        except HW6Error as exc:
            error = exc
            raise
        finally:
            self._event(context, user_id, session_id, 'generation', operation,
                        started_at, timer, error=error, **counts)

    def _embed(self, text, operation, context, user_id, session_id):
        started_at, timer, error, dimension = self.clock(), perf_counter(), None, None
        try:
            try:
                vector = valid_vector(self.embedder(text), self.config.embedding_dimension)
            except Exception:
                raise ModelUnavailable() from None
            dimension = len(vector)
            return vector
        except HW6Error as exc:
            error = exc
            raise
        finally:
            self._event(context, user_id, session_id, 'embedding', operation,
                started_at, timer, error=error, usage_source='not_applicable',
                input_count=1, embedding_dimension=dimension)

    def _window(self, user_id, session_id, current):
        candidates = self.storage.recent_messages(user_id, session_id,
            self.config.short_term_n, exclude_id=current['id'])
        if self.window_policy is None:
            return candidates
        selected = self.window_policy(deepcopy(candidates),
            short_term_n=self.config.short_term_n, token_budget=self.config.token_budget,
            count_tokens=self.count_tokens)
        # Verify seam integrity, without implementing D's choice of retention.
        remaining = iter(candidates)
        for row in selected:
            if not any(candidate == row for candidate in remaining):
                raise HW6Error('Window policy changed or reordered source records')
        return selected

    def _update_summaries(self, user_id, session_id, context):
        count = self.storage.user_message_count(user_id, session_id)
        if count % self.config.summarize_every_user_msgs:
            return
        previous = self.storage.latest_summary(user_id, 'session', session_id)
        if previous and previous.get('user_message_count') == count:
            return
        messages = self.storage.summary_messages(user_id, session_id, previous)
        text = self._auxiliary('session_summary', SESSION_PRIMER,
            {'previous_summary': previous['text'] if previous else None,
             'new_records': messages}, context, user_id, session_id)
        self.storage.add_summary(user_id, session_id, 'session', text, self.clock(),
            user_message_count=count, through_message={
                'id': messages[-1]['id'], 'created_at': messages[-1]['created_at']})
        sessions = self.storage.latest_session_summaries(user_id)
        if len(sessions) < 2:
            return
        text = self._auxiliary('lifetime_summary', LIFETIME_PRIMER,
            {'latest_session_summaries': sessions}, context, user_id, session_id)
        self.storage.add_summary(user_id, None, 'user', text, self.clock(),
            source_summary_ids=[row['id'] for row in sessions])

    def chat(self, request, *, context=None):
        started_at, timer = self.clock(), perf_counter()
        context = (context or RequestContext()).model_copy(
            update={'source_commit': self.config.source_commit})
        session_id = request.session_id or new_id()
        user_id, counts, parts, components, error = request.user_id, {}, None, None, None
        try:
            with self._turn_lock:
                self.storage.ensure_indexes()
                current = self.storage.add_message(user_id, session_id, 'user', request.message, self.clock())
                window = self._window(user_id, session_id, current)
                session_summary = self.storage.latest_summary(user_id, 'session', session_id)
                lifetime_summary = self.storage.latest_summary(user_id, 'user')
                query = self._embed(request.message, 'query', context, user_id, session_id)
                episodes = rank_episodes(query, self.storage.episodes(user_id),
                    dimension=self.config.embedding_dimension, top_k=self.config.top_k)
                messages, parts = assemble_prompt(window, session_summary, lifetime_summary,
                                                  episodes, request.message)
                components = TokenComponents(**{name: self.count_tokens(text) if text else 0
                    for name, text in parts.model_dump().items()},
                    tokenizer_identity=getattr(self.count_tokens, 'identity', None))
                result = self._complete(messages)
                counts = asdict(usage_counts(result))
                if counts['prompt_tokens'] is not None:
                    component_sum = sum(getattr(components, key) for key in type(parts).model_fields)
                    components.template_residual = counts['prompt_tokens'] - component_sum
                self._validate_result(result, counts)
                self.storage.add_message(user_id, session_id, 'assistant', result.content, self.clock())
                extracted = self._auxiliary('extraction', EXTRACTION_PRIMER,
                    {'user_message': request.message}, context, user_id, session_id)
                for fact in extract_facts(extracted, request.message):
                    vector = self._embed(fact.fact, 'fact', context, user_id, session_id)
                    self.storage.add_episode(user_id, session_id, fact.fact, fact.importance,
                                             vector, self.clock())
                self._update_summaries(user_id, session_id, context)
                return ChatResponse(user_id=user_id, session_id=session_id,
                    request_id=context.request_id, reply=result.content,
                    memory_used=MemoryUsed(short_term_count=len(window), short_term_messages=window,
                        session_summary=session_summary['text'] if session_summary else None,
                        lifetime_summary=lifetime_summary['text'] if lifetime_summary else None,
                        episodes=episodes, policy=self.config.policy))
        except PyMongoError:
            error = StorageUnavailable()
            raise error from None
        except HW6Error as exc:
            error = exc
            raise
        except Exception:
            error = HW6Error()
            raise error from None
        finally:
            self._event(context, user_id, session_id, 'request', 'chat', started_at, timer,
                        error=error, components=components, component_text=parts, **counts)

    def memory(self, user_id, *, session_id=None):
        try:
            selected = session_id if session_id is not None else self.storage.latest_session(user_id)
            return MemorySnapshot(user_id=user_id, session_id=selected,
                messages=self.storage.recent_messages(user_id, selected, 16),
                session_summary=self.storage.latest_summary(user_id, 'session', selected) if selected else None,
                lifetime_summary=self.storage.latest_summary(user_id, 'user'),
                episodes=self.storage.episodes(user_id, limit=20))
        except PyMongoError:
            raise StorageUnavailable() from None

    def aggregate(self, user_id):
        """Daily UTC counts include both roles across all sessions for this user."""
        try:
            return AggregateResponse(user_id=user_id,
                daily_message_counts=self.storage.daily_message_counts(user_id),
                recent_summaries=self.storage.recent_summaries(user_id))
        except PyMongoError:
            raise StorageUnavailable() from None
