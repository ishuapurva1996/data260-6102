"""The bike tools enforce their boundary independently of any model or HTTP layer."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from src.bikeshare.tools import TOOL_SCHEMAS, calculator, csv_sql, policy_retriever

NOW = datetime(2026, 10, 22, 3, 0, tzinfo=timezone.utc)
URL = "https://capitalbikeshare.com/pricing"


@pytest.fixture
def trips():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        "CREATE TABLE trips (ride_id TEXT, duration_minutes REAL, started_at TEXT);"
        "INSERT INTO trips VALUES ('a', 12.5, '2026-09-01T08:00:00'),"
        "('b', 30.0, '2026-09-08T08:00:00'), ('c', 7.5, '2026-09-08T10:00:00');"
        "CREATE TABLE private_accounts (secret TEXT);"
        "INSERT INTO private_accounts VALUES ('private');"
    )
    yield connection
    connection.close()


def assert_envelope(result, *, success):
    assert result["success"] is success
    assert result["ts"] == NOW.isoformat()
    assert isinstance(result["source"], str)
    json.dumps(result, allow_nan=False)
    if success:
        assert "data" in result and "error" not in result
    else:
        assert result["error"] and "data" not in result


def test_schemas_expose_only_the_three_assignment_inputs():
    schemas = {schema["name"]: schema["parameters"] for schema in TOOL_SCHEMAS}
    assert set(schemas) == {"csv_sql", "policy_retriever", "calculator"}
    assert set(schemas["csv_sql"]["properties"]) == {"sql"}
    assert schemas["csv_sql"]["required"] == ["sql"]
    assert set(schemas["policy_retriever"]["properties"]) == {"url", "query", "k"}
    assert schemas["policy_retriever"]["required"] == ["url", "query"]
    assert set(schemas["calculator"]["properties"]) == {"expression", "units"}
    assert schemas["calculator"]["required"] == ["expression"]
    assert schemas["calculator"]["properties"]["expression"]["pattern"] == (r"^[0-9+\-*/().\s]+$")
    assert all(schema["additionalProperties"] is False for schema in schemas.values())


def test_sql_summary_uses_uploaded_rows_and_preserves_them(trips):
    result = csv_sql(
        "SELECT COUNT(*) AS rides, ROUND(SUM(duration_minutes), 2) AS minutes, "
        "AVG(duration_minutes) AS average FROM trips",
        connection=trips,
        clock=lambda: NOW,
    )
    assert_envelope(result, success=True)
    assert result["data"] == {
        "rows": [{"rides": 3, "minutes": 50.0, "average": 50 / 3}],
        "row_count": 1,
        "source": "uploaded.csv",
    }
    assert trips.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 3


def test_sql_safe_grouping_and_case_work(trips):
    result = csv_sql(
        "SELECT strftime('%W', started_at) AS week, "
        "SUM(CASE WHEN duration_minutes > 10 THEN 1 ELSE 0 END) AS long_rides "
        "FROM trips GROUP BY week ORDER BY week;",
        connection=trips,
        clock=lambda: NOW,
    )
    assert_envelope(result, success=True)
    assert result["data"]["row_count"] == 2
    assert sum(row["long_rides"] for row in result["data"]["rows"]) == 2


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM trips",
        "UPDATE trips SET duration_minutes=0",
        "SELECT * FROM trips; DELETE FROM trips",
        "SELECT * FROM trips; SELECT * FROM trips",
        "PRAGMA table_info(trips)",
        "ATTACH DATABASE '/tmp/private.db' AS other",
        "SELECT * FROM private_accounts",
        "SELECT * FROM sqlite_master",
        "SELECT name FROM sqlite_schema",
        "SELECT readfile('/etc/passwd') FROM trips",
        "SELECT load_extension('unsafe') FROM trips",
        "SELECT writefile('/tmp/unsafe', 'x') FROM trips",
        "SELECT secret FROM trips JOIN private_accounts",
        "SELECT 1",
        "EXPLAIN SELECT * FROM trips",
        "CREATE TEMP TABLE stolen AS SELECT * FROM trips",
        "WITH removed AS (SELECT * FROM private_accounts) SELECT * FROM removed",
        "SELECT * FROM trips WHERE ride_id IN (SELECT secret FROM private_accounts)",
        "SELECT * FROM pragma_database_list",
    ],
)
def test_sql_rejects_writes_extra_statements_and_hidden_reads_without_row_loss(trips, sql):
    result = csv_sql(sql, connection=trips, clock=lambda: NOW)
    assert_envelope(result, success=False)
    assert trips.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 3
    assert "private" not in json.dumps(result)


def test_sql_unknown_function_never_executes(trips):
    effects = []
    trips.create_function("side_effect", 0, lambda: effects.append("called") or 1)
    result = csv_sql("SELECT side_effect() FROM trips", connection=trips, clock=lambda: NOW)
    assert_envelope(result, success=False)
    assert effects == []


def test_sql_rejects_temp_shadow_table(trips):
    trips.execute("CREATE TEMP TABLE trips (ride_id TEXT)")
    for sql in ("SELECT * FROM trips", "SELECT COUNT(*) FROM trips"):
        result = csv_sql(sql, connection=trips, clock=lambda: NOW)
        assert_envelope(result, success=False)


def test_sql_rejects_attached_database_even_for_count_optimization(trips):
    trips.execute("ATTACH ':memory:' AS other")
    trips.execute("CREATE TABLE other.trips (private_data TEXT)")
    result = csv_sql("SELECT COUNT(*) FROM other.trips", connection=trips, clock=lambda: NOW)
    assert_envelope(result, success=False)


def test_sql_rejects_side_effecting_override_of_an_allowed_function(trips):
    effects = []
    trips.create_function("abs", 1, lambda _: effects.append("called") or 1)
    result = csv_sql("SELECT abs(duration_minutes) FROM trips", connection=trips, clock=lambda: NOW)
    assert_envelope(result, success=False)
    assert effects == []


def test_sql_returns_errors_for_malformed_or_duplicate_columns(trips):
    for sql in ("SELECT nope FROM trips", "SELECT COUNT(*) AS n, SUM(1) AS n FROM trips"):
        result = csv_sql(sql, connection=trips, clock=lambda: NOW)
        assert_envelope(result, success=False)


def test_sql_bounds_results_and_cleans_handlers(trips):
    trips.executemany(
        "INSERT INTO trips VALUES (?, 1, '2026-09-08T10:00:00')",
        [(str(i),) for i in range(1100)],
    )
    result = csv_sql("SELECT * FROM trips", connection=trips, clock=lambda: NOW)
    assert_envelope(result, success=False)
    assert "row" in result["error"].lower()
    assert trips.execute("SELECT COUNT(*) FROM private_accounts").fetchone()[0] == 1
    summary = csv_sql("SELECT COUNT(*) AS n FROM trips", connection=trips)
    assert summary["success"] is True, summary


def test_sql_bounds_large_computation(trips):
    result = csv_sql(
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<100000000) "
        "SELECT SUM(x) FROM n CROSS JOIN trips",
        connection=trips,
        clock=lambda: NOW,
    )
    assert_envelope(result, success=False)


@pytest.mark.parametrize("expression,expected", [("3 * (2 + 4) / 2", 9), ("-1 + +2.50", 1.5)])
def test_calculator_returns_safe_arithmetic_and_optional_units(expression, expected):
    result = calculator(expression, "USD", clock=lambda: NOW)
    assert_envelope(result, success=True)
    assert result["data"] == {"value": expected, "units": "USD"}
    assert "units" not in calculator("1+2")["data"]


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "abs(-1)",
        "True+1",
        "1e3",
        "2**8",
        "7//2",
        "1/0",
        "1..2",
        "",
        " ",
        "1,2",
        "2%1",
        "0x10",
        "1\n2",
        "9" * 400,
        "(" * 70 + "1" + ")" * 70,
        "." + "0" * 400 + "1",
        "1 / (1-1)",
    ],
)
def test_calculator_rejects_non_arithmetic_and_unbounded_values(expression):
    result = calculator(expression, clock=lambda: NOW)
    assert_envelope(result, success=False)


@pytest.mark.parametrize("units", [42, True, "x" * 81, "USD\nforged line"])
def test_calculator_units_are_a_short_single_line_string(units):
    result = calculator("1+2", units, clock=lambda: NOW)
    assert_envelope(result, success=False)


def test_policy_retriever_ranks_actual_short_passages_and_keeps_source():
    text = (
        "Capital Bikeshare\nExplore the city and its stations.\n"
        "Monthly Membership costs $30 for 30 days.\n"
        "Classic bike rides include the first 45 minutes for members.\n"
        "Members pay $0.05 per additional minute after 45 minutes.\n"
        "Contact our customer service team.\n"
    )
    fetched = []

    def fetcher(url):
        fetched.append(url)
        return {
            "url": url,
            "text": text,
            "captured_at": NOW.isoformat(),
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        }

    result = policy_retriever(
        URL, "monthly membership included minutes overage", 3, fetcher=fetcher, clock=lambda: NOW
    )
    assert_envelope(result, success=True)
    assert fetched == [URL]
    passages = result["data"]["passages"]
    assert len(passages) == 3
    assert any("$30" in passage["text"] for passage in passages)
    assert any("45 minutes" in passage["text"] for passage in passages)
    assert all(set(passage) == {"text", "source", "score"} for passage in passages)
    assert all(passage["source"] == URL and passage["text"] in text for passage in passages)
    assert all(0 < passage["score"] <= 1 and len(passage["text"]) <= 600 for passage in passages)


def test_policy_retriever_no_matching_passage_is_an_explicit_error():
    result = policy_retriever(
        URL,
        "unrelatedword",
        fetcher=lambda _: {
            "url": URL,
            "text": "Monthly Membership costs $30.",
            "captured_at": NOW.isoformat(),
            "sha256": "0" * 64,
        },
        clock=lambda: NOW,
    )
    assert_envelope(result, success=False)


def test_policy_retriever_keeps_price_and_coverage_with_fragmented_html_heading():
    text = "Explore the city\nMonthly Membership\n$30.00\n30 days\nContact us"
    result = policy_retriever(
        URL,
        "monthly membership",
        1,
        fetcher=lambda _: {
            "url": URL,
            "text": text,
            "captured_at": NOW.isoformat(),
            "sha256": "0" * 64,
        },
        clock=lambda: NOW,
    )
    assert_envelope(result, success=True)
    passage = result["data"]["passages"][0]["text"]
    assert "Monthly Membership" in passage and "$30.00" in passage and "30 days" in passage
    assert passage in text


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://127.0.0.1", "https://x:y@example.com"]
)
def test_policy_retriever_rejects_unsafe_urls_before_fetch(url):
    calls = []
    result = policy_retriever(url, "price", fetcher=lambda u: calls.append(u), clock=lambda: NOW)
    assert_envelope(result, success=False)
    assert calls == []


@pytest.mark.parametrize("k", [True, 0, 9, 2.5, "3"])
def test_policy_retriever_bounds_k(k):
    result = policy_retriever(URL, "monthly", k, fetcher=lambda _: {}, clock=lambda: NOW)
    assert_envelope(result, success=False)


def test_policy_retriever_does_not_expose_fetcher_exception_secrets():
    def fetcher(_):
        raise RuntimeError("password=do-not-expose-this")

    result = policy_retriever(URL, "monthly", fetcher=fetcher, clock=lambda: NOW)
    assert_envelope(result, success=False)
    assert "password" not in json.dumps(result)


def test_policy_retriever_rejects_empty_or_untrusted_snapshot_shape():
    for snapshot in (
        {},
        {"url": "file:///private", "text": "Monthly $30"},
        {"url": URL, "text": ""},
        {"url": URL, "text": 42},
    ):
        result = policy_retriever(URL, "monthly", fetcher=lambda _: snapshot, clock=lambda: NOW)
        assert_envelope(result, success=False)


def test_policy_short_title_query_prefers_charge_passages_to_duplicate_navigation():
    text = (
        "30-Day Membership – Capital Bikeshare Help\nLogo\nCapital Bikeshare Help\n"
        "30-Day Membership\nThe 30-Day Membership offers a flexible way to ride.\n"
        "$25 / 30-Day Membership includes:\nUnlimited 45-minute rides on classic bikes for 30 days from purchase.\n"
        "If you need more time, pay $0.05 per minute.\n"
    )
    result = policy_retriever(
        "https://capitalbikeshare.com/pricing/30-day",
        "30 Day Membership",
        k=3,
        fetcher=lambda url: {"url": url, "text": text},
    )
    passages = result["data"]["passages"]
    assert "$25" in passages[0]["text"]
    assert any("45-minute" in p["text"] for p in passages)


def test_full_supported_upload_size_can_run_the_agent_aggregate():
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE trips (scenario_account_id TEXT, rideable_type TEXT, billable_minutes INTEGER)"
        )
        connection.executemany(
            "INSERT INTO trips VALUES (?, ?, ?)",
            [(str(i % 10), "classic_bike", 46) for i in range(20000)],
        )
        result = csv_sql(
            "SELECT COUNT(*) AS rides, COUNT(DISTINCT scenario_account_id) AS accounts, SUM(CASE WHEN rideable_type='classic_bike' THEN billable_minutes ELSE 0 END) AS classic_minutes, SUM(CASE WHEN rideable_type='electric_bike' THEN billable_minutes ELSE 0 END) AS ebike_minutes, SUM(CASE WHEN rideable_type='classic_bike' THEN MAX(billable_minutes-45,0) ELSE 0 END) AS overage FROM trips",
            connection=connection,
        )
        assert result["success"]
        assert result["data"]["rows"] == [
            {
                "rides": 20000,
                "accounts": 10,
                "classic_minutes": 920000,
                "ebike_minutes": 0,
                "overage": 20000,
            }
        ]
    finally:
        connection.close()
