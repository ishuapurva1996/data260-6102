"""Consistent, public-to-authenticated-users SQL facts for HW9 Q&A."""

import re

from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, inspect, select, update

from .models import Rental

VERSIONS = Table(
    "rental_data_version",
    MetaData(),
    Column("id", Integer, primary_key=True),
    Column("dataset_id", String(32), nullable=False),
    Column("version", BigInteger, nullable=False),
)
CODE = re.compile(r"(?<![\w-])S6102-R-[1-9][0-9]*(?![\w-])", re.IGNORECASE | re.ASCII)


def advance_rental_version(db):
    # Older SQL-only deployments can still use the pre-HW9 schema. Once 007 is
    # present, writes advance the version even while Q&A ingress is offline.
    if inspect(db.connection()).has_table(VERSIONS.name):
        db.flush()  # Acquire rental row locks before taking the version write lock.
        result = db.execute(
            update(VERSIONS).where(VERSIONS.c.id == 1).values(version=VERSIONS.c.version + 1)
        )
        if result.rowcount != 1:
            raise RuntimeError("Rental data version row is missing. Apply migration 007.")


def rental_version(db, *, lock=False):
    statement = select(VERSIONS.c.dataset_id, VERSIONS.c.version).where(VERSIONS.c.id == 1)
    if lock:
        statement = statement.with_for_update(read=True)
    dataset_id, version = db.execute(statement).one()
    return dataset_id, version


def rental_fact_snapshot(session_factory, question):
    codes = list(dict.fromkeys(match.group().upper() for match in CODE.finditer(question)))
    # The marker and facts come from one MySQL statement/snapshot, including
    # questions with no code or codes that no longer exist.
    statement = (
        select(
            VERSIONS.c.dataset_id,
            VERSIONS.c.version,
            Rental.listing_code,
            Rental.listing_title,
            Rental.property_type,
            Rental.available_units,
        )
        .select_from(VERSIONS.outerjoin(Rental.__table__, Rental.listing_code.in_(codes)))
        .where(VERSIONS.c.id == 1)
        .order_by(Rental.listing_code)
    )
    with session_factory() as db:
        rows = db.execute(statement).mappings().all()
    if not rows:
        raise RuntimeError("Rental data version row is missing. Apply migration 007.")
    facts = [
        {
            "listing_code": row["listing_code"],
            "listing_title": row["listing_title"],
            "property_type": row["property_type"],
            "available_units": row["available_units"],
        }
        for row in rows
        if row["listing_code"] is not None
    ]
    return {
        "dataset_id": rows[0]["dataset_id"],
        "data_version": rows[0]["version"],
        "requested_codes": codes,
        "listings": facts,
    }
