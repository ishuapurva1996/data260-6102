"""The shared rental housing app, served locally on the SID-derived port 8702.

Records live in one process: refreshing the browser retains them, while restarting
the server restores the two seeds. Run one Uvicorn worker for this assignment.
"""

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_validator


PORT_BASE = 8702
STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


class RentalUpdate(BaseModel):
    """An update may change only the domain's primary and secondary fields."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    listingTitle: str = Field(min_length=1)
    propertyAddress: str = Field(min_length=1)


class RentalCreate(RentalUpdate):
    """The complete create form; the server alone assigns its ID."""

    submitterEmail: EmailStr
    description: str = Field(min_length=26)
    propertyType: Literal["apartment", "house", "condo", "townhouse"]
    termsAccepted: StrictBool = Field(description="Must be true to accept the terms.")

    @field_validator("termsAccepted")
    @classmethod
    def require_accepted_terms(cls, accepted: bool) -> bool:
        if not accepted:
            raise ValueError("Please agree to the terms and conditions.")
        return accepted


class Rental(RentalCreate):
    """A stored record and API response, including its server-owned ID."""

    id: int


def seed_rentals() -> list[Rental]:
    """Create fresh seed objects so different app instances do not share state."""
    return [
        Rental(
            id=1,
            listingTitle="Sunny Downtown Apartment",
            propertyAddress="123 San Carlos Street, San Jose, CA",
            submitterEmail="downtown@example.com",
            description="A bright apartment close to campus, shops, and public transit.",
            propertyType="apartment",
            termsAccepted=True,
        ),
        Rental(
            id=2,
            listingTitle="Spacious Garden House",
            propertyAddress="456 Willow Street, San Jose, CA",
            submitterEmail="garden@example.com",
            description="A comfortable house with a private garden and a sunny living room.",
            propertyType="house",
            termsAccepted=True,
        ),
    ]


def create_app(initial_rentals: list[Rental | dict] | None = None) -> FastAPI:
    """Build an independent app, optionally with a test's own initial records."""
    app = FastAPI(title="Rental Housing Listings", version="2.0.0")
    rentals = (
        seed_rentals()
        if initial_rentals is None
        else [Rental.model_validate(record).model_copy(deep=True) for record in initial_rentals]
    )

    def rental_index(rental_id: int) -> int:
        for index, rental in enumerate(rentals):
            if rental.id == rental_id:
                return index
        raise HTTPException(status_code=404, detail=f"Rental listing ID {rental_id} was not found.")

    def delete_record(rental_id: int) -> Response:
        del rentals[rental_index(rental_id)]
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/", response_class=FileResponse)
    async def home():
        return FileResponse(STATIC_DIRECTORY / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/rentals", response_model=list[Rental])
    async def list_rentals(response: Response, q: str | None = None):
        response.headers["Cache-Control"] = "no-store"
        query = (q or "").strip().casefold()
        return [
            rental for rental in rentals
            if not query
            or query in rental.listingTitle.casefold()
            or query in rental.propertyAddress.casefold()
        ]

    # These async handlers do not await between reading and changing the store,
    # so each mutation completes together on the single worker's event loop.
    @app.post("/api/rentals", response_model=Rental, status_code=status.HTTP_201_CREATED)
    async def create_rental(payload: RentalCreate):
        next_id = max((rental.id for rental in rentals), default=0) + 1
        rental = Rental(id=next_id, **payload.model_dump())
        rentals.append(rental)
        return rental

    @app.put("/api/rentals/{rental_id}", response_model=Rental)
    async def update_rental(rental_id: int, payload: RentalUpdate):
        index = rental_index(rental_id)
        rentals[index] = rentals[index].model_copy(update=payload.model_dump())
        return rentals[index]

    # Register this literal path before the integer-ID delete route.
    @app.delete("/api/rentals/highest", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_highest_rental():
        if not rentals:
            raise HTTPException(status_code=404, detail="There are no rental listings to delete.")
        return delete_record(max(rental.id for rental in rentals))

    @app.delete("/api/rentals/{rental_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_rental(rental_id: int):
        return delete_record(rental_id)

    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT_BASE, workers=1)
