"""Persistent memory for Sentinel Prime — local SQLite (FTS5) store.

Survives restarts so the agent remembers facts and past exchanges across
sessions. Self-contained and dependency-free; can later mirror to Supermemory.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Writable by both SYSTEM and Administrator (the two launch contexts).
DB_PATH = os.path.join(os.environ.get("SENTINEL_MEMORY_DIR", r"C:\SentinelDesktop"), "sentinel_memory.db")
_lock = threading.Lock()
_fts_ok = True


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.execute("CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, text TEXT)")
    global _fts_ok
    if _fts_ok:
        try:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(text, content='memories', content_rowid='id')")
        except sqlite3.OperationalError:
            _fts_ok = False
    return c


def store(text: str, kind: str = "note") -> None:
    text = (text or "").strip()
    if not text:
        return
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with _lock, _conn() as c:
            cur = c.execute("INSERT INTO memories (ts, kind, text) VALUES (?,?,?)", (ts, kind, text))
            if _fts_ok:
                c.execute("INSERT INTO mem_fts (rowid, text) VALUES (?, ?)", (cur.lastrowid, text))
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory.store failed: %s", exc)


def _fts_query(q: str) -> str:
    words = re.findall(r"[A-Za-z0-9_]{3,}", q or "")
    return " OR ".join(words[:12]) if words else ""


def recall(query: str, k: int = 6) -> list[str]:
    """Return up to k relevant memories (FTS match) plus a couple of recent ones."""
    out: list[str] = []
    try:
        with _lock, _conn() as c:
            seen: set[str] = set()
            if _fts_ok:
                fq = _fts_query(query)
                if fq:
                    try:
                        for (t,) in c.execute(
                            "SELECT text FROM mem_fts WHERE mem_fts MATCH ? ORDER BY rank LIMIT ?", (fq, k)
                        ):
                            if t not in seen:
                                seen.add(t); out.append(t)
                    except sqlite3.OperationalError:
                        pass
            if not out:  # fallback keyword LIKE
                for w in re.findall(r"[A-Za-z0-9_]{3,}", query or "")[:5]:
                    for (t,) in c.execute(
                        "SELECT text FROM memories WHERE text LIKE ? ORDER BY id DESC LIMIT ?", (f"%{w}%", k)
                    ):
                        if t not in seen:
                            seen.add(t); out.append(t)
                    if len(out) >= k:
                        break
            # always include the 2 most recent for continuity
            for (t,) in c.execute("SELECT text FROM memories ORDER BY id DESC LIMIT 2"):
                if t not in seen:
                    seen.add(t); out.append(t)
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory.recall failed: %s", exc)
    return out[: k + 2]


def stats() -> dict:
    try:
        with _lock, _conn() as c:
            n = c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        return {"count": n, "db": DB_PATH}
    except Exception as exc:  # noqa: BLE001
        return {"count": 0, "error": str(exc)}
