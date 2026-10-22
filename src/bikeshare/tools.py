"""Read-only trip SQL, source-linked policy passages, and bounded arithmetic.

The caller supplies one isolated SQLite connection and a policy fetch/cache function.
No model, network client, filesystem reader, or application database is imported here.
"""

import ast
import math
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

ARITHMETIC_PATTERN = r"^[0-9+\-*/().\s]+$"
MAX_SQL_ROWS = 1_000
MAX_SQL_INSTRUCTIONS = 2_000_000
MAX_SQL_SECONDS = 2.0
MAX_VALUE = 1e100
SAFE_SQL_FUNCTIONS = frozenset(
    {
        "abs",
        "avg",
        "coalesce",
        "count",
        "date",
        "datetime",
        "floor",
        "ifnull",
        "iif",
        "instr",
        "julianday",
        "length",
        "lower",
        "ltrim",
        "max",
        "min",
        "nullif",
        "replace",
        "round",
        "rtrim",
        "strftime",
        "substr",
        "substring",
        "sum",
        "time",
        "total",
        "trim",
        "typeof",
        "unixepoch",
        "upper",
    }
)

TOOL_SCHEMAS = [
    {
        "name": "csv_sql",
        "description": (
            "Run exactly one read-only SELECT over the isolated uploaded trips table. "
            "Trip columns include rideable_type (classic_bike/electric_bike), duration_seconds, "
            "billable_minutes, scenario_account_id, coverage_start, and coverage_end. "
            "Returns rows and row_count. Other tables, writes, and multiple statements fail."
        ),
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "minLength": 1, "maxLength": 20_000}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
    {
        "name": "policy_retriever",
        "description": (
            "Retrieve short, source-linked passages from the captured official pricing URL. "
            "Query membership fees, included minutes, unlock fees, and overage rules."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri", "maxLength": 2_048},
                "query": {"type": "string", "minLength": 1, "maxLength": 1_000},
                "k": {"type": "integer", "minimum": 1, "maximum": 8, "default": 3},
            },
            "required": ["url", "query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calculator",
        "description": (
            "Evaluate arithmetic using only decimal numbers, parentheses, +, -, *, and /. "
            "Names, calls, powers, and floor division are rejected."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 1_000,
                    "pattern": ARITHMETIC_PATTERN,
                },
                "units": {"type": "string", "minLength": 1, "maxLength": 80},
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
]


def _utc_now():
    return datetime.now(timezone.utc)


def _envelope(success, *, source, clock, data=None, error=None):
    stamp = clock()
    if isinstance(stamp, datetime):
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(timezone.utc).isoformat()
    result = {"success": success, "source": source, "ts": str(stamp)}
    if success:
        result["data"] = data
    else:
        result["error"] = error
    return result


def _select_leader(sql):
    """Exclude EXPLAIN and non-query statements before SQLite's authorizer runs."""
    without_comments = re.sub(
        r"\A\s*(?:(?:--[^\n]*(?:\n|$)|/\*.*?\*/)\s*)*", "", sql, flags=re.DOTALL
    )
    return re.match(r"(?:SELECT|WITH)\b", without_comments, re.IGNORECASE) is not None


def csv_sql(sql, *, connection, clock=_utc_now):
    """Execute one bounded SELECT; SQLite authorizes every read and operation.

    ``connection`` must be the caller's isolated, per-run uploaded-trip connection,
    created without application-defined functions. It never points to the rental DB.
    """
    source = "uploaded.csv"

    def fail(message):
        return _envelope(False, source=source, clock=clock, error=message)

    if not isinstance(sql, str) or not sql.strip() or len(sql) > 20_000:
        return fail("sql must be a non-empty string of at most 20000 characters.")
    if not isinstance(connection, sqlite3.Connection):
        return fail("An isolated uploaded-trip SQLite connection is required.")
    if not _select_leader(sql):
        return fail("Only one read-only SELECT over trips is permitted.")

    read_trips = False
    denied = False
    steps = 0
    started = time.monotonic()

    def authorize(action, arg1, arg2, database, _trigger):
        nonlocal read_trips, denied
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
            return sqlite3.SQLITE_OK
        # SQLite's optimized COUNT(*) reports an empty column with no database.
        if (
            action == sqlite3.SQLITE_READ
            and arg1 == "trips"
            and (database == "main" or (database is None and arg2 == ""))
        ):
            read_trips = True
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in SAFE_SQL_FUNCTIONS:
            return sqlite3.SQLITE_OK
        denied = True
        return sqlite3.SQLITE_DENY

    def progress():
        nonlocal steps
        steps += 1_000
        return int(steps > MAX_SQL_INSTRUCTIONS or time.monotonic() - started > MAX_SQL_SECONDS)

    try:
        connection.execute("PRAGMA query_only=ON")
        if any(
            row[1] not in {"main", "temp"} for row in connection.execute("PRAGMA database_list")
        ):
            return fail("The uploaded-trip connection cannot contain attached databases.")
        if connection.execute("SELECT 1 FROM temp.sqlite_schema WHERE name='trips'").fetchone():
            return fail("The uploaded trips table cannot be shadowed by a temporary table.")
        table = connection.execute(
            "SELECT type, sql FROM main.sqlite_schema WHERE name='trips'"
        ).fetchone()
        if (
            not table
            or table[0] != "table"
            or not re.match(r"CREATE\s+TABLE\b", table[1] or "", re.IGNORECASE)
        ):
            return fail("The uploaded trips source must be an ordinary SQLite table.")
        overridden = {
            row[0].lower()
            for row in connection.execute("PRAGMA function_list")
            if row[1] == 0 and row[0].lower() in SAFE_SQL_FUNCTIONS
        }
        if overridden:
            return fail(
                "Application-defined overrides of approved SQL functions are not permitted."
            )
        connection.set_authorizer(authorize)
        connection.set_progress_handler(progress, 1_000)
        cursor = connection.execute(sql)
        if not read_trips or cursor.description is None:
            return fail("The SELECT must read the uploaded trips table.")
        columns = [column[0] for column in cursor.description]
        if len(columns) != len(set(columns)):
            return fail("SELECT columns need unique names; use distinct aliases.")
        raw_rows = cursor.fetchmany(MAX_SQL_ROWS + 1)
        if len(raw_rows) > MAX_SQL_ROWS:
            return fail("The SELECT exceeds the 1000-row result limit; aggregate or add LIMIT.")
        rows = [dict(zip(columns, row, strict=True)) for row in raw_rows]
        for row in rows:
            for value in row.values():
                if not isinstance(value, (str, int, float, type(None))):
                    return fail("The SELECT returned a value that cannot be represented in JSON.")
                if isinstance(value, float) and not math.isfinite(value):
                    return fail("The SELECT returned a non-finite number.")
        if sum(len(str(row)) for row in rows) > 1_000_000:
            return fail("The SELECT exceeds the result size limit; select fewer columns or rows.")
        return _envelope(
            True,
            source=source,
            clock=clock,
            data={"rows": rows, "row_count": len(rows), "source": source},
        )
    except sqlite3.Error as exc:
        if denied:
            return fail("SELECT denied: only trips and approved read-only functions are permitted.")
        if steps > MAX_SQL_INSTRUCTIONS or time.monotonic() - started > MAX_SQL_SECONDS:
            return fail("The SELECT exceeded its instruction or time budget.")
        if isinstance(exc, sqlite3.ProgrammingError):
            return fail(
                "Submit exactly one SELECT statement without parameters or extra statements."
            )
        missing = re.fullmatch(r"no such column: ([A-Za-z_][A-Za-z_0-9.]{0,100})", str(exc))
        if missing:
            return fail(
                f"Unknown trip column {missing[1]}. Inspect column names with SELECT * FROM trips LIMIT 1; bike types use rideable_type."
            )
        return fail("Invalid SELECT. Check trip column names, syntax, and approved SQL functions.")
    finally:
        try:
            connection.set_progress_handler(None, 0)
            connection.set_authorizer(None)
        except sqlite3.Error:
            pass  # A closed caller-owned connection already produced a sanitized error.


def _https_url(value):
    if not isinstance(value, str) or not value or len(value) > 2_048:
        return False
    try:
        parts = urlsplit(value)
        return (
            parts.scheme == "https"
            and bool(parts.hostname)
            and not parts.username
            and not parts.password
            and parts.port in (None, 443)
            and not any(character.isspace() for character in value)
        )
    except ValueError:
        return False


def _terms(text):
    return {
        word.rstrip("s")
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) > 1 and word not in {"the", "and", "for", "with", "from", "what", "how"}
    }


def _passage_windows(text):
    """Keep snippets as exact substrings so they can be checked against snapshot bytes."""
    seen = set()
    spans = []
    for match in re.finditer(r"[^\r\n]+", text):
        line = match.group()
        if line.strip():
            start = match.start() + len(line) - len(line.lstrip())
            end = match.end() - len(line) + len(line.rstrip())
            spans.append((start, end))
    for index, (line_start, line_end) in enumerate(spans):
        line = text[line_start:line_end]
        if len(line) <= 600:
            window_end = spans[min(index + 2, len(spans) - 1)][1]
            window = text[line_start:window_end]
            # A heading, fee, and duration may occupy separate HTML text lines.
            candidates = [window, line] if len(window) <= 600 else [line]
        else:
            candidates = []
            start = 0
            while start < len(line):
                end = min(start + 600, len(line))
                if end < len(line):
                    boundary = line.rfind(" ", start + 300, end)
                    if boundary != -1:
                        end = boundary
                candidates.append(line[start:end])
                start = end
                while start < len(line) and line[start].isspace():
                    start += 1
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                yield candidate


def policy_retriever(url, query, k=3, *, fetcher, clock=_utc_now):
    """Rank captured policy lines without inventing text or fetching in toolcore.

    The injected fetch/cache function enforces official-host/redirect/network policy
    and retains exact snapshot bytes, capture time, and SHA-256 for run evidence.
    """
    source = url if _https_url(url) else "policy"

    def fail(message):
        return _envelope(False, source=source, clock=clock, error=message)

    if not _https_url(url):
        return fail("url must be an HTTPS policy URL without credentials or a nonstandard port.")
    if not isinstance(query, str) or not query.strip() or len(query) > 1_000:
        return fail("query must be a non-empty string of at most 1000 characters.")
    if type(k) is not int or not 1 <= k <= 8:
        return fail("k must be an integer from 1 through 8.")
    query_terms = _terms(query)
    if not query_terms:
        return fail("query must contain searchable pricing terms.")
    try:
        snapshot = fetcher(url)
    except Exception:
        return fail("The official policy snapshot could not be fetched or loaded.")
    if not isinstance(snapshot, dict) or not _https_url(snapshot.get("url")):
        return fail("The policy fetcher did not return a valid source URL.")
    text = snapshot.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 2_000_000:
        return fail("The policy snapshot must contain non-empty text within the size limit.")
    source = snapshot["url"]
    candidates = []
    for index, passage in enumerate(_passage_windows(text)):
        matched = len(query_terms & _terms(passage))
        if matched:
            charge_rule = bool(re.search(r"\$\s*\d|round(?:ed|ing)\s+up", passage, re.I))
            score = 0.5 * matched / len(query_terms) + 0.5 * charge_rule
            lead_matches = len(query_terms & _terms(passage.splitlines()[0]))
            candidates.append(
                (-score, -lead_matches, index, {"text": passage, "source": source, "score": score})
            )
    candidates.sort(key=lambda item: item[:3])
    if not candidates:
        return fail("No relevant passage matched the query in the captured policy text.")
    return _envelope(
        True,
        source=source,
        clock=clock,
        data={"passages": [candidate[3] for candidate in candidates[:k]]},
    )


def _arithmetic(node, depth=0):
    if depth > 32:
        raise ValueError("The expression is too deeply nested.")
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = node.value
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _arithmetic(node.operand, depth + 1)
        value = operand if isinstance(node.op, ast.UAdd) else -operand
    elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _arithmetic(node.left, depth + 1)
        right = _arithmetic(node.right, depth + 1)
        if isinstance(node.op, ast.Add):
            value = left + right
        elif isinstance(node.op, ast.Sub):
            value = left - right
        elif isinstance(node.op, ast.Mult):
            value = left * right
        else:
            value = left / right
    else:
        raise ValueError("Use only numbers, parentheses, and +, -, *, / arithmetic.")
    if not math.isfinite(value) or abs(value) > MAX_VALUE:
        raise ValueError("The expression exceeded the finite numeric magnitude limit.")
    return value


def calculator(expression, units=None, *, clock=_utc_now):
    """Evaluate the assignment's arithmetic whitelist through a small AST interpreter."""
    source = "calculator"

    def fail(message):
        return _envelope(False, source=source, clock=clock, error=message)

    if (
        not isinstance(expression, str)
        or not expression.strip()
        or len(expression) > 1_000
        or re.fullmatch(ARITHMETIC_PATTERN, expression) is None
    ):
        return fail("expression must contain only numbers, whitespace, +, -, *, /, (, ), and dots.")
    if units is not None and (
        not isinstance(units, str)
        or not units.strip()
        or len(units) > 80
        or any(ord(character) < 32 for character in units)
    ):
        return fail("units must be a non-empty single-line string of at most 80 characters.")
    for literal in re.findall(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", expression):
        if float(literal) == 0 and any(character in "123456789" for character in literal):
            return fail("A nonzero decimal literal underflows the supported numeric range.")
    # A lexical limit also rejects parentheses that Python drops from its AST.
    nesting = 0
    for character in expression:
        nesting += (character == "(") - (character == ")")
        if nesting > 32:
            return fail("The expression is too deeply nested.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 256:
            return fail("The expression exceeds the arithmetic operation limit.")
        value = _arithmetic(tree.body)
    except ZeroDivisionError:
        return fail("Division by zero is not permitted.")
    except (SyntaxError, ValueError, OverflowError, RecursionError):
        return fail("Invalid or unbounded arithmetic; use finite decimal values and +, -, *, /.")
    data = {"value": value}
    if units is not None:
        data["units"] = units
    return _envelope(True, source=source, clock=clock, data=data)
