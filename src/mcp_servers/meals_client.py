"""Small asynchronous client for the four assigned TheMealDB V1 endpoints."""
import re

import httpx


BASE_URL = "https://www.themealdb.com/api/json/v1/1/"
HTTP_TIMEOUT_SECONDS = 10.0


class MealsError(Exception):
    """A clean upstream failure safe to display to an MCP client."""


def _text_input(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string.")
    return value.strip()


def _limit(value, maximum=None):
    if type(value) is not int or value < 1 or (maximum is not None and value > maximum):
        suffix = f" between 1 and {maximum}" if maximum else " greater than zero"
        raise ValueError(f"limit must be an integer{suffix}.")
    return value


def _meal_id(value):
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[0-9]*[1-9][0-9]*", value):
        return value
    raise ValueError("id must be a positive integer or a positive digit string.")


def _field(meal, key):
    value = meal.get(key)
    if value is not None and not isinstance(value, str):
        raise MealsError("TheMealDB returned an invalid response.")
    return value


def _card(meal):
    identity = {"id": _field(meal, "idMeal"), "name": _field(meal, "strMeal")}
    if not identity["id"] or not identity["name"]:
        raise MealsError("TheMealDB returned an invalid response.")
    return {**identity, "thumb": _field(meal, "strMealThumb")}


def _detail(meal):
    card = _card(meal)
    ingredients = []
    for index in range(1, 21):
        name = _field(meal, f"strIngredient{index}")
        if name and name.strip():
            ingredients.append({"name": name.strip(), "measure": _field(meal, f"strMeasure{index}") or ""})
    return {
        "id": card["id"], "name": card["name"],
        "category": _field(meal, "strCategory"), "area": _field(meal, "strArea"),
        "instructions": _field(meal, "strInstructions"), "image": card["thumb"],
        "source": _field(meal, "strSource"), "youtube": _field(meal, "strYoutube"),
        "ingredients": ingredients,
    }


class MealsClient:
    """Requests are lazy, finite, and injectable through HTTPX's public transport."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def _get_meals(self, endpoint, params=None):
        try:
            async with httpx.AsyncClient(
                base_url=BASE_URL, timeout=HTTP_TIMEOUT_SECONDS, transport=self._transport,
            ) as client:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
        except httpx.TimeoutException:
            raise MealsError("TheMealDB request timed out.") from None
        except httpx.HTTPStatusError:
            raise MealsError("TheMealDB returned an unsuccessful HTTP status.") from None
        except httpx.RequestError:
            raise MealsError("TheMealDB could not be reached.") from None
        try:
            payload = response.json()
        except ValueError:
            raise MealsError("TheMealDB returned invalid JSON.") from None
        if not isinstance(payload, dict) or "meals" not in payload:
            raise MealsError("TheMealDB returned an invalid response.")
        meals = payload["meals"]
        if meals is None:
            return []
        if not isinstance(meals, list) or any(not isinstance(meal, dict) for meal in meals):
            raise MealsError("TheMealDB returned an invalid response.")
        return meals

    async def search_meals_by_name(self, query, limit=5):
        query, limit = _text_input(query, "query"), _limit(limit, maximum=25)
        meals = await self._get_meals("search.php", {"s": query})
        return [
            {**_card(meal), "area": _field(meal, "strArea"), "category": _field(meal, "strCategory")}
            for meal in meals[:limit]
        ]

    async def meals_by_ingredient(self, ingredient, limit=12):
        ingredient, limit = _text_input(ingredient, "ingredient"), _limit(limit)
        meals = await self._get_meals("filter.php", {"i": ingredient})
        return [_card(meal) for meal in meals[:limit]]

    async def random_meal(self):
        meals = await self._get_meals("random.php")
        return _detail(meals[0]) if meals else None

    async def meal_details(self, id):
        meals = await self._get_meals("lookup.php", {"i": _meal_id(id)})
        return _detail(meals[0]) if meals else None
