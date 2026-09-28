"""Experiment-only SQL counts measured at execution, including auth and serialization.

The mutable counter is created in the ASGI context before dependencies run. AnyIO
copies that context into sync worker threads, so every execution in this request
updates the same object; concurrent requests receive different objects. We count
SQLAlchemy cursor executions, not DBAPI protocol operations (BEGIN/COMMIT/ROLLBACK
or pool ping). No statement text, parameters, passwords or tokens are retained.
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock

from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class _Counts:
    total: int = 0
    data: int = 0
    lock: Lock = field(default_factory=Lock)


_counts: ContextVar[_Counts | None] = ContextVar('hw4_sql_counts', default=None)
_PATHS = {'/api/rentals/naive', '/api/rentals/fixed'}


def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    counts = _counts.get()
    if counts is not None:
        with counts.lock:
            counts.total += 1
            if context.execution_options.get('hw4_data_query', False):
                counts.data += 1


def install_query_counter():
    """Install once for the app's shared SQLAlchemy engines, including test binds."""
    if not event.contains(Engine, 'before_cursor_execute', before_cursor_execute):
        event.listen(Engine, 'before_cursor_execute', before_cursor_execute)


class QueryMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') not in _PATHS:
            return await self.app(scope, receive, send)
        counts = _Counts()
        token = _counts.set(counts)

        async def send_counted(message):
            if message['type'] == 'http.response.start':
                # These JSON endpoints have finished materializing and serializing
                # before response.start. Streaming endpoints are outside the scope.
                headers = list(message.get('headers', []))
                headers.extend([
                    (b'x-sql-statements', str(counts.total).encode('ascii')),
                    (b'x-data-sql-statements', str(counts.data).encode('ascii')),
                ])
                message = {**message, 'headers': headers}
            await send(message)

        try:
            await self.app(scope, receive, send_counted)
        finally:
            _counts.reset(token)
