"""Meals contract tests use controlled HTTP responses, never the public API."""
import asyncio
import json

import httpx
import pytest

from src.mcp_servers.meals import create_server
from src.mcp_servers.meals_client import MealsClient, MealsError


MEAL = {
    "idMeal": "52772", "strMeal": "Teriyaki Chicken Casserole",
    "strArea": "Japanese", "strCategory": "Chicken", "strMealThumb": "https://example.com/meal.jpg",
    "strInstructions": "Bake until cooked.", "strSource": "https://example.com/recipe",
    "strYoutube": "https://example.com/video", "strIngredient1": " Chicken ",
    "strMeasure1": " 2 cups ", "strIngredient2": "", "strMeasure2": "unused",
    "strIngredient3": None, "strIngredient4": " Rice ", "strMeasure4": None, "strIngredient5": "   ",
    "strIngredient20": "Salt", "strMeasure20": "to taste", "unrequestedField": "excluded",
}
DETAIL = {
    "id": "52772", "name": "Teriyaki Chicken Casserole", "category": "Chicken", "area": "Japanese",
    "instructions": "Bake until cooked.", "image": "https://example.com/meal.jpg",
    "source": "https://example.com/recipe", "youtube": "https://example.com/video",
    "ingredients": [{"name": "Chicken", "measure": " 2 cups "}, {"name": "Rice", "measure": ""},
                    {"name": "Salt", "measure": "to taste"}],
}


def client_for(payload):
    return MealsClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.mark.parametrize(("method", "arguments", "endpoint", "params", "expected"), [
    ("search_meals_by_name", ("  chicken  ", 1), "search.php", {"s": "chicken"}, [
        {"id": "52772", "name": "Teriyaki Chicken Casserole", "area": "Japanese", "category": "Chicken",
         "thumb": "https://example.com/meal.jpg"}]),
    ("meals_by_ingredient", ("  chicken_breast  ", 1), "filter.php", {"i": "chicken_breast"}, [
        {"id": "52772", "name": "Teriyaki Chicken Casserole", "thumb": "https://example.com/meal.jpg"}]),
    ("random_meal", (), "random.php", {}, DETAIL),
    ("meal_details", ("52772",), "lookup.php", {"i": "52772"}, DETAIL),
    ("meal_details", (52772,), "lookup.php", {"i": "52772"}, DETAIL),
])
def test_endpoints_and_exact_public_shapes(method, arguments, endpoint, params, expected):
    def respond(request):
        assert str(request.url).startswith("https://www.themealdb.com/api/json/v1/1/")
        assert request.url.path.endswith("/" + endpoint)
        assert dict(request.url.params) == params
        assert all(0 < value <= 10 for value in request.extensions["timeout"].values())
        return httpx.Response(200, json={"meals": [MEAL, MEAL]})

    client = MealsClient(transport=httpx.MockTransport(respond))
    assert run(getattr(client, method)(*arguments)) == expected


def test_search_and_ingredient_defaults_limit_results():
    client = client_for({"meals": [MEAL] * 30})
    assert len(run(client.search_meals_by_name("chicken"))) == 5
    assert len(run(client.search_meals_by_name("chicken", 25))) == 25
    assert len(run(client.meals_by_ingredient("chicken"))) == 12
    assert len(run(client.meals_by_ingredient("chicken", 30))) == 30


@pytest.mark.parametrize("upstream", [None, []])
def test_no_matches_preserve_empty_list_or_null(upstream):
    client = client_for({"meals": upstream})
    assert run(client.search_meals_by_name("missing")) == []
    assert run(client.meals_by_ingredient("missing")) == []
    assert run(client.meal_details("999999")) is None
    assert run(client.random_meal()) is None


@pytest.mark.parametrize(("method", "arguments"), [
    ("search_meals_by_name", ("",)), ("search_meals_by_name", (" \t\n",)),
    ("search_meals_by_name", (1,)), ("search_meals_by_name", ("chicken", 0)),
    ("search_meals_by_name", ("chicken", 26)), ("search_meals_by_name", ("chicken", True)),
    ("search_meals_by_name", ("chicken", 1.0)), ("search_meals_by_name", ("chicken", "1")),
    ("meals_by_ingredient", ("",)), ("meals_by_ingredient", (None,)),
    ("meals_by_ingredient", ("chicken", -1)), ("meals_by_ingredient", ("chicken", False)),
    ("meal_details", (0,)), ("meal_details", (-1,)), ("meal_details", (True,)),
    ("meal_details", (1.0,)), ("meal_details", ("",)), ("meal_details", ("0",)),
    ("meal_details", ("-1",)), ("meal_details", ("1.0",)), ("meal_details", ("12?x=1",)),
])
def test_invalid_inputs_do_not_call_upstream(method, arguments):
    def unexpected(request):
        pytest.fail("Invalid arguments must not call TheMealDB")

    client = MealsClient(transport=httpx.MockTransport(unexpected))
    with pytest.raises(ValueError):
        run(getattr(client, method)(*arguments))


@pytest.mark.parametrize("response", [
    httpx.Response(503, text="private upstream diagnostic"),
    httpx.Response(200, text="not JSON private upstream diagnostic"),
    httpx.Response(200, json=[]), httpx.Response(200, json={}),
    httpx.Response(200, json={"meals": "invalid"}),
    httpx.Response(200, json={"meals": [None]}),
    httpx.Response(200, json={"meals": [{"strMeal": "missing id"}]}),
])
def test_http_and_payload_errors_are_clean(response):
    client = MealsClient(transport=httpx.MockTransport(lambda request: response))
    with pytest.raises(MealsError) as caught:
        run(client.search_meals_by_name("chicken"))
    assert "TheMealDB" in str(caught.value)
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_network_errors_are_clean(error):
    def fail(request):
        raise error("private network diagnostic", request=request)

    with pytest.raises(MealsError) as caught:
        run(MealsClient(transport=httpx.MockTransport(fail)).random_meal())
    assert "private" not in str(caught.value)
    assert "TheMealDB" in str(caught.value)


def test_mcp_inventory_and_published_input_schemas():
    server = create_server(client=client_for({"meals": [MEAL]}))
    tools = {tool.name: tool for tool in run(server.list_tools())}
    assert server.name == "meals"
    assert set(tools) == {"search_meals_by_name", "meals_by_ingredient", "random_meal", "meal_details"}
    search = tools["search_meals_by_name"].inputSchema
    assert search["required"] == ["query"]
    assert search["properties"]["limit"]["minimum"] == 1
    assert search["properties"]["limit"]["maximum"] == 25
    assert search["properties"]["limit"]["default"] == 5
    assert tools["meals_by_ingredient"].inputSchema["properties"]["limit"]["default"] == 12
    assert tools["meal_details"].inputSchema["required"] == ["id"]
    assert {shape["type"] for shape in tools["meal_details"].inputSchema["properties"]["id"]["anyOf"]} == {"string", "integer"}
    assert tools["random_meal"].inputSchema["properties"] == {}


@pytest.mark.parametrize(("name", "arguments", "empty"), [
    ("search_meals_by_name", {"query": "missing"}, []),
    ("meals_by_ingredient", {"ingredient": "missing"}, []),
    ("meal_details", {"id": "999999"}, None), ("random_meal", {}, None),
])
def test_mcp_empty_result_includes_accompanying_text(name, arguments, empty):
    server = create_server(client=client_for({"meals": None}))
    result = run(server.call_tool(name, arguments))
    assert not result.isError
    assert json.loads(result.content[0].text) == empty
    assert result.content[1].text == "No matches."
    assert result.structuredContent is None


def test_mcp_success_keeps_the_detail_object_shape():
    server = create_server(client=client_for({"meals": [MEAL]}))
    result = run(server.call_tool("meal_details", {"id": 52772}))
    assert not result.isError
    assert len(result.content) == 1
    assert json.loads(result.content[0].text) == DETAIL
    assert result.structuredContent is None


def test_mcp_upstream_failure_is_a_clean_error():
    server = create_server(client=client_for({"meals": "private bad payload"}))
    result = run(server.call_tool("random_meal", {}))
    assert result.isError
    assert "TheMealDB" in result.content[0].text
    assert "private" not in result.content[0].text


@pytest.mark.parametrize(("name", "arguments"), [
    ("search_meals_by_name", {"query": "chicken", "limit": "1"}),
    ("search_meals_by_name", {"query": "chicken", "limit": True}),
    ("meals_by_ingredient", {"ingredient": "chicken", "limit": 1.0}),
    ("meal_details", {"id": False}), ("meal_details", {"id": 52772.0}),
])
def test_mcp_rejects_coercible_input_types_before_http(name, arguments):
    from mcp.server.fastmcp.exceptions import ToolError

    def unexpected(request):
        pytest.fail("Invalid arguments must not call TheMealDB")

    server = create_server(client=MealsClient(transport=httpx.MockTransport(unexpected)))
    with pytest.raises(ToolError, match="validation error"):
        run(server.call_tool(name, arguments))
