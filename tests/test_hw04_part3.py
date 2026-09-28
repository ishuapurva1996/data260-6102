"""Request-local instrumentation and opt-in real MySQL performance checks."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code'))

from web_application.query_metrics import QueryMetricsMiddleware, before_cursor_execute


def emit_statement(*, data=False):
    # Unit-level execution callback; real SQL checks below use the MySQL engine.
    before_cursor_execute(None, None, 'SELECT', None,
                          SimpleNamespace(execution_options={'hw4_data_query': data}), False)


def test_request_context_survives_threads_and_serialization_and_does_not_leak():
    async def scenario():
        ready = asyncio.Event()
        arrived = 0

        async def downstream(scope, receive, send):
            nonlocal arrived
            emit_statement()  # auth equivalent
            await asyncio.to_thread(emit_statement, data=True)
            arrived += 1
            if arrived == 2:
                ready.set()
            await ready.wait()
            for _ in range(scope['extra']):
                emit_statement(data=True)  # response preparation/serialization
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'[]'})

        middleware = QueryMetricsMiddleware(downstream)
        async def request(extra):
            sent = []
            async def send(message):
                sent.append(message)
            await middleware({'type': 'http', 'path': '/api/rentals/naive', 'extra': extra}, None, send)
            return dict(sent[0]['headers'])
        first, second = await asyncio.gather(request(10), request(50))
        assert first[b'x-sql-statements'] == b'12'
        assert first[b'x-data-sql-statements'] == b'11'
        assert second[b'x-sql-statements'] == b'52'
        assert second[b'x-data-sql-statements'] == b'51'
        emit_statement()  # outside a request must not mutate a previous result
        assert first[b'x-sql-statements'] == b'12'
    asyncio.run(scenario())


def test_non_experiment_routes_do_not_expose_sql_counters():
    async def scenario():
        sent = []
        async def downstream(scope, receive, send):
            emit_statement()
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        async def send(message):
            sent.append(message)
        await QueryMetricsMiddleware(downstream)({'type': 'http', 'path': '/api/health'}, None, send)
        assert sent[0]['headers'] == []
    asyncio.run(scenario())

# These integration checks use only the already seeded, independently owned MySQL.
# The foundation, auth dependency, session factory, engine and serializer are real.
import os
from concurrent.futures import ThreadPoolExecutor
import pytest

LIVE = pytest.mark.skipif(os.environ.get('HW4_PART3_MYSQL_TESTS') != '1',
                          reason='Set HW4_PART3_MYSQL_TESTS=1 for owned real MySQL checks')


@pytest.fixture
def mysql_app():
    if os.environ.get('HW4_PART3_MYSQL_TESTS') != '1':
        pytest.skip('Dedicated MySQL opt-in required')
    from web_application.database import db_session_basede26
    from web_application.main import create_app
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/hw04/part3'))
    from ownership import verify_engine_ownership
    verify_engine_ownership(db_session_basede26, os.environ['HW4_PART3_OWNERSHIP'])
    return create_app()


def authenticated_client(app):
    from fastapi.testclient import TestClient
    client = TestClient(app, base_url='https://localhost:8733')
    response = client.post('/api/auth/login', json={
        'email': os.environ['HW4_SEED_EMAIL'], 'password': os.environ['HW4_SEED_PASSWORD']})
    assert response.status_code == 200
    return client


@LIVE
@pytest.mark.parametrize('size', [10, 50, 200])
def test_mysql_payload_and_actual_sql_include_auth(mysql_app, size):
    from sqlalchemy import event
    from web_application.database import db_session_basede26
    observed = []
    def record(conn, cursor, statement, parameters, context, executemany):
        observed.append({'sql': statement, 'data': bool(context.execution_options.get('hw4_data_query'))})
    with authenticated_client(mysql_app) as client:
        event.listen(db_session_basede26, 'before_cursor_execute', record)
        try:
            payloads = []
            for version in ('naive', 'fixed'):
                observed.clear()
                response = client.get(f'/api/rentals/{version}?page_size={size}&offset=0')
                assert response.status_code == 200
                data = response.json()
                assert len(data) == size
                assert [row['id'] for row in data] == list(range(1, size + 1))
                assert all(row['manager']['id'] > 0 for row in data)
                assert int(response.headers['X-SQL-Statements']) == len(observed)
                assert int(response.headers['X-Data-SQL-Statements']) == sum(row['data'] for row in observed)
                auth = [row['sql'] for row in observed if not row['data']]
                assert len(auth) == 2  # independently observed foundation SELECT + activity UPDATE
                assert 'sessions' in auth[0] and 'users' in auth[0]
                assert auth[1].lstrip().upper().startswith('UPDATE SESSIONS')
                assert sum(row['data'] for row in observed) == (size + 1 if version == 'naive' else 1)
                payloads.append(data)
            assert payloads[0] == payloads[1]
            if size == 200:
                assert len({row['manager']['id'] for row in payloads[0]}) < size
        finally:
            event.remove(db_session_basede26, 'before_cursor_execute', record)


@LIVE
def test_mysql_auth_validation_and_empty_pages(mysql_app):
    from fastapi.testclient import TestClient
    with TestClient(mysql_app, base_url='https://localhost:8733') as client:
        for version in ('naive', 'fixed'):
            assert client.get(f'/api/rentals/{version}').status_code == 401
    with authenticated_client(mysql_app) as client:
        for version in ('naive', 'fixed'):
            for query in ('page_size=0', 'page_size=201', 'page_size=oops', 'offset=-1'):
                assert client.get(f'/api/rentals/{version}?{query}').status_code == 422
            response = client.get(f'/api/rentals/{version}?page_size=10&offset=5000')
            assert response.status_code == 200 and response.json() == []
            assert int(response.headers['X-Data-SQL-Statements']) == 1
            page = client.get(f'/api/rentals/{version}?page_size=10&offset=20').json()
            assert [row['id'] for row in page] == list(range(21, 31))


@LIVE
def test_mysql_repeated_managers_and_null_are_equivalent_without_identity_map_reuse(mysql_app):
    from sqlalchemy import update
    from sqlalchemy.orm import sessionmaker
    from web_application.database import db_session_basede26
    from web_application.main import create_app
    from web_application.models import Rental
    # Bound savepoints retain foundation auth commits while the outer transaction
    # rolls back every fixture change. No dataset rows are permanently modified.
    with db_session_basede26.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(update(Rental).where(Rental.id <= 10).values(manager_id=1))
            connection.execute(update(Rental).where(Rental.id == 1).values(manager_id=None))
            factory = sessionmaker(bind=connection, expire_on_commit=False, join_transaction_mode='create_savepoint')
            app = create_app(session_factory=factory)
            with authenticated_client(app) as client:
                naive = client.get('/api/rentals/naive?page_size=10')
                fixed = client.get('/api/rentals/fixed?page_size=10')
                assert naive.status_code == fixed.status_code == 200
                assert naive.json() == fixed.json()
                assert naive.json()[0]['manager'] is None
                assert {row['manager']['id'] for row in naive.json()[1:]} == {1}
                assert int(naive.headers['X-Data-SQL-Statements']) == 11
                assert int(fixed.headers['X-Data-SQL-Statements']) == 1
        finally:
            transaction.rollback()


@LIVE
def test_mysql_concurrent_requests_have_independent_counters(mysql_app):
    clients = [authenticated_client(mysql_app) for _ in range(6)]
    work = [(size, version) for size in (10, 50, 200) for version in ('naive', 'fixed')]
    try:
        def request(entry):
            client, (size, version) = entry
            response = client.get(f'/api/rentals/{version}?page_size={size}')
            assert response.status_code == 200 and len(response.json()) == size
            assert int(response.headers['X-Data-SQL-Statements']) == (size + 1 if version == 'naive' else 1)
            assert int(response.headers['X-SQL-Statements']) == int(response.headers['X-Data-SQL-Statements']) + 2
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(request, zip(clients, work)))
    finally:
        for client in clients:
            client.close()
