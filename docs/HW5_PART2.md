# HW5 Part 2: Meals and Rental MCP servers

Part 2 provides two independent servers using the official Python MCP SDK and
STDIO transport. Meals uses `FastMCP`; rentals uses the public low-level `Server`
API so the SDK validates the shared strict schemas before dispatch. A client starts the Python process and
exchanges MCP messages through its standard input and output. Neither server
needs the FastAPI application on port 8702. Standard output is reserved for MCP
traffic; diagnostics go to standard error.

The Meals server calls TheMealDB. The rental server reads public columns from
MySQL through the shared `src/rental_tools` contracts, service, static registry,
and injectable reader. The servers do not initialize databases or connect during
imports. This implementation covers Parts 2A and 2B; the later reliability
experiment, executor, privacy flag, and agent loop are outside this part.

## Python environment and launch

Run these commands from the repository root using Python 3.12:

```bash
python3.12 -m venv .venv-mcp
.venv-mcp/bin/python -m pip install -r requirements-mcp.txt
.venv-mcp/bin/python -m pip check
```

Use this dedicated environment. The older web environment pins Uvicorn 0.27.0,
whereas MCP 1.28.1 requires a newer Uvicorn. `requirements-mcp.txt` pins
`mcp[cli]==1.28.1`, HTTPX 0.28.1, Pydantic 2.12.5, SQLAlchemy 2.0.48,
PyMySQL 1.1.2, cryptography 46.0.5, and pytest 8.4.2. This is the official `mcp`
package, not the separately distributed `fastmcp` package.

The launch commands are:

```bash
.venv-mcp/bin/python scripts/hw05/part2/run_meals.py
.venv-mcp/bin/python scripts/hw05/part2/run_domain.py
```

A process waiting quietly for an MCP client is normal. These launchers also work
from another directory when both the Python executable and script are supplied
as absolute paths. Quote paths containing spaces in shell commands.

Before starting the domain server, set `HW5_MCP_DATABASE_URL` privately in the
launching shell. It must use the `mysql+pymysql` driver and explicitly select
database `s6102_rel`. Its shape is:

```text
mysql+pymysql://hw5_reader:<URL-encoded-password>@127.0.0.1:3308/s6102_rel
```

The placeholder is not a credential. Use a read-only database account and avoid
placing a real DSN in source files, command history, screenshots, or submitted
logs. The adapter does not fall back to the web application's environment
variables. An absent, malformed, wrong-driver, or wrong-database DSN produces a
sanitized configuration error when a read is requested. Connection timeout is
5 seconds; database read and write socket timeouts are 10 seconds. The runtime
issues only SELECT statements and does not import the web application's ORM or
database setup.

## Meals tool contracts

Server name: `meals`. Its inventory contains exactly these four tools:

| Tool | Inputs | Endpoint and JSON result |
| --- | --- | --- |
| `search_meals_by_name` | Nonempty string `query`; strict integer `limit=5`, range 1–25 | `search.php?s=…`; list of `{id,name,area,category,thumb}` |
| `meals_by_ingredient` | Nonempty string `ingredient`; strict positive integer `limit=12` | `filter.php?i=…`; list of `{id,name,thumb}` |
| `random_meal` | No inputs | `random.php`; one full recipe or `null` |
| `meal_details` | `id`: positive integer or ASCII digit string containing a nonzero digit | `lookup.php?i=…`; one full recipe or `null` |

The fixed base URL is `https://www.themealdb.com/api/json/v1/1/`, using the
educational key `1`. Ingredient-search limits have no additional maximum in this
contract. Input text is trimmed, and whitespace-only text fails validation.
Boolean values are not valid integer limits or IDs.

A full recipe has this shape:

```json
{
  "id": "52771",
  "name": "Spicy Arrabiata Penne",
  "category": "Vegetarian",
  "area": "Italian",
  "instructions": "...",
  "image": "...",
  "source": "...",
  "youtube": "...",
  "ingredients": [{"name": "penne rigate", "measure": "1 pound"}]
}
```

Optional upstream string fields can be `null`. Numbered ingredient fields are
combined with their measurement fields, blank ingredient names are omitted,
ingredient names are trimmed, and absent measurements become empty strings.
The first MCP text block contains the JSON value. An empty result remains `[]`
for either search and `null` for a detail/random lookup; a second text block says
`No matches.` The Meals server does not use the rental result envelope.

HTTPX applies a finite 10-second timeout. Timeouts, network errors, unsuccessful
HTTP status codes, invalid JSON, and malformed response shapes produce clean
MCP error text with `isError: true`. SDK input-schema failures also use native
MCP error results. Controlled tests exercise these failures without relying on
the public service being unavailable.

## Rental tool contracts

Server name: `rentals`. Its inventory contains exactly these three tools:

| Tool | Inputs | Successful `data` |
| --- | --- | --- |
| `search_rentals` | Strict string `query`, raw length 1–255; strict integer `limit=5`, range 1–25 | `{items:[…],returnedCount,limit}` |
| `get_rental` | Strict positive integer `rental_id` | One public rental, including `description` |
| `count_rentals` | Strict positive integer `manager_id` | `{managerId,managerName,count}` |

Query length is checked before trimming, so surrounding spaces count toward the
255-character maximum. After trimming, at least one non-whitespace character
must remain. Search examines only titles and addresses and returns ascending
rental IDs, up to the requested limit. `returnedCount` counts returned items,
not every match in the database. A search with no matches succeeds with an
empty `items` list.

Every public rental contains only `id`, `listingTitle`, `propertyAddress`,
`propertyType`, and `managerId`; the detail tool additionally returns
`description`. An unassigned rental preserves `managerId: null`. No submitter
email, manager email, authentication data, or session data is exposed.

Successful application results have this envelope:

```json
{"ok":true,"data":{"managerId":3,"managerName":"Empty Portfolio","count":0},"error":null}
```

An existing manager with no assigned rentals succeeds with `count: 0`. A missing
manager or rental produces an application failure:

```json
{"ok":false,"data":null,"error":"Rental 8 was not found."}
```

The three intentional semantic failures used for this fixture are:

| Tool | Arguments | Application result |
| --- | --- | --- |
| `search_rentals` | `{"query":"   ","limit":5}` | `ok:false`, invalid non-whitespace query |
| `get_rental` | `{"rental_id":8}` | `ok:false`, rental not found |
| `count_rentals` | `{"manager_id":4}` | `ok:false`, property manager not found |

These arguments pass the published SDK schema and reach the shared handler.
Their MCP results have `isError: false`, with the failure described in the JSON
envelope. The SDK also supplies the envelope as `structuredContent`.

Native SDK validation is a separate boundary. The recorded STDIO calls with
`{}`, `{"rental_id":false}`, `{"rental_id":0}`, and
`{"rental_id":"1"}` all return `isError: true`, native validation text, and
`structuredContent: null`. In particular, the string `"1"` is not coerced into
an integer by the tested rental server. Do not expect an application envelope
for these requests. All three published input schemas come directly from the
shared models and include `additionalProperties: false`. An unexpected field
such as `bogus` produces a native SDK error before the handler or reader runs.
Arguments remain flat objects with the same named fields and defaults.

The domain wrapper uses public `Server.list_tools`, `Server.call_tool` with
`validate_input=True`, and `stdio_server` APIs. FastMCP 1.28.1 silently discarded
unexpected fields before its handlers; the low-level API validates the original
arguments. No private SDK state is patched. The broad dictionary output schemas,
public result projection, and application envelopes remain unchanged.

JSON Schema treats `1.0` as an integer. It therefore reaches the shared strict
Pydantic model, which rejects it with an application failure before reader access.
It is never coerced into an accepted ID or limit. Whitespace-only queries likewise
remain application failures. Actual STDIO tests verify these boundaries and use
a subprocess reader access log, with valid control calls, to prove rejected
extra fields and integral floats do not reach the reader.

Database/configuration failures return sanitized application envelopes. Raw
SQL, dependency exception messages, and connection credentials are omitted.

### Literal text and Unicode search

The MySQL adapter binds input values as parameters and escapes `%`, `_`, and
`!` for a literal substring `LIKE` search using `!` as the escape character.
Quotes and backslashes remain bound data. It applies MySQL `LOWER` to both
operands and compares with `utf8mb4_bin`. This makes case behavior follow
MySQL's lowercase mappings while preserving accents and code-point sequences.
It does not use Python `casefold` or Unicode normalization.

The MySQL 8.4.11 checks in `reports/hw05/raw/part2/mysql-checks.json` confirmed:

- `%` and `_` match only the fixture title containing those literal characters.
- A quote and a backslash match the corresponding literal title; an SQL-like
  string (`' OR 1=1 --`) returns no rows.
- `CAFÉ` matches `Café`; unaccented `cafe` does not.
- `straße` matches `Straße`; `STRASSE` does not.
- Decomposed `cafe` plus a combining acute accent does not match composed `Café`.
- Address matching returns stable ascending IDs, an empty manager counts as
  zero, and an unassigned rental keeps a null manager ID.

The offline fake reader is useful for deterministic contract tests, but it is
not proof of all MySQL Unicode behavior.

## Explicit isolated fixture setup

The recorded live database is an owned MySQL 8.4.11 instance at
`127.0.0.1:3308`, database `s6102_rel`. It is separate from Part 1's MySQL on
3307 and application on 8702. Check port availability before starting an owned
instance, and give it its own data directory and credentials.

Administrative setup is separate from both server launchers:

1. Create the empty database `s6102_rel` on the owned 3308 instance.
2. Privately set `HW5_FIXTURE_ADMIN_URL` to its administrative `mysql+pymysql`
   DSN and `HW5_FIXTURE_READER_PASSWORD` to a new reader password.
3. Run the command below once. It refuses any destination other than
   `mysql+pymysql` at `127.0.0.1:3308/s6102_rel`, and refuses a database that
   already contains tables.

```bash
.venv-mcp/bin/python scripts/hw05/part2/setup_fixture.py
```

The administrative connection uses finite connect/read/write socket timeouts
of 5/10/10 seconds, matching the reader. An offline test checks the effective
PyMySQL connection options before any network access or database setup.

The script applies the existing `code/web_application/migrations/001_initial.sql`
baseline, inserts seven synthetic rentals and three managers, and creates
`hw5_reader` with these column-level permissions:

```sql
GRANT SELECT (id, listing_title, property_address, description, property_type, manager_id)
ON s6102_rel.rentals TO 'hw5_reader'@'%';
GRANT SELECT (id, name)
ON s6102_rel.property_managers TO 'hw5_reader'@'%';
```

It does not grant writes or access to contact/authentication fields. The live
checks confirmed that reading the private submitter-email column was denied.
Set `HW5_MCP_DATABASE_URL` to this reader's DSN for the runtime. Do not give the
server the administrative DSN. Unset fixture administration variables after
setup. MySQL DDL is not transactionally rolled back; if setup is interrupted,
inspect that owned instance rather than resetting or blindly rerunning it.
The saved fixture record documents the initial grant-command failure and its
explicit repair without replacing the already seeded rows.

## Inspector UI

The selected Inspector version is 1.0.2, with all four packages pinned to that
version. Its package `engines.node` declaration is `>=22.7.5`; the runtime used
for this work is Node 24.19.0. The repository's unrelated browser-check package
does not define Inspector's Node requirement.

Choose an external runtime directory, set `INSPECTOR_DIR` to its absolute path,
and install the pins there. Keep that runtime and its dependencies out of Git:

```bash
mkdir -p "$INSPECTOR_DIR"
npm install --prefix "$INSPECTOR_DIR" --save-exact \
  @modelcontextprotocol/inspector@1.0.2 \
  @modelcontextprotocol/inspector-cli@1.0.2 \
  @modelcontextprotocol/inspector-client@1.0.2 \
  @modelcontextprotocol/inspector-server@1.0.2
```

From the repository root, after privately exporting the read-only domain DSN
when needed, start the UI on 6274 and its proxy on 6277:

```bash
CLIENT_PORT=6274 SERVER_PORT=6277 MCP_AUTO_OPEN_ENABLED=false \
  "$INSPECTOR_DIR/node_modules/.bin/mcp-inspector"
```

Open the authenticated local URL printed by Inspector. Keep the generated proxy
token private. Use one server at a time. Select **STDIO** and fill the fields as
follows, replacing the example repository prefix with the actual absolute path:

| Field | Value |
| --- | --- |
| Command | `/absolute/path/with spaces/to/repository/.venv-mcp/bin/python` |
| Arguments for Meals | `'/absolute/path/with spaces/to/repository/scripts/hw05/part2/run_meals.py'` |
| Arguments for rentals | `'/absolute/path/with spaces/to/repository/scripts/hw05/part2/run_domain.py'` |

The **Command** field is the executable path itself, without surrounding quote
characters. The **Arguments** field is shell-parsed, so retain the single quotes
around a script path containing spaces. These field rules differ from a shell
command, where both paths require quoting. The launched Inspector proxy inherits
the exported `HW5_MCP_DATABASE_URL`; avoid entering credentials in the UI's
environment fields or an Inspector `-e` argument, which can appear in logs.

Connect, list tools, verify the exact inventory, then call each tool. Use Meals
inputs `{"query":"Arrabiata","limit":5}`,
`{"ingredient":"chicken","limit":3}`, `{}`, and `{"id":"52771"}`.
For the synthetic rental fixture, use a successful search for
`Sunny Downtown Apartment`, rental ID 1, and manager ID 1, plus the three rejected
cases above. Preserve actual inputs and outputs. Determine absent IDs again
when using a different database.

Required GUI evidence is four Meals input/output screenshots and six rental
screenshots, one success and one semantic failure per rental tool. Label domain
captures with the actual MySQL source. The JSON STDIO captures described below
do not establish that these Inspector screenshots have been taken. Before any
terminal screenshot, print `Pragya Apurva` in that terminal. Keep credentials and
Inspector authentication tokens outside screenshot frames. Disconnect and stop
only the Inspector/server processes started for this session.

## Verification and evidence

Run the focused tests from the dedicated environment:

```bash
.venv-mcp/bin/python -m pytest \
  tests/test_hw05_meals.py \
  tests/test_hw05_domain_tools.py \
  tests/test_hw05_mcp_stdio.py \
  tests/test_hw05_fixture_setup.py
```

These tests use controlled upstream responses and injected readers. They check
normalization, contracts, public projection, failure handling, SQL construction,
network-free imports, and real subprocess STDIO initialization/discovery/calls.
They do not substitute for live TheMealDB or MySQL evidence.

Capture live calls with the official MCP `ClientSession` over actual STDIO:

```bash
.venv-mcp/bin/python scripts/hw05/part2/capture_stdio.py \
  meals reports/hw05/raw/part2/meals-stdio.json
.venv-mcp/bin/python scripts/hw05/part2/capture_stdio.py \
  domain reports/hw05/raw/part2/domain-stdio.json
```

Each output records initialization, exact tool inventory, published input
schemas, requests, responses, timestamp, source identity, and current Git HEAD.
The script overwrites its chosen output path; choose a new filename to preserve
an earlier run. Record uncommitted source changes separately when interpreting
the revision. The current saved live records contain four successful Meals
calls and six domain calls with the expected success/failure envelopes. The
domain capture additionally records four native SDK validation errors and one
unexpected-field rejection per rental tool. Captures also record whether the
worktree was dirty; use accompanying source hashes to identify uncommitted code.

The domain capture reads a real existing rental and manager, determines IDs
above each current maximum, verifies those IDs are absent, and uses them for the
missing-record cases. It requires at least one rental and one manager. Its DSN
is read from the environment; saved metadata includes host, port, database, and
username, but no password. Run against a stable read window so concurrent
inserts do not invalidate the absent-ID check.

`database-fixture.json` identifies the synthetic data, baseline hash, and runtime
grants. `mysql-checks.json` records live literal/Unicode and privilege checks.
`meals-stdio.json` and `domain-stdio.json` are genuine transport records, not
Inspector screenshots. Submission evidence status and capture mapping belong
in `reports/hw05/part2/EVIDENCE.md`; do not infer GUI completion from JSON files.

## Integration with Part 1

After Part 1's migration is integrated and independently verified, obtain a
read-only DSN for that migrated `s6102_rel` database. Grant only the public
columns listed above, export it as `HW5_MCP_DATABASE_URL`, and rerun the domain
STDIO capture to a distinct file. Then repeat all three domain success/failure
calls in Inspector against that same source.

Do not run `setup_fixture.py` on Part 1's database. No schema upgrade or seed is
needed by the MCP server: it deliberately reads only stable HW4 columns. This
recapture verifies the combined schema and supplies actual absent IDs for that
dataset without changing its rows.

The reusable `RentalReader` interface has `search_rentals(query, limit)`,
`get_rental(rental_id)`, and `count_rentals(manager_id)`. `RentalService` validates
inputs and creates the public envelopes. `TOOL_REGISTRY` is a static allowlist
with descriptions, input models, and service handlers. Later parts can use
these interfaces without adding tools to this part's MCP inventory.
