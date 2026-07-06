"""
Sentinel Desktop v29.0.0 - Telemetry & Analytics.

Opt-in metrics collection for agent runs, actions, and performance.
Data is stored in SQLite for historical analysis.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_LOCK = threading.Lock()


def _utcnow() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class TelemetryCollector:
    """Collects and queries agent telemetry data via SQLite."""

    def __init__(self, db_path: Path | None = None, enabled: bool = False) -> None:
        self.enabled = enabled
        if db_path is None:
            db_path = Path.home() / ".sentinel-desktop" / "telemetry.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they do not exist."""
        with _DB_LOCK:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        started_at TEXT NOT NULL,
                        finished_at TEXT,
                        goal TEXT,
                        steps INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'running',
                        tenant TEXT,
                        model TEXT
                    );

                    CREATE TABLE IF NOT EXISTS actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id INTEGER REFERENCES runs(id),
                        step INTEGER,
                        action_type TEXT,
                        success INTEGER,
                        latency_ms REAL,
                        timestamp TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS llm_calls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id INTEGER REFERENCES runs(id),
                        provider TEXT,
                        model TEXT,
                        input_tokens INTEGER,
                        output_tokens INTEGER,
                        latency_ms REAL,
                        timestamp TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
                    CREATE INDEX IF NOT EXISTS idx_actions_run ON actions(run_id);
                    CREATE INDEX IF NOT EXISTS idx_llm_run ON llm_calls(run_id);
                    """
                )
                conn.commit()
            finally:
                conn.close()
        logger.info("Telemetry DB initialized at %s", self.db_path)

    def start_run(self, goal: str, tenant: str = "", model: str = "") -> int:
        """Record the start of an agent run. Returns run_id."""
        if not self.enabled:
            return 0
        with _DB_LOCK:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute(
                    "INSERT INTO runs (started_at, goal, status, tenant, model) VALUES (?, ?, ?, ?, ?)",
                    (_utcnow(), goal[:500], "running", tenant, model),
                )
                conn.commit()
                return cur.lastrowid or 0
            finally:
                conn.close()

    def finish_run(self, run_id: int, steps: int, status: str = "completed") -> None:
        """Record completion of an agent run."""
        if not self.enabled or not run_id:
            return
        with _DB_LOCK:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute(
                    "UPDATE runs SET finished_at = ?, steps = ?, status = ? WHERE id = ?",
                    (_utcnow(), steps, status, run_id),
                )
                conn.commit()
            finally:
                conn.close()

    def record_action(self, run_id: int, step: int, action_type: str, success: bool, latency_ms: float) -> None:
        """Record a single action execution."""
        if not self.enabled:
            return
        with _DB_LOCK:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute(
                    "INSERT INTO actions (run_id, step, action_type, success, latency_ms, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, step, action_type[:100], int(success), latency_ms, _utcnow()),
                )
                conn.commit()
            finally:
                conn.close()

    def record_llm_call(self, run_id: int, provider: str, model: str, input_tokens: int, output_tokens: int, latency_ms: float) -> None:
        """Record an LLM API call."""
        if not self.enabled:
            return
        with _DB_LOCK:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute(
                    "INSERT INTO llm_calls (run_id, provider, model, input_tokens, output_tokens, latency_ms, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (run_id, provider[:50], model[:100], input_tokens, output_tokens, latency_ms, _utcnow()),
                )
                conn.commit()
            finally:
                conn.close()

    def get_summary(self, days: int = 30) -> dict[str, Any]:
        """Return aggregated telemetry summary for the last N days."""
        with _DB_LOCK:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            try:
                cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

                total_runs = conn.execute("SELECT COUNT(*) as c FROM runs").fetchone()["c"]
                completed = conn.execute("SELECT COUNT(*) as c FROM runs WHERE status = 'completed'").fetchone()["c"]
                failed = conn.execute("SELECT COUNT(*) as c FROM runs WHERE status = 'failed'").fetchone()["c"]

                avg_steps_row = conn.execute("SELECT AVG(steps) as a FROM runs WHERE steps > 0").fetchone()
                avg_steps = round(avg_steps_row["a"], 1) if avg_steps_row["a"] else 0

                total_actions = conn.execute("SELECT COUNT(*) as c FROM actions").fetchone()["c"]
                success_actions = conn.execute("SELECT COUNT(*) as c FROM actions WHERE success = 1").fetchone()["c"]

                avg_latency_row = conn.execute("SELECT AVG(latency_ms) as a FROM actions").fetchone()
                avg_latency = round(avg_latency_row["a"], 1) if avg_latency_row["a"] else 0

                # Action type distribution
                action_types: dict[str, int] = {}
                for row in conn.execute("SELECT action_type, COUNT(*) as c FROM actions GROUP BY action_type ORDER BY c DESC LIMIT 20"):
                    action_types[row["action_type"]] = row["c"]

                # Total LLM tokens
                tokens_row = conn.execute("SELECT COALESCE(SUM(input_tokens), 0) as i, COALESCE(SUM(output_tokens), 0) as o FROM llm_calls").fetchone()

                return {
                    "period_days": days,
                    "runs": {"total": total_runs, "completed": completed, "failed": failed},
                    "avg_steps": avg_steps,
                    "actions": {"total": total_actions, "successful": success_actions, "success_rate": round(success_actions / total_actions * 100, 1) if total_actions else 0},
                    "avg_action_latency_ms": avg_latency,
                    "top_action_types": action_types,
                    "llm_tokens": {"input": tokens_row["i"], "output": tokens_row["o"]},
                }
            finally:
                conn.close()

    def get_recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent agent runs."""
        with _DB_LOCK:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()


# Singleton instance
_collector: TelemetryCollector | None = None


def get_collector(enabled: bool = False) -> TelemetryCollector:
    """Get or create the singleton telemetry collector."""
    global _collector
    if _collector is None:
        _collector = TelemetryCollector(enabled=enabled)
    return _collector
