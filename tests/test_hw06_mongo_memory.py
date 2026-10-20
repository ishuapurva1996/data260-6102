"""Offline engineering checks; fake Mongo/model outputs are not live evidence."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from types import SimpleNamespace

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from pymongo.errors import ConnectionFailure

from src.model_client import CompletionResult, TokenUsage
from src.hw06_shared.config import HW6Config
from src.hw06_shared.contracts import ChatRequest, render_window
from src.hw06_shared.errors import ModelUnavailable, StorageUnavailable, install_error_handlers
from src.hw06_shared.telemetry import RequestContext
from src.hw06_memory_mongo.storage import MongoMemoryStorage
from src.hw06_memory_mongo.service import MongoMemoryService


NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def matches(row, query):
    for key, value in query.items():
        if key == '$or':
            if not any(matches(row, item) for item in value):
                return False
        elif isinstance(value, dict):
            for op, operand in value.items():
                if op == '$ne' and row.get(key) == operand:
                    return False
                if op == '$gt' and row.get(key) <= operand:
                    return False
                if op == '$in' and row.get(key) not in operand:
                    return False
        elif row.get(key) != value:
            return False
    return True


class Cursor(list):
    def sort(self, keys):
        for key, direction in reversed(keys):
            super().sort(key=lambda r: r[key], reverse=direction < 0)
        return self

    def limit(self, n):
        return Cursor(self[:n])


class Collection:
    def __init__(self):
        self.rows = []
        self.indexes = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def insert_one(self, doc):
        doc = deepcopy(doc)
        doc.setdefault('_id', ObjectId())
        self.rows.append(doc)
        return SimpleNamespace(inserted_id=doc['_id'])

    def find(self, query):
        return Cursor(deepcopy([r for r in self.rows if matches(r, query)]))

    def find_one(self, query, sort=None):
        rows = self.find(query)
        if sort:
            rows.sort(sort)
        return rows[0] if rows else None

    def count_documents(self, query):
        return len(self.find(query))

    def aggregate(self, pipeline):
        assert pipeline[1]['$group']['_id']['$dateToString']['timezone'] == 'UTC'
        counts = defaultdict(int)
        for row in self.find(pipeline[0]['$match']):
            counts[row['created_at'].astimezone(timezone.utc).strftime('%Y-%m-%d')] += 1
        return [{'_id': day, 'count': n} for day, n in sorted(counts.items())]


class Database(defaultdict):
    name = 's6102_doc'

    def __init__(self):
        super().__init__(Collection)


class Model:
    def __init__(self):
        self.calls = []
        self.reported = True
        self.facts = [{'fact': 'I need an elevator.', 'importance': 0.9,
                       'evidence': 'I need an elevator.'}]
        self.fail = None

    def complete(self, messages, tools=None):
        self.calls.append(deepcopy(messages))
        system = messages[0][1]
        if self.fail and self.fail in system:
            raise RuntimeError('PRIVATE_SENTINEL')
        if 'Extract' in system:
            content = json.dumps({'facts': self.facts})
        elif 'Summarize' in system:
            content = '- User needs an elevator; preserve corrections.'
        else:
            content = 'An elevator can help with access.'
        return CompletionResult(content, TokenUsage(100, 8, 108, self.reported), None)


class Counter:
    identity = 'offline-word-counter'

    def __call__(self, text):
        return len(text.split())


class Sink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


@pytest.fixture
def rig():
    def build(**overrides):
        database, model, sink = Database(), Model(), Sink()
        storage = MongoMemoryStorage(database)
        embedder = lambda text: [1.0, 0.0] if 'elevator' in text.lower() else [0.0, 1.0]
        service = MongoMemoryService(model=model, embedder=embedder, storage=storage,
            config=HW6Config(embedding_dimension=2, source_commit='server-sha', **overrides),
            count_tokens=Counter(), clock=lambda: NOW, telemetry=sink)
        return SimpleNamespace(service=service, db=database, storage=storage, model=model, sink=sink)
    return build


def chat(r, message='I need an elevator.', user='7', session='s'):
    return r.service.chat(ChatRequest(user_id=user, session_id=session, message=message))


@pytest.mark.parametrize('n', [0, 1, 3, 12])
def test_window_counts_previous_records_and_current_once(rig, n):
    r = rig(short_term_n=n)
    for index in range(8):
        result = chat(r, f'Unique message {index}')
        used = result.memory_used
        assert used.short_term_count == min(n, index * 2)
        assert all(m['content'] != f'Unique message {index}' for m in used.short_term_messages)
        main = [c for c in r.model.calls if 'Rental housing' in c[0][1]][-1]
        assert main[1][1].count(f'Unique message {index}') == 1
    assert len(r.db['messages'].rows) == 16
    assert r.storage.database is r.db
    assert set(r.db) == {'messages', 'summaries', 'episodes'}


def test_cadence_and_explicit_lifetime_rule_across_sessions(rig):
    r = rig()
    for i in range(10):
        result = chat(r)
        assert (result.memory_used.session_summary is not None) == (i >= 5)
    rows = r.db['summaries'].rows
    assert [(x['scope'], x['session_id']) for x in rows] == [('session', 's')] * 2
    for i in range(5):
        result = chat(r, session='second')
        assert result.memory_used.session_summary is None
        assert result.memory_used.lifetime_summary is None
    assert len(r.db['summaries'].rows) == 4
    lifetime = r.db['summaries'].rows[-1]
    assert lifetime['scope'] == 'user' and lifetime['session_id'] is None
    assert chat(r, session='third').memory_used.lifetime_summary
    for i in range(5):
        chat(r, session='s')
    assert len([x for x in r.db['summaries'].rows if x['scope'] == 'user']) == 2


def test_isolation_ranking_and_invalid_stored_vectors(rig):
    r = rig(top_k=2)
    def fact(user, session, text, vector):
        r.storage.add_episode(user, session, text, 0.8, vector, NOW)
    fact('7', 'old', 'elevator exact', [1.0, 0.0])
    fact('7', 'old', 'partial', [0.6, 0.8])
    fact('7', 'old', 'unrelated', [0.0, 1.0])
    fact('8', 's', 'PRIVATE other user', [1.0, 0.0])
    # Corrupt historic vectors are skipped during ranking; never propagate NaN.
    for vector in ([0.0, 0.0], [1.0], [float('nan'), 0.0]):
        r.db['episodes'].insert_one(dict(user_id='7', session_id='old', fact='bad',
            importance=0.5, embedding=vector, created_at=NOW))
    chat(r, user='8')
    result = chat(r)
    assert [e.fact for e in result.memory_used.episodes] == ['elevator exact', 'partial']
    assert result.memory_used.episodes[0].similarity == 1.0
    assert result.memory_used.short_term_count == 0
    assert not result.memory_used.session_summary
    assert all(m['user_id'] == '7' for m in r.service.memory('7').messages)


def test_inspection_limits_latest_session_and_utc_counts(rig):
    r = rig()
    for _ in range(12):
        chat(r)
    chat(r, user='8')
    snapshot = r.service.memory('7')
    assert len(snapshot.messages) == 16 and len(snapshot.episodes) == 12
    assert snapshot.session_id == 's'
    assert len(r.service.aggregate('7').daily_message_counts) == 1
    assert r.service.aggregate('7').daily_message_counts[0].count == 24
    chat(r, session='new')
    assert r.service.memory('7').session_id == 'new'
    assert r.service.memory('7', session_id='s').session_id == 's'
    assert r.service.memory('absent').messages == []
    r.storage.add_message('7', 'new', 'user', 'UTC boundary', NOW - timedelta(seconds=1))
    counts = r.service.aggregate('7').daily_message_counts
    assert [(x.date, x.count) for x in counts] == [('2026-10-19', 1), ('2026-10-20', 26)]


def test_fact_validation_cap_and_user_only_source(rig):
    r = rig()
    r.model.facts = [
        {'fact': 'assistant invented a pool', 'importance': 0.9, 'evidence': 'pool'},
        {'fact': '', 'importance': 0.4},
        {'fact': 'bad score', 'importance': 2},
        {'fact': 'not finite', 'importance': float('nan')},
    ] + [{'fact': f'Access requirement {i}', 'importance': 0.8,
          'evidence': 'elevator'} for i in range(5)]
    chat(r)
    assert len(r.db['episodes'].rows) == 3
    assert not any('pool' in x['fact'] for x in r.db['episodes'].rows)
    extraction = [c for c in r.model.calls if 'Extract' in c[0][1]][0]
    assert 'An elevator can help' not in extraction[1][1]


def test_telemetry_main_auxiliary_usage_and_residual(rig):
    r = rig(summarize_every_user_msgs=1)
    context = RequestContext(request_id='req', run_id='run', turn_id=1, phase='test')
    result = r.service.chat(ChatRequest(user_id='7', message='I need an elevator.'), context=context)
    assert result.session_id and result.request_id == 'req'
    events = r.sink.events
    assert [(e.kind, e.operation) for e in events] == [
        ('embedding', 'query'), ('generation', 'extraction'), ('embedding', 'fact'),
        ('generation', 'session_summary'), ('request', 'chat')]
    event = events[-1]
    assert all(e.context.request_id == 'req' for e in events)
    assert event.prompt_tokens == 100 and event.completion_tokens == 8
    component_sum = sum(getattr(event.components, name) for name in
        ('system', 'session_summary', 'lifetime_summary', 'window', 'episodes', 'current_message'))
    assert event.components.template_residual == 100 - component_sum
    assert event.components.tokenizer_identity == 'offline-word-counter'
    assert event.component_text.current_message == 'I need an elevator.'
    assert event.latency_ms >= sum(e.latency_ms for e in events[:-1])
    assert 'mongo_uri' not in event.config
    assert events[0].usage_source == 'not_applicable' and events[0].prompt_tokens is None
    assert all(e.prompt_tokens == 100 for e in events if e.kind == 'generation')
    r.model.reported = False
    chat(r)
    assert r.sink.events[-1].usage_source == 'missing'
    assert r.sink.events[-1].prompt_tokens is None
    assert r.sink.events[-1].components.template_residual is None


def test_model_and_storage_errors_emit_failed_request(rig):
    r = rig()
    r.model.fail = 'Rental housing'
    with pytest.raises(ModelUnavailable):
        chat(r)
    assert r.sink.events[-1].status == 'error'
    assert r.sink.events[-1].error_code == 'model_unavailable'
    assert len(r.db['messages'].rows) == 1
    r = rig()
    def unavailable(*args, **kwargs):
        raise ConnectionFailure('PRIVATE_SENTINEL')
    r.db['messages'].insert_one = unavailable
    with pytest.raises(StorageUnavailable):
        chat(r)
    assert len(r.sink.events) == 1 and r.sink.events[0].error_code == 'storage_unavailable'


def make_client(service, principal=SimpleNamespace(id=7)):
    from web_application.routers.chat import create_router
    def auth():
        if principal is None:
            raise HTTPException(401, 'Authentication required.')
        return principal
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(create_router(service, current_user_dependency=auth))
    return TestClient(app, raise_server_exceptions=False)


def test_mountable_routes_auth_validation_response_and_counts(rig):
    r = rig()
    with make_client(r.service) as client:
        response = client.post('/api/chat', json={'user_id': '7', 'message': 'I need an elevator.'},
            headers={'X-HW6-Request-ID': 'route-id', 'X-HW6-Source-Commit': 'spoof'})
        assert response.status_code == 200
        data = response.json()
        assert set(data) == {'user_id', 'session_id', 'request_id', 'reply', 'memory_used'}
        assert data['request_id'] == 'route-id' and data['session_id']
        assert r.sink.events[-1].context.source_commit == 'server-sha'
        assert client.get('/api/memory/7').json()['session_id'] == data['session_id']
        assert client.get('/api/aggregate/7').json()['daily_message_counts'][0]['count'] == 2
        for path in ['/api/memory/8', '/api/aggregate/8']:
            assert client.get(path).status_code == 403
        assert client.post('/api/chat', json={'user_id': '8', 'message': 'x'}).status_code == 403
        assert client.post('/api/chat', json={'user_id': '7', 'message': '  '}).status_code == 422
        assert client.post('/api/chat', json={'user_id': '7:hw6:test', 'message': 'x'},
            headers={'X-HW6-Turn-ID': '-1'}).status_code == 422
        assert len(r.db['messages'].rows) == 2
        assert client.post('/api/chat', json={'user_id': '7:hw6:test', 'message': 'x'}).status_code == 200
    with make_client(r.service, principal=None) as client:
        assert client.get('/api/memory/7').status_code == 401


def test_policy_receives_only_previous_n_records_and_does_not_touch_storage(rig):
    r = rig(short_term_n=3)
    for i in range(4):
        chat(r, f'old {i}')
    observed = []
    def policy(messages, **kwargs):
        observed.extend(deepcopy(messages))
        assert kwargs['short_term_n'] == 3
        assert kwargs['token_budget'] == 160
        return messages[-1:]
    r.service.window_policy = policy
    result = chat(r, 'current')
    assert len(observed) == 3 and observed[-1]['role'] == 'assistant'
    assert result.memory_used.short_term_count == 1
    assert len(r.db['messages'].rows) == 10
    assert r.sink.events[-1].component_text.window == render_window(result.memory_used.short_term_messages)


def test_bad_policy_cannot_inject_or_reorder_records(rig):
    r = rig()
    chat(r)
    r.service.window_policy = lambda messages, **kwargs: list(reversed(messages))
    with make_client(r.service) as client:
        response = client.post('/api/chat', json={'user_id': '7', 'session_id': 's', 'message': 'current'})
    assert response.status_code == 500
    assert response.json()['code'] == 'internal_error'
    assert r.sink.events[-1].status == 'error'


@pytest.mark.parametrize('vector', [[0.0, 0.0], [1.0], [float('inf'), 1.0], [True, 0.0]])
def test_invalid_query_embedding_is_failed_auxiliary_work(rig, vector):
    r = rig()
    r.service.embedder = lambda _: vector
    with pytest.raises(ModelUnavailable):
        chat(r)
    assert [(e.operation, e.status) for e in r.sink.events] == [('query', 'error'), ('chat', 'error')]
    assert all(e.prompt_tokens is None for e in r.sink.events)


@pytest.mark.parametrize('operation,needle', [('extraction', 'Extract'), ('session_summary', 'Summarize')])
def test_auxiliary_failure_retains_main_usage_and_fails_request(rig, operation, needle):
    r = rig(summarize_every_user_msgs=1)
    r.model.fail = needle
    with make_client(r.service) as client:
        response = client.post('/api/chat', json={'user_id': '7', 'message': 'I need an elevator.'})
    assert response.status_code == 503 and response.json()['code'] == 'model_unavailable'
    assert 'PRIVATE_SENTINEL' not in response.text
    event = r.sink.events[-1]
    assert event.status == 'error' and event.prompt_tokens == 100
    failure = [e for e in r.sink.events if e.operation == operation][-1]
    assert failure.status == 'error' and failure.usage_source == 'missing'
    assert len(r.db['messages'].rows) == 2  # partial durable turn; no silent retry


def test_context_guard_prevents_generation_and_records_selected_components(rig):
    r = rig(context_window=600, output_limit=512)
    with make_client(r.service) as client:
        response = client.post('/api/chat', json={'user_id': '7', 'message': 'word ' * 200})
    assert response.status_code == 422
    assert response.json()['code'] == 'context_limit_exceeded'
    assert r.model.calls == []
    event = r.sink.events[-1]
    assert event.components.current_message == 200
    assert event.status == 'error' and event.prompt_tokens is None


def test_summary_refresh_uses_only_new_records_and_latest_session_summaries(rig):
    r = rig(summarize_every_user_msgs=2)
    for _ in range(4):
        chat(r)
    session_calls = [c for c in r.model.calls if c[0][1].startswith('Summarize the supplied')]
    assert len(json.loads(session_calls[-1][1][1])['new_records']) == 4
    for _ in range(2):
        chat(r, session='other')
    lifetime = [c for c in r.model.calls if c[0][1].startswith('Summarize the latest')]
    summaries = json.loads(lifetime[0][1][1])['latest_session_summaries']
    assert len(summaries) == 2 and summaries[0]['user_message_count'] == 4
    assert r.sink.events[-2].operation == 'lifetime_summary'
    assert r.sink.events[-2].prompt_tokens == 100


def test_inspection_episode_and_summary_caps_and_order(rig):
    r = rig(summarize_every_user_msgs=1)
    for _ in range(22):
        chat(r)
    snapshot = r.service.memory('7')
    assert len(snapshot.episodes) == 20 and len(snapshot.messages) == 16
    assert [m['id'] for m in snapshot.messages] == sorted(m['id'] for m in snapshot.messages)
    summaries = r.service.aggregate('7').recent_summaries
    assert len(summaries) == 10
    assert [s['id'] for s in summaries] == sorted((s['id'] for s in summaries), reverse=True)


def test_indexes_utc_and_no_part1_collection_changes(rig):
    r = rig()
    r.db['rentals'].insert_one({'title': 'unchanged'})
    rentals = deepcopy(r.db['rentals'].rows)
    chat(r)
    assert r.db['rentals'].rows == rentals
    assert len(r.db['messages'].indexes) == 2
    assert len(r.db['summaries'].indexes) == len(r.db['episodes'].indexes) == 1
    chat(r)
    assert len(r.db['messages'].indexes) == 2
    assert all(row['created_at'].utcoffset() == timedelta(0) for row in r.db['messages'].rows)


def test_real_zero_usage_is_kept_and_component_residual_can_be_negative(rig):
    r = rig()
    r.model.complete = lambda messages: CompletionResult('{"facts": []}', TokenUsage(0, 0, 0), None)
    chat(r)
    event = r.sink.events[-1]
    assert event.prompt_tokens == event.completion_tokens == event.total_tokens == 0
    assert event.usage_source == 'model_reported'
    assert event.components.template_residual < 0


def test_auxiliary_reported_context_overflow_keeps_usage_and_error(rig):
    r = rig(context_window=1000)
    original = r.model.complete
    def complete(messages):
        result = original(messages)
        if 'Extract' in messages[0][1]:
            return CompletionResult(result.content, TokenUsage(900, 8, 908), None)
        return result
    r.model.complete = complete
    with make_client(r.service) as client:
        response = client.post('/api/chat', json={'user_id': '7', 'message': 'I need an elevator.'})
    assert response.status_code == 422
    extraction = r.sink.events[-2]
    assert extraction.operation == 'extraction' and extraction.prompt_tokens == 900
    assert extraction.error_code == 'context_limit_exceeded'
    assert r.sink.events[-1].prompt_tokens == 100


def test_fact_embedding_failure_has_own_event_and_main_usage(rig):
    r = rig()
    calls = []
    def embed(text):
        calls.append(text)
        return [1.0, 0.0] if len(calls) == 1 else [0.0, 0.0]
    r.service.embedder = embed
    with pytest.raises(ModelUnavailable):
        chat(r)
    assert r.sink.events[-2].operation == 'fact' and r.sink.events[-2].status == 'error'
    assert r.sink.events[-1].prompt_tokens == 100
    assert r.db['episodes'].rows == []


def test_empty_model_reply_keeps_real_usage_but_does_not_save_assistant(rig):
    r = rig()
    r.model.complete = lambda messages: CompletionResult('', TokenUsage(15, 0, 15), None)
    with pytest.raises(ModelUnavailable):
        chat(r)
    assert len(r.db['messages'].rows) == 1
    assert r.sink.events[-1].prompt_tokens == 15
    assert r.sink.events[-1].status == 'error'


def test_router_accepts_chat_service_protocol_without_config_attribute(rig):
    r = rig()
    service = SimpleNamespace(chat=r.service.chat, memory=r.service.memory, aggregate=r.service.aggregate)
    with make_client(service) as client:
        response = client.post('/api/chat', json={'user_id': '7', 'message': 'I need an elevator.'})
    assert response.status_code == 200
    assert r.sink.events[-1].context.source_commit == 'server-sha'
