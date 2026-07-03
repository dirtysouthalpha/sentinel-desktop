"""Long-term memory — persistent across sessions.

Stores: user preferences, learned patterns, automation history,
element locations that were discovered, what worked and what didn't.

Backed by SQLite for persistence and retrieval.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_PATH = Path(os.environ.get("SENTINEL_MEMORY_DB", Path.home() / ".sentinel" / "memory.db"))

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    category TEXT DEFAULT '',
    value TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    score REAL DEFAULT 0.0,
    created_at REAL NOT NULL,
    last_accessed REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
CREATE INDEX IF NOT EXISTS idx_memories_score ON memories(score DESC);
"""


@dataclass
class LongTermEntry:
    """A stored long-term memory."""

    key: str
    value: str
    category: str = ""
    metadata: dict[str, Any] | None = None
    score: float = 0.0
    created_at: float = 0.0
    last_accessed: float = 0.0


class LongTermMemory:
    """Persistent key-value store with scoring for relevance."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        import sqlite3
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.executescript(_INIT_SQL)

    def store(self, key: str, value: str, category: str = "", **meta: Any) -> None:
        import sqlite3
        now = time.time()
        meta_json = json.dumps(meta)
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """INSERT INTO memories (key, category, value, metadata, score, created_at, last_accessed)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value,
                       category=excluded.category,
                       metadata=excluded.metadata,
                       last_accessed=excluded.last_accessed""",
                (key, category, value, meta_json, 0.0, now, now),
            )

    def recall(self, key: str) -> str | None:
        import sqlite3
        with sqlite3.connect(str(self._db_path)) as conn:
            cursor = conn.execute(
                "SELECT value FROM memories WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            if row:
                # Update last_accessed
                conn.execute(
                    "UPDATE memories SET last_accessed = ? WHERE key = ?",
                    (time.time(), key),
                )
                conn.execute(
                    "UPDATE memories SET score = score + 1 WHERE key = ?",
                    (key,),
                )
                return row[0]
        return None

    def search(self, category: str = "", limit: int = 20, min_score: float = -1.0) -> list[LongTermEntry]:
        """Search memories by category, ordered by score."""
        import sqlite3
        query = "SELECT key, category, value, metadata, score, created_at, last_accessed FROM memories"
        params: list[Any] = []
        conditions = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if min_score >= 0:
            conditions.append("score >= ?")
            params.append(min_score)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY score DESC, last_accessed DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(str(self._db_path)) as conn:
            cursor = conn.execute(query, params)
            results = []
            for row in cursor.fetchall():
                results.append(LongTermEntry(
                    key=row[0], category=row[1], value=row[2],
                    metadata=json.loads(row[3]) if row[3] else {},
                    score=row[4], created_at=row[5], last_accessed=row[6],
                ))
            return results

    def forget(self, key: str) -> bool:
        import sqlite3
        with sqlite3.connect(str(self._db_path)) as conn:
            cursor = conn.execute("DELETE FROM memories WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def remember_workflow_result(self, name: str, success: bool, duration: float) -> None:
        """Record whether a workflow succeeded."""
        key = f"workflow:{name}"
        value = json.dumps({"success": success, "duration": duration, "timestamp": time.time()})
        self.store(key, value, category="workflows")

    def get_preferred_locations(self) -> dict[str, list[dict]]:
        """Retrieve stored element locations (from vision grounding)."""
        entries = self.search(category="element_locations")
        result = {}
        for e in entries:
            result[e.key] = json.loads(e.value)
        return result

    def store_element_location(self, description: str, x: int, y: int, w: int, h: int) -> None:
        """Remember where an element was found."""
        key = f"element:{description}"
        value = json.dumps({"x": x, "y": y, "width": w, "height": h})
        self.store(key, value, category="element_locations")

    def clear_all(self) -> None:
        import sqlite3
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("DELETE FROM memories")


__all__ = ["LongTermEntry", "LongTermMemory"]
