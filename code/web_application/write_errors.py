"""Translate constraint races without leaking database statements or parameters."""
from fastapi import HTTPException


def raise_write_conflict(db, error, detail):
    db.rollback()
    # A referenced manager can disappear after request validation. MySQL remains
    # the final authority, and this race has the same response as an absent FK.
    if error.orig.args[0] == 1452:
        raise HTTPException(422, "The supplied property manager does not exist.") from None
    raise HTTPException(409, detail) from None
