"""Authenticated rental CRUD, stable pagination, and literal Unicode search."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PropertyManager, Rental, utc_now
from ..schemas import RentalCreate, RentalResponse, RentalUpdate, rental_json
from ..write_errors import raise_write_conflict
from .auth import can_delete, can_write, require_user

router = APIRouter(prefix="/api/rentals", tags=["rentals"], dependencies=[Depends(require_user)])
RecordId = Annotated[int, Path(gt=0)]


def find_rental(db, rental_id):
    row = db.get(Rental, rental_id)
    if row is None:
        raise HTTPException(404, f"Rental listing ID {rental_id} was not found.")
    return row


def validate_manager(db, manager_id):
    if manager_id is not None and db.get(PropertyManager, manager_id) is None:
        raise HTTPException(422, "The supplied property manager does not exist.")


@router.get("", response_model=list[RentalResponse])
def list_rentals(
    response: Response,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    statement = select(Rental).order_by(Rental.id)
    query = (q or "").strip().casefold()
    if query:
        # Python casefold intentionally preserves Straße/strasse expansion and
        # treats SQL wildcards as ordinary text. Filter before count/pagination.
        matches = [
            row
            for row in db.scalars(statement)
            if query in row.listing_title.casefold() or query in row.property_address.casefold()
        ]
        total, rows = len(matches), matches[offset : offset + limit]
    else:
        total = db.scalar(select(func.count()).select_from(Rental))
        rows = db.scalars(statement.limit(limit).offset(offset)).all()
    response.headers["X-Total-Count"] = str(total)
    return [rental_json(row) for row in rows]


@router.post("", response_model=RentalResponse, status_code=201, dependencies=[Depends(can_write)])
def create_rental(payload: RentalCreate, db: Session = Depends(get_db)):
    validate_manager(db, payload.managerId)
    now = utc_now()
    row = Rental(
        listing_title=payload.listingTitle,
        property_address=payload.propertyAddress,
        submitter_email=str(payload.submitterEmail),
        description=payload.description,
        property_type=payload.propertyType,
        terms_accepted=payload.termsAccepted,
        manager_id=payload.managerId,
        available_units=payload.availableUnits,
        listing_code=payload.listingCode or f"pending-{uuid4().hex}",
        created_at=now,
        updated_at=now,
    )
    try:
        db.add(row)
        db.flush()
        if payload.listingCode is None:
            # Reserve the auto-increment ID, then complete its code in the same
            # transaction. Concurrent requests never depend on SELECT MAX(id).
            row.listing_code = f"S6102-R-{row.id}"
            row.updated_at = now
        db.commit()
    except IntegrityError as error:
        raise_write_conflict(db, error, "A rental with this listing code already exists.")
    return rental_json(row)


@router.delete("/highest", status_code=204, dependencies=[Depends(can_delete)])
def delete_highest(db: Session = Depends(get_db)):
    row = db.scalar(select(Rental).order_by(Rental.id.desc()).limit(1).with_for_update())
    if row is None:
        raise HTTPException(404, "There are no rental listings to delete.")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/{rental_id}", response_model=RentalResponse)
def get_rental(rental_id: RecordId, db: Session = Depends(get_db)):
    return rental_json(find_rental(db, rental_id))


@router.put("/{rental_id}", response_model=RentalResponse, dependencies=[Depends(can_write)])
def update_rental(rental_id: RecordId, payload: RentalUpdate, db: Session = Depends(get_db)):
    row = find_rental(db, rental_id)
    if "managerId" in payload.model_fields_set:
        validate_manager(db, payload.managerId)
    columns = {
        "listingTitle": "listing_title",
        "propertyAddress": "property_address",
        "submitterEmail": "submitter_email",
        "description": "description",
        "propertyType": "property_type",
        "termsAccepted": "terms_accepted",
        "listingCode": "listing_code",
        "availableUnits": "available_units",
        "managerId": "manager_id",
    }
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, columns[key], value)
    row.updated_at = utc_now()
    try:
        db.commit()
    except IntegrityError as error:
        raise_write_conflict(db, error, "A rental with this listing code already exists.")
    return rental_json(row)


@router.delete("/{rental_id}", status_code=204, dependencies=[Depends(can_delete)])
def delete_rental(rental_id: RecordId, db: Session = Depends(get_db)):
    db.delete(find_rental(db, rental_id))
    db.commit()
    return Response(status_code=204)
