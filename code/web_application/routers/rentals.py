"""Ordinary authenticated CRUD; database-generated IDs survive restarts."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Rental
from ..schemas import RentalCreate, RentalUpdate, RentalResponse, rental_json
from .auth import require_user

router = APIRouter(prefix="/api/rentals", tags=["rentals"], dependencies=[Depends(require_user)])
RecordId = Annotated[int, Path(gt=0)]


def find_rental(db, rental_id):
    row = db.get(Rental, rental_id)
    if row is None:
        raise HTTPException(404, f"Rental listing ID {rental_id} was not found.")
    return row


@router.get("", response_model=list[RentalResponse])
def list_rentals(q: str | None = None, db: Session = Depends(get_db)):
    statement = select(Rental).order_by(Rental.id)
    query = (q or "").strip()
    if query:
        statement = statement.where(or_(Rental.listing_title.contains(query, autoescape=True),
                                       Rental.property_address.contains(query, autoescape=True)))
    return [rental_json(row) for row in db.scalars(statement)]


@router.post("", response_model=RentalResponse, status_code=201)
def create_rental(payload: RentalCreate, db: Session = Depends(get_db)):
    row = Rental(listing_title=payload.listingTitle, property_address=payload.propertyAddress,
                 submitter_email=str(payload.submitterEmail), description=payload.description,
                 property_type=payload.propertyType, terms_accepted=payload.termsAccepted)
    db.add(row)
    db.commit()
    return rental_json(row)


@router.delete("/highest", status_code=204)
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


@router.put("/{rental_id}", response_model=RentalResponse)
def update_rental(rental_id: RecordId, payload: RentalUpdate, db: Session = Depends(get_db)):
    row = find_rental(db, rental_id)
    row.listing_title, row.property_address = payload.listingTitle, payload.propertyAddress
    db.commit()
    return rental_json(row)


@router.delete("/{rental_id}", status_code=204)
def delete_rental(rental_id: RecordId, db: Session = Depends(get_db)):
    db.delete(find_rental(db, rental_id))
    db.commit()
    return Response(status_code=204)
