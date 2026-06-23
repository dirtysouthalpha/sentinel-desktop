"""Sentinel Desktop v11.0 — Semantic Memory.

Stores key-value knowledge facts that the agent has learned.
Unlike episodic memory (raw interaction logs), semantic memory
stores distilled knowledge: facts, procedures, preferences.

Examples:
- "SonicWall at 192.168.1.1 uses admin/admin default credentials"
- "Client ABC's VPN server is at vpn.abc.com"
- "Preferred browser: Firefox for firewall UIs"

Storage is SQLite for fast querying. No vector DB dependency.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.utils import restrict_file_perms

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("memory/semantic.db")


class SemanticMemory:
    """Key-value knowledge store backed by SQLite.

    Usage::

        mem = SemanticMemory()
        mem.store("firewall_default_creds", "SonicWall default: admin/password",
                  category="credentials", tags=["sonicwall", "default"])
        result = mem.query("SonicWall")
        facts = mem.recall_category("credentials")
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        restrict_file_perms(self._path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    access_count INTEGER DEFAULT 0,
                    source TEXT DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_key ON facts(key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON facts(category)")

    def store(
        self,
        key: str,
        value: str,
        category: str = "",
        tags: list[str] | None = None,
        source: str = "",
    ) -> int:
        """Store a fact. Returns the fact ID."""
        now = datetime.utcnow().isoformat()
        tags_json = json.dumps(tags or [])

        with self._connect() as conn:
            # Check if key already exists
            existing = conn.execute("SELECT id FROM facts WHERE key = ?", (key,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE facts "
                    "SET value=?, category=?, tags=?, updated_at=?, source=? "
                    "WHERE key=?",
                    (value, category, tags_json, now, source, key),
                )
                return existing[0]

            cursor = conn.execute(
                "INSERT INTO facts "
                "(key, value, category, tags, created_at, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (key, value, category, tags_json, now, source),
            )
            return cursor.lastrowid  # type: ignore

    def recall(self, key: str) -> dict[str, Any] | None:
        """Recall a fact by exact key."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM facts WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            # Increment access count
            conn.execute(
                "UPDATE facts SET access_count = access_count + 1 WHERE key = ?",
                (key,),
            )
            return self._row_to_dict(row)

    def query(self, search: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search facts by keyword in key, value, or tags."""
        pattern = f"%{search}%"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM facts "
                "WHERE key LIKE ? OR value LIKE ? OR tags LIKE ? "
                "ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                (pattern, pattern, pattern, limit),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def recall_category(self, category: str) -> list[dict[str, Any]]:
        """Get all facts in a category."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE category = ? ORDER BY created_at DESC",
                (category,),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def delete(self, key: str) -> bool:
        """Delete a fact by key."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM facts WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def list_keys(self, category: str = "") -> list[str]:
        """List all fact keys, optionally filtered by category."""
        with self._connect() as conn:
            if category:
                rows = conn.execute(
                    "SELECT key FROM facts WHERE category = ? ORDER BY key",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT key FROM facts ORDER BY key").fetchall()
            return [row[0] for row in rows]

    def count(self) -> int:
        """Count total facts."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "key": row["key"],
            "value": row["value"],
            "category": row["category"],
            "tags": json.loads(row["tags"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "access_count": row["access_count"],
            "source": row["source"],
        }
