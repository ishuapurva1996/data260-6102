"""Shared SQLAlchemy 2 models for ordinary CRUD, login, and Part 3 queries.

MySQL DATETIME does not preserve timezone offsets. All application timestamps
are UTC with ``tzinfo`` removed before storage; naive stored values mean UTC.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint, text
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
    __table_args__ = (UniqueConstraint("email", name="uq_property_managers_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    company: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=utc_now, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=utc_now,
        server_default=text("CURRENT_TIMESTAMP(6)"))
    # Even loaded children must reach MySQL's RESTRICT constraint on deletion.
    rentals: Mapped[list["Rental"]] = relationship(back_populates="manager", passive_deletes="all")


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
        CheckConstraint("available_units >= 0", name="ck_rentals_available_units"),
        UniqueConstraint("listing_code", name="uq_rentals_listing_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_title: Mapped[str] = mapped_column(String(255), nullable=False)
    property_address: Mapped[str] = mapped_column(String(255), nullable=False)
    submitter_email: Mapped[str] = mapped_column(String(320), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    property_type: Mapped[str] = mapped_column(String(20), nullable=False)
    terms_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    listing_code: Mapped[str] = mapped_column(String(64), nullable=False)
    available_units: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=utc_now, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=utc_now,
        server_default=text("CURRENT_TIMESTAMP(6)"))
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("property_managers.id", name="fk_rentals_manager", ondelete="RESTRICT"),
        nullable=True, index=True
    )
    manager: Mapped[PropertyManager | None] = relationship(back_populates="rentals")
