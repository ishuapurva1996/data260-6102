"""One JSON event per line, with aware UTC time and process identity."""
from datetime import datetime, timezone
import json
import os


def event(name: str, **fields):
    record = {'timestamp': datetime.now(timezone.utc).isoformat(),
              'student': 'Pragya Apurva', 'source_commit': os.getenv('HW8_SOURCE_COMMIT', 'unrecorded'),
              'pid': os.getpid(), 'event': name, **fields}
    print(json.dumps(record, default=str, sort_keys=True), flush=True)
    return record
