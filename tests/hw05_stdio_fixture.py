"""Offline subprocess fixtures for real MCP STDIO tests; not a live data source."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Reader:
    row = {"id": 1, "listing_title": "Campus Apartment", "property_address": "1 Campus Way",
           "description": "A synthetic rental for offline transport testing.",
           "property_type": "apartment", "manager_id": 1,
           "submitter_email": "PRIVATE_SENTINEL@example.com"}

    def __init__(self, audit_path=None):
        self.audit_path = audit_path

    def record_access(self, operation):
        if self.audit_path is not None:
            with self.audit_path.open("a") as audit:
                audit.write(operation + "\n")

    def search_rentals(self, query, limit):
        self.record_access("search_rentals")
        return [self.row] if query.lower() in "campus apartment 1 campus way" else []

    def get_rental(self, rental_id):
        self.record_access("get_rental")
        return self.row if rental_id == 1 else None

    def count_rentals(self, manager_id):
        self.record_access("count_rentals")
        return {"manager_id": manager_id, "manager_name": "Offline Manager",
                "count": 1 if manager_id == 1 else 0} if manager_id in (1, 2) else None


def main():
    if sys.argv[1] == "meals":
        import httpx
        from src.mcp_servers.meals import create_server
        from src.mcp_servers.meals_client import MealsClient

        def respond(request):
            if request.url.params.get("s") == "absent":
                return httpx.Response(200, json={"meals": None})
            return httpx.Response(200, json={"meals": [{
                "idMeal": "52772", "strMeal": "Offline Recipe", "strArea": "Italian",
                "strCategory": "Vegetarian", "strMealThumb": "https://example.com/recipe.jpg",
                "strInstructions": "Cook and serve.", "strIngredient1": "Tomato",
                "strMeasure1": "1 cup", "strIngredient2": "  "}]})

        create_server(client=MealsClient(transport=httpx.MockTransport(respond))).run(transport="stdio")
    else:
        import anyio
        from src.mcp_servers.rentals import create_server, run_stdio
        audit_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        anyio.run(run_stdio, create_server(reader=Reader(audit_path)))


if __name__ == "__main__":
    main()
