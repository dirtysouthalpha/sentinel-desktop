"""Local SQLite state cache for fleet mesh nodes."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StateCache:
    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

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
