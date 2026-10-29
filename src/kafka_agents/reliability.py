"""Stage-local receipts; Kafka remains the only handoff between stages."""

import json
import sqlite3
from pathlib import Path


class ReceiptStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS receipts (
                correlation_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                output TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS attempts (
                source TEXT PRIMARY KEY, count INTEGER NOT NULL);
        """)

    def lookup(self, correlation_id, fingerprint):
        row = self.connection.execute(
            "SELECT fingerprint, output, published FROM receipts WHERE correlation_id=?",
            (correlation_id,),
        ).fetchone()
        if row is None:
            return None
        if row[0] != fingerprint:
            raise ValueError("correlation_id reused with different payload")
        return json.loads(row[1]), bool(row[2])

    def remember(self, correlation_id, fingerprint, output):
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO receipts(correlation_id,fingerprint,output) VALUES(?,?,?)",
                (correlation_id, fingerprint, json.dumps(output, sort_keys=True)),
            )
        # A concurrent Writer cannot replace the first stored logical result.
        return self.lookup(correlation_id, fingerprint)

    def mark_published(self, correlation_id):
        with self.connection:
            self.connection.execute(
                "UPDATE receipts SET published=1 WHERE correlation_id=?",
                (correlation_id,),
            )

    def attempts(self, source):
        row = self.connection.execute(
            "SELECT count FROM attempts WHERE source=?", (source,)
        ).fetchone()
        return 0 if row is None else row[0]

    def next_attempt(self, source):
        with self.connection:
            self.connection.execute(
                """INSERT INTO attempts(source,count) VALUES(?,1)
                ON CONFLICT(source) DO UPDATE SET count=count+1""",
                (source,),
            )
        return self.attempts(source)

    def close(self):
        self.connection.close()
