"""Research-only SQLite monotonic epoch allocator; no production broker wiring."""
import sqlite3
from pathlib import Path

class DurableEpochStore:
    def __init__(self, path):
        self.path = str(Path(path))
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS epoch (id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL)")
            db.execute("INSERT OR IGNORE INTO epoch(id,value) VALUES (1,0)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def allocate(self):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("UPDATE epoch SET value=value+1 WHERE id=1")
                value = db.execute("SELECT value FROM epoch WHERE id=1").fetchone()[0]
                db.execute("COMMIT")
                return value
            except BaseException:
                db.execute("ROLLBACK")
                raise
