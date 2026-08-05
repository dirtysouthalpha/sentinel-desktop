"""Local SQLite state cache for fleet mesh nodes."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StateCache:
    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, run the caller's work in a transaction, then CLOSE it.

        The close is the whole point. `with sqlite3.connect(...) as conn:` is a
        *transaction* manager (it commits or rolls back), NOT a resource manager —
        it never closes the connection. That left every call here leaking an open
        handle for the GC to reap whenever it felt like it.

        On CPython 3.10 refcounting reaped them at method exit, so nobody noticed.
        From 3.11 on, sqlite3 connections land in reference cycles, so refcounting
        can't free them and they survive until a generational GC pass. On POSIX that
        is merely untidy — an unlinked-but-open file just disappears on last close.
        On Windows an open handle makes the file undeletable, so tearing down a
        tempdir over a still-open cache.db raised WinError 32 and reddened only the
        windows-latest 3.11/3.12 CI legs.

        Closing here rather than in the tests fixes the leak for the daemon too,
        which opens a connection per operation and never reclaimed one on its own.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            # Preserve the previous commit-on-success / rollback-on-error semantics
            # that callers got from `with sqlite3.connect(...)`.
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    bucket TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (bucket, key)
                )
            """)
            conn.commit()

    def put(self, bucket: str, key: str, value: dict[str, Any]) -> None:
        now = time.time()
        blob = json.dumps({"bucket": bucket, "key": key, "value": value, "created_at": now})
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (bucket, key, value, created_at) VALUES (?, ?, ?, ?)",
                (bucket, key, blob, now),
            )
            conn.commit()

    def get(self, bucket: str, key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM cache WHERE bucket = ? AND key = ?", (bucket, key)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0]).get("value")
        except (json.JSONDecodeError, KeyError):
            return None

    def list_bucket(self, bucket: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT value FROM cache WHERE bucket = ?", (bucket,)).fetchall()
        results = []
        for row in rows:
            try:
                data = json.loads(row[0])
                entry = data.get("value", {})
                entry["_key"] = data.get("key", "")
                results.append(entry)
            except (json.JSONDecodeError, KeyError):
                continue
        return results

    def delete(self, bucket: str, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE bucket = ? AND key = ?", (bucket, key))
            conn.commit()

    def prune(self, max_age_seconds: float) -> int:
        cutoff = time.time() - max_age_seconds
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))
            conn.commit()
            return cursor.rowcount
