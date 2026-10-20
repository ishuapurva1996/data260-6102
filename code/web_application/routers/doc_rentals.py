"""Mountable authenticated MongoDB routes; A owns shared app/CORS configuration."""
from fastapi import APIRouter, Depends, Response

from src.hw06_documents.schemas import RentalCreate, RentalResponse, RentalUpdate
from src.hw06_documents.service import DocumentService

from .auth import require_user


def create_router(service: DocumentService, *, current_user_dependency=require_user) -> APIRouter:
    router = APIRouter(prefix="/api/doc-rentals", tags=["document rentals"],
                       dependencies=[Depends(current_user_dependency)])

    @router.post("", response_model=RentalResponse, status_code=201)
    def create_rental(payload: RentalCreate):
        return service.create(payload)

    @router.get("", response_model=list[RentalResponse])
    def list_rentals():
        return service.list()

    @router.get("/{rental_id}", response_model=RentalResponse)
    def get_rental(rental_id: str):
        return service.get(rental_id)

    @router.put("/{rental_id}", response_model=RentalResponse)
    def update_rental(rental_id: str, payload: RentalUpdate):
        return service.update(rental_id, payload)

    @router.delete("/{rental_id}", status_code=204)
    def delete_rental(rental_id: str):
        service.delete(rental_id)
        return Response(status_code=204)

    return router
