"""Equivalent authenticated rental lists that expose the cost of N+1 queries."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PropertyManager, Rental
from ..schemas import RentalResponse, rental_json
from .auth import require_user

router = APIRouter(prefix='/api/rentals', tags=['Part 3 performance'],
                   dependencies=[Depends(require_user)])


class ManagerResponse(BaseModel):
    id: int = Field(gt=0)
    name: str


class PerformanceRentalResponse(RentalResponse):
    manager: ManagerResponse | None


def _serialize(rental, manager):
    return {**rental_json(rental), 'manager': (
        {'id': manager.id, 'name': manager.name} if manager is not None else None
    )}


@router.get('/naive', response_model=list[PerformanceRentalResponse])
def naive(page_size: int = Query(10, ge=1, le=200), offset: int = Query(0, ge=0),
          db: Session = Depends(get_db)):
    rentals = db.scalars(select(Rental).order_by(Rental.id).limit(page_size).offset(offset)
                         .execution_options(hw4_data_query=True)).all()
    rows = []
    for rental in rentals:
        # An explicit SELECT always executes, even when the same manager is
        # already in the ORM identity map. Session.get/lazy access would hide N+1.
        manager = db.scalar(select(PropertyManager).where(PropertyManager.id == rental.manager_id)
                            .execution_options(hw4_data_query=True))
        rows.append(_serialize(rental, manager))
    return rows


@router.get('/fixed', response_model=list[PerformanceRentalResponse])
def fixed(page_size: int = Query(10, ge=1, le=200), offset: int = Query(0, ge=0),
          db: Session = Depends(get_db)):
    rows = db.execute(select(Rental, PropertyManager)
                      .outerjoin(PropertyManager, Rental.manager_id == PropertyManager.id)
                      .order_by(Rental.id).limit(page_size).offset(offset)
                      .execution_options(hw4_data_query=True)).all()
    return [_serialize(rental, manager) for rental, manager in rows]
