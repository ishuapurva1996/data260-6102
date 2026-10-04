"""Injectable storage interface and lazy SQLAlchemy Core MySQL SELECT adapter.

Search uses MySQL LOWER on both operands, followed by utf8mb4_bin comparison.
It is accent-sensitive and does not expand sharp-s to ``ss`` or normalize
composed/decomposed Unicode. MySQL's LOWER mappings define Unicode case behavior;
Python casefold is not used and is not an equivalent search specification.
"""

import os
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, bindparam, create_engine, func, or_, select
from sqlalchemy.engine import Engine, make_url


class RentalReader(Protocol):
    def search_rentals(self, query: str, limit: int) -> Sequence[Mapping[str, Any]]: ...
    def get_rental(self, rental_id: int) -> Mapping[str, Any] | None: ...
    def count_rentals(self, manager_id: int) -> Mapping[str, Any] | None: ...


class RentalReaderConfigurationError(ValueError):
    """Configuration messages deliberately contain no connection URL."""


# Describe only the stable HW4 public columns; never reflect or create schema.
metadata = MetaData()
rentals = Table(
    "rentals", metadata,
    Column("id", Integer), Column("listing_title", String(255)),
    Column("property_address", String(255)), Column("description", Text),
    Column("property_type", String(20)), Column("manager_id", Integer),
)
property_managers = Table(
    "property_managers", metadata, Column("id", Integer), Column("name", String(255)),
)


class MySQLRentalReader:
    """No connection or environment access until the first requested read."""

    def __init__(self, database_url: str | None = None):
        self._database_url = database_url
        self._engine: Engine | None = None

    def _get_engine(self) -> Engine:
        if self._engine is None:
            raw = self._database_url if self._database_url is not None else os.environ.get("HW5_MCP_DATABASE_URL")
            message = "HW5_MCP_DATABASE_URL must explicitly select mysql+pymysql and database s6102_rel."
            try:
                url = make_url(raw) if raw else None
            except Exception:
                raise RentalReaderConfigurationError(message) from None
            if url is None or url.drivername != "mysql+pymysql" or url.database != "s6102_rel":
                raise RentalReaderConfigurationError(message)
            self._engine = create_engine(
                url, hide_parameters=True,
                connect_args={"charset": "utf8mb4", "connect_timeout": 5, "read_timeout": 10, "write_timeout": 10},
            )
        return self._engine

    def search_rentals(self, query: str, limit: int) -> Sequence[Mapping[str, Any]]:
        # '!' is the explicit escape character; backslashes and quotes remain bound data.
        escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        pattern = func.lower(bindparam("pattern", value=f"%{escaped}%")).collate("utf8mb4_bin")
        statement = select(
            rentals.c.id, rentals.c.listing_title, rentals.c.property_address,
            rentals.c.property_type, rentals.c.manager_id,
        ).where(or_(
            func.lower(rentals.c.listing_title).collate("utf8mb4_bin").like(pattern, escape="!"),
            func.lower(rentals.c.property_address).collate("utf8mb4_bin").like(pattern, escape="!"),
        )).order_by(rentals.c.id.asc()).limit(limit)
        with self._get_engine().connect() as connection:
            return connection.execute(statement).mappings().all()

    def get_rental(self, rental_id: int) -> Mapping[str, Any] | None:
        statement = select(
            rentals.c.id, rentals.c.listing_title, rentals.c.property_address,
            rentals.c.description, rentals.c.property_type, rentals.c.manager_id,
        ).where(rentals.c.id == rental_id)
        with self._get_engine().connect() as connection:
            return connection.execute(statement).mappings().first()

    def count_rentals(self, manager_id: int) -> Mapping[str, Any] | None:
        # COUNT(child.id) yields zero for an existing manager's empty LEFT JOIN.
        statement = select(
            property_managers.c.id.label("manager_id"),
            property_managers.c.name.label("manager_name"),
            func.count(rentals.c.id).label("count"),
        ).select_from(property_managers.outerjoin(
            rentals, rentals.c.manager_id == property_managers.c.id,
        )).where(property_managers.c.id == manager_id).group_by(
            property_managers.c.id, property_managers.c.name,
        )
        with self._get_engine().connect() as connection:
            return connection.execute(statement).mappings().first()

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
