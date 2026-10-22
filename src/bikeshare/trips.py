import csv
import hashlib
import io
import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000
ORIGINAL_FIELDS = (
    "ride_id",
    "rideable_type",
    "started_at",
    "ended_at",
    "start_station_name",
    "start_station_id",
    "end_station_name",
    "end_station_id",
    "start_lat",
    "start_lng",
    "end_lat",
    "end_lng",
    "member_casual",
)
ACCOUNT_FIELDS = (
    "scenario_account_id",
    "coverage_start",
    "coverage_end",
    "scenario_account_assumption",
)
PROVENANCE_FIELDS = ("source_csv", "source_row_number", "source_csv_sha256")


def _datetime(value, field):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}: use an ISO date and time.") from exc


def parse_trips(csv_bytes):
    """Require an explicit 30-day membership basis; never infer rider identities."""
    if not isinstance(csv_bytes, bytes) or not csv_bytes or len(csv_bytes) > MAX_BYTES:
        raise ValueError("Upload a nonempty UTF-8 CSV of at most 5 MiB.")
    try:
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"), newline=""))
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or any(
            not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", name) for name in fields
        ):
            raise ValueError("CSV column names must be unique simple identifiers.")
        missing = set(ORIGINAL_FIELDS + ACCOUNT_FIELDS) - set(fields)
        if missing:
            raise ValueError(
                "Missing trip/account/coverage assumption columns: " + ", ".join(sorted(missing))
            )
        if {"duration_seconds", "billable_minutes"} & set(fields):
            raise ValueError("duration_seconds and billable_minutes are reserved derived columns.")
        present_provenance = set(PROVENANCE_FIELDS) & set(fields)
        if present_provenance and len(present_provenance) != len(PROVENANCE_FIELDS):
            raise ValueError(
                "Source provenance requires CSV name, row number, and SHA-256 together."
            )
        rows, seen, accounts, windows, assumptions = [], set(), defaultdict(list), set(), set()
        for line, row in enumerate(reader, 2):
            if len(rows) >= MAX_ROWS:
                raise ValueError("Upload at most 20,000 trip rows.")
            if None in row or any(value is None for value in row.values()):
                raise ValueError(
                    f"CSV row {line} has a different number of columns from its header."
                )
            if not row["ride_id"].strip() or row["ride_id"] in seen:
                raise ValueError(f"CSV row {line} needs a unique nonempty ride_id.")
            seen.add(row["ride_id"])
            if row["rideable_type"] not in {"classic_bike", "electric_bike"}:
                raise ValueError(
                    f"CSV row {line}: supported bike types are classic_bike and electric_bike."
                )
            if (
                not row["scenario_account_id"].strip()
                or not row["scenario_account_assumption"].strip()
            ):
                raise ValueError(
                    "Every row needs an account ID and explicit account assignment assumption."
                )
            start = _datetime(row["started_at"], "started_at")
            end = _datetime(row["ended_at"], "ended_at")
            coverage_start = _datetime(row["coverage_start"], "coverage_start")
            coverage_end = _datetime(row["coverage_end"], "coverage_end")
            if (
                len({value.tzinfo is None for value in (start, end, coverage_start, coverage_end)})
                != 1
            ):
                raise ValueError(
                    "Trip and coverage timestamps must use a consistent timezone basis."
                )
            if coverage_end - coverage_start != timedelta(days=30):
                raise ValueError("Every account must have one explicit 30-day coverage window.")
            if (
                coverage_start.tzinfo is None
                and coverage_start.replace(tzinfo=ZoneInfo("America/New_York")).utcoffset()
                != coverage_end.replace(tzinfo=ZoneInfo("America/New_York")).utcoffset()
            ):
                raise ValueError(
                    "A local-time window crossing daylight-saving changes requires explicit UTC offsets and 30 elapsed days."
                )
            if not coverage_start <= start < end <= coverage_end:
                raise ValueError(
                    f"CSV row {line}: trip duration must be positive and within coverage."
                )
            seconds = (end - start).total_seconds()
            if seconds > 24 * 3600:
                raise ValueError("Trips over 24 hours need separate penalty-policy review.")
            windows.add((coverage_start.isoformat(), coverage_end.isoformat()))
            assumptions.add(row["scenario_account_assumption"])
            accounts[row["scenario_account_id"]].append((start, end))
            if present_provenance:
                if not re.fullmatch(r"[0-9a-f]{64}", row["source_csv_sha256"]):
                    raise ValueError("Source CSV SHA-256 must be a lowercase 64-character digest.")
                if not row["source_row_number"].isdigit() or int(row["source_row_number"]) < 2:
                    raise ValueError(
                        "Source row numbers are 1-based CSV records, with the header at 1."
                    )
                if not row["source_csv"].strip():
                    raise ValueError("Source CSV name must be nonempty.")
            rows.append(
                {**row, "duration_seconds": seconds, "billable_minutes": math.ceil(seconds / 60)}
            )
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("Invalid UTF-8 CSV upload.") from exc
    if not rows:
        raise ValueError("Upload at least one trip row.")
    if len(windows) != 1:
        raise ValueError("Use one common 30-day coverage window for this comparison.")
    for account, rides in accounts.items():
        ordered = sorted(rides)
        for previous, current in zip(ordered, ordered[1:]):
            if previous[1] + timedelta(minutes=2) > current[0]:
                raise ValueError(
                    f"Account {account}: overlapping rides or less than a 2-minute turnaround."
                )
    coverage_start, coverage_end = next(iter(windows))
    return {
        "rows": rows,
        "columns": fields,
        "row_count": len(rows),
        "account_count": len(accounts),
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "input_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "assumptions": sorted(assumptions)
        + [
            "Each scenario account purchases its own 30-day membership at coverage_start; fees cannot be shared between accounts.",
            "The coverage end is exclusive for trip starts; every trip must finish within coverage.",
            "Offset-free trip timestamps are interpreted in America/New_York local time; no observed rider identity is inferred.",
        ],
    }


def open_trip_database(dataset):
    """Use a private in-memory SQLite table; uploaded text is bound as data."""
    columns = dataset["columns"]
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    definitions = [f'"{name}" TEXT' for name in columns]
    definitions += ["duration_seconds REAL", "billable_minutes INTEGER"]
    connection.execute("CREATE TABLE trips (" + ", ".join(definitions) + ")")
    names = columns + ["duration_seconds", "billable_minutes"]
    connection.executemany(
        "INSERT INTO trips VALUES (" + ",".join("?" for _ in names) + ")",
        ([row[name] for name in names] for row in dataset["rows"]),
    )
    connection.commit()
    return connection
