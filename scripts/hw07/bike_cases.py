"""Reproduce public 500-row scenarios from the SHA-pinned official January archive.

Download the manifest's source URL separately, then pass --source CSV_OR_ZIP.
No prices or application cost calculations influence which rows are selected.
"""

import argparse
import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

CSV_NAME = "202401-capitalbikeshare-tripdata.csv"
CSV_SHA256 = "bb189909da35620f98191dab9a4ba6ca36162d92917bfee174d91ad5704336b9"
ZIP_SHA256 = "48d11e148db00bd53c47fe419b166f37862faefac61a1ce9503b87017573ed34"
ROOT = Path(__file__).resolve().parents[2]
START = datetime(2024, 1, 1)
END = datetime(2024, 1, 31)
SCENARIOS = (("frequent", 300, 3600, 10, 50), ("occasional", 60, 300, 125, 4))
EXTRA_FIELDS = [
    "source_csv",
    "source_row_number",
    "source_csv_sha256",
    "scenario_account_id",
    "coverage_start",
    "coverage_end",
    "scenario_account_assumption",
]


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def read_source(path):
    payload = path.read_bytes()
    if path.suffix.lower() == ".zip":
        if _sha(payload) != ZIP_SHA256:
            raise ValueError("Official source archive SHA-256 differs from the frozen source.")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            payload = archive.read(CSV_NAME)
    if _sha(payload) != CSV_SHA256:
        raise ValueError("Source CSV SHA-256 differs from the frozen official CSV.")
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8"), newline=""))
    fields = reader.fieldnames
    rows = []
    for row_number, row in enumerate(reader, 2):
        start = datetime.fromisoformat(row["started_at"])
        end = datetime.fromisoformat(row["ended_at"])
        if row["rideable_type"] == "classic_bike" and START <= start < end < END:
            rows.append((start, end, int((end - start).total_seconds()), row_number, row))
    return fields, rows


def select_rows(source_rows, name, low, high, account_count, rides_per_account):
    daily = defaultdict(list)
    for entry in source_rows:
        if low <= entry[2] <= high:
            daily[entry[0].date()].append(entry)
    selected = []
    for day_index in range(30):
        day = (START + timedelta(days=day_index)).date()
        eligible = sorted(daily[day], key=lambda item: (item[0], item[4]["ride_id"], item[3]))
        quota = 17 if day_index < 20 else 16
        if len(eligible) < quota:
            raise ValueError(f"Insufficient genuine rows for {name} on {day}.")
        for index in range(quota):
            selected.append(eligible[((2 * index + 1) * len(eligible)) // (2 * quota)])
    selected.sort(key=lambda item: (item[0], item[4]["ride_id"], item[3]))
    account_rides, last_end = defaultdict(int), {}
    output, provenance = [], []
    for start, end, _seconds, row_number, original in selected:
        available = [
            account
            for account in range(1, account_count + 1)
            if account_rides[account] < rides_per_account
            and (account not in last_end or last_end[account] + timedelta(minutes=2) <= start)
        ]
        if not available:
            raise ValueError("Cannot assign hypothetical accounts without overlapping rides.")
        account = min(available, key=lambda item: (account_rides[item], item))
        account_rides[account] += 1
        last_end[account] = end
        output.append(
            {
                **original,
                "source_csv": CSV_NAME,
                "source_row_number": row_number,
                "source_csv_sha256": CSV_SHA256,
                "scenario_account_id": f"{name}-{account:03}",
                "coverage_start": START.isoformat(),
                "coverage_end": END.isoformat(),
                "scenario_account_assumption": "hypothetical assigned account; not observed rider history",
            }
        )
        provenance.append(
            {
                "ride_id": original["ride_id"],
                "source_row_number": row_number,
                "original_values_sha256": _sha(
                    json.dumps(
                        original, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                    ).encode("utf-8")
                ),
            }
        )
    if (
        len(output) != 500
        or len(account_rides) != account_count
        or any(count != rides_per_account for count in account_rides.values())
    ):
        raise ValueError("Reproducible selection failed its row/account-count invariant.")
    return output, provenance


def reproduce(source, output, verify=False):
    fields, eligible = read_source(source)
    manifest = {
        "schema_version": 1,
        "student": "Pragya Apurva",
        "source": {
            "system": "Capital Bikeshare, Washington metropolitan area",
            "csv_name": CSV_NAME,
            "csv_sha256": CSV_SHA256,
            "archive_sha256": ZIP_SHA256,
            "url": "https://s3.amazonaws.com/capitalbikeshare-data/202401-capitalbikeshare-tripdata.zip",
            "source_page": "https://capitalbikeshare.com/system-data",
            "captured_at": "2026-10-22T06:45:29.984478+00:00",
            "original_fields": fields,
            "source_row_number_basis": "1-based CSV record number, header=1; source contains no multiline records.",
        },
        "coverage_start": START.isoformat(),
        "coverage_end": END.isoformat(),
        "coverage_timezone_assumption": "America/New_York; offset-free original timestamps, January 2024 EST.",
        "selection_algorithm": "For each January 1–30 date, filter classic_bike and inclusive scenario duration range; sort by (started_at, ride_id, source_row_number). Select 17 rows on first 20 dates and 16 on the last 10 using index floor((2*i+1)*day_count/(2*quota)). Sort all selected rows by the same tuple.",
        "assignment_algorithm": "Chronological rows go to the available account with minimum (assigned_ride_count, account_number), subject to the scenario's per-account cap and at least two minutes since that account's previous trip ended.",
        "assumptions": [
            "Account labels are hypothetical scenario assignments, not observed rider histories or true rider identities.",
            "Each account separately purchases a membership at January 1 coverage_start for the same 30-day window; one membership does not cover unrelated accounts.",
            "No assertion is made about true rider travel trajectories or which plan the original rider bought.",
            "All thirteen original source trip fields remain unchanged; appended columns only describe provenance and scenario assumptions.",
            "Current captured prices will be applied counterfactually to observed 2024 durations, with pre-tax base transportation costs only.",
        ],
        "scenarios": {},
    }
    for name, low, high, accounts, rides_per_account in SCENARIOS:
        rows, provenance = select_rows(eligible, name, low, high, accounts, rides_per_account)
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields + EXTRA_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        payload = buffer.getvalue().encode("utf-8")
        path = output / f"{name}.csv"
        if verify:
            if path.read_bytes() != payload:
                raise ValueError(f"{path.name} differs from the reproducible genuine selection.")
        else:
            output.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        manifest["scenarios"][name] = {
            "path": path.name,
            "sha256": _sha(payload),
            "row_count": len(rows),
            "account_count": accounts,
            "rides_per_account": rides_per_account,
            "duration_seconds_inclusive": [low, high],
            "original_row_provenance": provenance,
        }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    manifest_path = output / "manifest.json"
    if verify:
        if manifest_path.read_bytes() != manifest_bytes:
            raise ValueError("Scenario manifest differs from the frozen reproducible selection.")
    else:
        manifest_path.write_bytes(manifest_bytes)
    return {
        name: {key: value for key, value in scenario.items() if key != "original_row_provenance"}
        for name, scenario in manifest["scenarios"].items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/hw07/cases/bikeshare")
    parser.add_argument(
        "--verify", action="store_true", help="Compare all bytes without modifying any case."
    )
    args = parser.parse_args()
    print(json.dumps(reproduce(args.source, args.output, args.verify), indent=2))


if __name__ == "__main__":
    main()
