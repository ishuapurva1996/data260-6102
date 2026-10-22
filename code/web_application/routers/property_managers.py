"""Property-manager records are independent of authentication users."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PropertyManager, Rental, utc_now
from ..schemas import ManagerCreate, ManagerResponse, RentalResponse, manager_json, rental_json
from ..write_errors import raise_write_conflict
from .auth import can_delete, can_write, require_user

router = APIRouter(
    prefix="/api/property-managers",
    tags=["property managers"],
    dependencies=[Depends(require_user)],
)
ManagerId = Annotated[int, Path(gt=0)]


def find_manager(db, manager_id):
    row = db.get(PropertyManager, manager_id)
    if row is None:
        raise HTTPException(404, f"Property manager ID {manager_id} was not found.")
    return row


@router.get("", response_model=list[ManagerResponse])
def list_managers(
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    response.headers["X-Total-Count"] = str(
        db.scalar(select(func.count()).select_from(PropertyManager))
    )
    rows = db.scalars(
        select(PropertyManager).order_by(PropertyManager.id).limit(limit).offset(offset)
    )
    return [manager_json(row) for row in rows]


@router.post("", response_model=ManagerResponse, status_code=201, dependencies=[Depends(can_write)])
def create_manager(payload: ManagerCreate, db: Session = Depends(get_db)):
    now = utc_now()
    row = PropertyManager(**payload.model_dump(), created_at=now, updated_at=now)
    try:
        db.add(row)
        db.commit()
    except IntegrityError as error:
        raise_write_conflict(db, error, "A property manager with this email already exists.")
    return manager_json(row)


@router.get("/{manager_id}/rentals", response_model=list[RentalResponse])
def manager_rentals(
    manager_id: ManagerId,
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    find_manager(db, manager_id)
    response.headers["X-Total-Count"] = str(
        db.scalar(select(func.count()).select_from(Rental).where(Rental.manager_id == manager_id))
    )
    rows = db.scalars(
        select(Rental)
        .where(Rental.manager_id == manager_id)
        .order_by(Rental.id)
        .limit(limit)
        .offset(offset)
    )
    return [rental_json(row) for row in rows]


@router.get("/{manager_id}", response_model=ManagerResponse)
def get_manager(manager_id: ManagerId, db: Session = Depends(get_db)):
    return manager_json(find_manager(db, manager_id))


@router.put("/{manager_id}", response_model=ManagerResponse, dependencies=[Depends(can_write)])
def update_manager(manager_id: ManagerId, payload: ManagerCreate, db: Session = Depends(get_db)):
    row = find_manager(db, manager_id)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_at = utc_now()
    try:
        db.commit()
    except IntegrityError as error:
        raise_write_conflict(db, error, "A property manager with this email already exists.")
    return manager_json(row)


@router.delete("/{manager_id}", status_code=204, dependencies=[Depends(can_delete)])
def delete_manager(manager_id: ManagerId, db: Session = Depends(get_db)):
    row = find_manager(db, manager_id)
    try:
        db.delete(row)
        db.commit()
    except IntegrityError as error:
        raise_write_conflict(
            db, error, "This property manager still has rental listings and cannot be deleted."
        )
    return Response(status_code=204)
