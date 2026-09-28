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
