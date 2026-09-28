"""Shared SQLAlchemy 2 models for ordinary CRUD, login, and Part 3 queries.

MySQL DATETIME does not preserve timezone offsets. All application timestamps
are UTC with ``tzinfo`` removed before storage; naive stored values mean UTC.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import DATETIME, VARCHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return UTC in the naive representation used by MySQL DATETIME(6)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


class SessionToken(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(VARCHAR(128, charset="ascii", collation="ascii_bin"), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, default=utc_now)
    user: Mapped[User] = relationship()


class PropertyManager(Base):
    __tablename__ = "property_managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Rental(Base):
    __tablename__ = "rentals"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(TRIM(listing_title)) > 0", name="ck_rentals_title"),
        CheckConstraint("CHAR_LENGTH(TRIM(property_address)) > 0", name="ck_rentals_address"),
        CheckConstraint("CHAR_LENGTH(description) >= 26", name="ck_rentals_description"),
        CheckConstraint(
            "property_type IN ('apartment', 'house', 'condo', 'townhouse')",
            name="ck_rentals_property_type",
        ),
        CheckConstraint("terms_accepted = 1", name="ck_rentals_terms"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_title: Mapped[str] = mapped_column(String(255), nullable=False)
    property_address: Mapped[str] = mapped_column(String(255), nullable=False)
    submitter_email: Mapped[str] = mapped_column(String(320), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    property_type: Mapped[str] = mapped_column(String(20), nullable=False)
    terms_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("property_managers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    manager: Mapped[PropertyManager | None] = relationship()
