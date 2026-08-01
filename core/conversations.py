"""Conversation persistence for the Sentinel Command Center.

The dashboard has had a conversation sidebar since v8 — four date groups, a
search box, a delete button per row. None of it was connected: ``loadConvs()``
was ``renderConvs([])`` with a ``// Phase 3:`` comment, ``openConv()`` printed
"Loading conversation…" and stopped, ``delConv()`` toasted success and deleted
nothing, and ``POST /api/conversations`` — which ``sendMsg()`` calls on the
first message of every chat — answered 404.

This is the store behind it. SQLite in WAL mode, two tables, no ORM: the
access pattern is "list by recency" and "read one conversation's messages", and
that does not need one.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_ENV = "SENTINEL_CONVERSATIONS_DB"

#: Titles are derived from the first user message; this bounds that.
TITLE_MAX = 80

#: A single message body. Generous — an agent transcript can be long — but not
#: unbounded, because this is a public POST body.
CONTENT_MAX = 262_144

_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None
_CONN_PATH: str | None = None


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def db_path() -> Path:
    """Where the store lives. Overridable for tests and for a moved data dir."""
    override = os.environ.get(DB_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "conversations.db"


def _connect() -> sqlite3.Connection:
    """Open (or reuse) the connection, applying the schema once.

    Cached on the resolved path so that changing ``SENTINEL_CONVERSATIONS_DB``
    — which only tests do — actually takes effect instead of silently reusing
    the previous database.
    """
    global _CONN, _CONN_PATH
    path = str(db_path())
    if _CONN is not None and _CONN_PATH == path:
        return _CONN

    if _CONN is not None:
        try:
            _CONN.close()
        except sqlite3.Error:
            pass

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL from day one: the API is async and the GUI reads the same file.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL DEFAULT 'Untitled',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL
                            REFERENCES conversations(id) ON DELETE CASCADE,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            created_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conv
            ON messages(conversation_id, id);
        CREATE INDEX IF NOT EXISTS idx_conversations_updated
            ON conversations(updated_at DESC);
        """
    )
    conn.commit()
    _CONN, _CONN_PATH = conn, path
    return conn


def reset_connection() -> None:
    """Drop the cached connection. For tests and for a data-dir change."""
    global _CONN, _CONN_PATH
    with _LOCK:
        if _CONN is not None:
            try:
                _CONN.close()
            except sqlite3.Error:
                pass
        _CONN, _CONN_PATH = None, None


def _derive_title(content: str) -> str:
    first = (content or "").strip().splitlines()[0] if (content or "").strip() else ""
    first = " ".join(first.split())
    if len(first) > TITLE_MAX:
        first = first[: TITLE_MAX - 1].rstrip() + "…"
    return first or "Untitled"


def create(title: str | None = None) -> dict[str, Any]:
    """Create an empty conversation and return it."""
    conv_id = uuid.uuid4().hex
    ts = _now()
    with _LOCK:
        conn = _connect()
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, (title or "Untitled")[:TITLE_MAX], ts, ts),
        )
        conn.commit()
    return {"id": conv_id, "title": title or "Untitled", "created_at": ts, "updated_at": ts, "step_count": 0}


def list_all(limit: int = 200) -> list[dict[str, Any]]:
    """Conversations by recency, each with its message count.

    ``step_count`` is the field name the dashboard's ``renderConvs()`` already
    reads for the "· N steps" meta line.
    """
    limit = max(1, min(int(limit), 1000))
    with _LOCK:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS step_count
            FROM conversations c
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get(conv_id: str) -> dict[str, Any] | None:
    with _LOCK:
        conn = _connect()
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
    return dict(row) if row else None


def delete(conv_id: str) -> bool:
    """Delete a conversation and (via ON DELETE CASCADE) its messages."""
    with _LOCK:
        conn = _connect()
        cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.commit()
    return cur.rowcount > 0


def messages(conv_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 5000))
    with _LOCK:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages WHERE conversation_id = ?
            ORDER BY id ASC LIMIT ?
            """,
            (conv_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def add_message(conv_id: str, role: str, content: str) -> dict[str, Any]:
    """Append a message, bumping the conversation's ``updated_at``.

    The first user message also names the conversation, so the sidebar shows
    something meaningful without a separate titling step.

    Raises:
        KeyError: the conversation does not exist. The caller answers 404 —
        silently creating one here would let a typo'd id fork the history.
    """
    role = (role or "").strip().lower()
    if role not in {"user", "assistant", "system", "error"}:
        raise ValueError(f"unknown role: {role!r}")
    content = (content or "")[:CONTENT_MAX]
    ts = _now()

    with _LOCK:
        conn = _connect()
        exists = conn.execute("SELECT title FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if exists is None:
            raise KeyError(conv_id)

        cur = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conv_id, role, content, ts),
        )
        if role == "user" and (exists["title"] or "Untitled") == "Untitled":
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (_derive_title(content), ts, conv_id),
            )
        else:
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conv_id))
        conn.commit()

    return {"id": cur.lastrowid, "conversation_id": conv_id, "role": role, "content": content, "created_at": ts}


def search(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Full-text-ish search over message bodies.

    The dashboard's ``filterConvs()`` only ever matched titles, so a phrase from
    three days ago was unfindable. LIKE rather than FTS5 deliberately: the
    corpus is one user's chat history, and an FTS table is a migration and an
    index to keep in sync for no measurable gain at this size.
    """
    q = (query or "").strip()
    if not q:
        return []
    limit = max(1, min(int(limit), 500))
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with _LOCK:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.updated_at,
                   (SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id) AS step_count,
                   MAX(m.id) AS hit_message_id,
                   SUBSTR(m.content, 1, 200) AS snippet
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            WHERE m.content LIKE ? ESCAPE '\\' OR c.title LIKE ? ESCAPE '\\'
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
    return [dict(r) for r in rows]
