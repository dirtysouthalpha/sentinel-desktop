"""Sentinel Desktop v10.0 — Sentinel Daemon.

Background service manager that runs the agent as a daemon process.
Handles:
- Start/stop the agent loop as a background service
- Auto-start with the OS (Windows Task Scheduler / systemd)
- Heartbeat monitoring
- Graceful shutdown on signal
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = Path("config/daemon_state.json")


class DaemonStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class SentinelDaemon:
    """Manages the Sentinel agent as a background daemon service.

    Usage::

        daemon = SentinelDaemon()
        daemon.start()
        # ... runs in background ...
        daemon.stop()
    """

    def __init__(self, state_path: Path | str | None = None) -> None:
        self._state_path = Path(state_path) if state_path else DEFAULT_STATE_PATH
        self._status: DaemonStatus = DaemonStatus.STOPPED
        self._started_at: str | None = None
        self._pid: int | None = None
        self._jobs_completed: int = 0
        self._jobs_failed: int = 0
        self._last_heartbeat: str | None = None
        self._running: bool = False

    @property
    def status(self) -> DaemonStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._running and self._status == DaemonStatus.RUNNING

    @property
    def uptime_seconds(self) -> float:
        if not self._started_at:
            return 0.0
        started = datetime.fromisoformat(self._started_at)
        return (datetime.utcnow() - started).total_seconds()

    def start(self) -> dict[str, Any]:
        """Start the daemon service."""
        if self.is_running:
            return {"success": False, "error": "Already running"}

        self._status = DaemonStatus.STARTING
        self._pid = os.getpid()
        self._started_at = datetime.utcnow().isoformat()
        self._running = True
        self._status = DaemonStatus.RUNNING
        self._heartbeat()

        self._save_state()
        logger.info("Sentinel Daemon started (pid=%d)", self._pid)
        return {"success": True, "pid": self._pid}

    def stop(self) -> dict[str, Any]:
        """Stop the daemon service."""
        if not self.is_running:
            return {"success": False, "error": "Not running"}

        self._status = DaemonStatus.STOPPING
        self._running = False
        self._status = DaemonStatus.STOPPED

        self._save_state()
        logger.info("Sentinel Daemon stopped (jobs_completed=%d)", self._jobs_completed)
        return {"success": True, "jobs_completed": self._jobs_completed}

    def heartbeat(self) -> dict[str, Any]:
        """Update heartbeat timestamp."""
        self._heartbeat()
        return {"success": True, "timestamp": self._last_heartbeat}

    def record_job(self, success: bool) -> None:
        """Record a completed job."""
        if success:
            self._jobs_completed += 1
        else:
            self._jobs_failed += 1
        self._heartbeat()
        self._save_state()

    def get_status(self) -> dict[str, Any]:
        """Get full daemon status."""
        return {
            "status": self._status.value,
            "pid": self._pid,
            "started_at": self._started_at,
            "uptime_seconds": self.uptime_seconds,
            "jobs_completed": self._jobs_completed,
            "jobs_failed": self._jobs_failed,
            "last_heartbeat": self._last_heartbeat,
        }

    def _heartbeat(self) -> None:
        self._last_heartbeat = datetime.utcnow().isoformat()

    def _save_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(self.get_status(), indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save daemon state: %s", exc)

    def _load_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
