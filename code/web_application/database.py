"""Configured MySQL engine and request-scoped database sessions.

Engine construction is lazy: importing this module does not connect, create
tables, or seed data. Run ``scripts/hw04/db_setup.py`` explicitly for setup.
"""

from collections.abc import Iterator
import os

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker


DATABASE_NAME = "s6102_rel"
DEFAULT_DATABASE_URL = "mysql+pymysql://root@127.0.0.1:3306/s6102_rel"


def get_database_url() -> URL:
    """Validate the assignment's driver/database without displaying credentials."""
    raw_url = os.environ.get("HW4_DATABASE_URL", DEFAULT_DATABASE_URL)
    try:
        url = make_url(raw_url)
    except (ArgumentError, TypeError, ValueError):
        raise ValueError("HW4_DATABASE_URL must be a valid MySQL connection URL.") from None
    if url.drivername != "mysql+pymysql" or url.database != DATABASE_NAME:
        raise ValueError(
            "HW4_DATABASE_URL must use mysql+pymysql and database s6102_rel."
        )
    return url


# The assignment requires this exact name. This is a SQLAlchemy Engine, not an
# authentication token or a request's SQLAlchemy Session.
db_session_basede26 = create_engine(
    get_database_url(),
    pool_pre_ping=True,
    pool_recycle=1800,
    hide_parameters=True,
    connect_args={"charset": "utf8mb4", "init_command": "SET time_zone = '+00:00'"},
)
SessionLocal = sessionmaker(bind=db_session_basede26, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    """Yield one unit of database work, rolling back failed requests and closing.

The application installs ``SessionLocal`` on ``app.state.session_factory``.
Tests can supply another factory bound to a dedicated MySQL instance. Mutation
handlers commit explicitly; this dependency never commits on their behalf.
"""
    session = request.app.state.session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
