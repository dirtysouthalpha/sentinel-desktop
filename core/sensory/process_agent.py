"""Process sensory agent — watches running processes.

Monitors the system process list at intervals, detects new processes,
terminated processes, and processes that may be consuming excessive resources.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProcessEvent:
    """Emitted when a process change is detected."""

    timestamp: float
    event_type: str  # "new", "terminated", "high_cpu", "high_memory"
    pid: int
    name: str
    details: str = ""


@dataclass
class ProcessConfig:
    """Configuration for the process agent."""

    check_interval_seconds: float = 10.0
    cpu_alert_threshold: float = 80.0  # percent
    memory_alert_threshold_mb: float = 1024.0  # MB
    enabled: bool = True


class ProcessAgent:
    """Continuously monitors system processes."""

    def __init__(self, config: ProcessConfig | None = None) -> None:
        self._config = config or ProcessConfig()
        self._running = False
        self._thread: threading.Thread | None = None
        self._known: dict[int, dict[str, Any]] = {}
        self._callbacks: list[Callable[[ProcessEvent], None]] = []

    def on_change(self, callback: Callable[[ProcessEvent], None]) -> None:
        """Register a callback for process events."""
        self._callbacks.append(callback)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="sensory-process")
        self._thread.start()
        logger.info("Process agent started (interval=%ss)", self._config.check_interval_seconds)

    def stop(self) -> None:
        self._running = False

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._check_processes()
            except Exception as exc:
                logger.debug("Process check failed: %s", exc)
            time.sleep(self._config.check_interval_seconds)

    def _check_processes(self) -> None:
        try:
            import psutil
        except ImportError:
            return

        current: dict[int, dict[str, Any]] = {}
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                info = p.info
                pid = info.get("pid", 0)
                current[pid] = info
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Detect new processes
        for pid, info in current.items():
            if pid not in self._known:
                self._emit(ProcessEvent(
                    timestamp=time.time(),
                    event_type="new",
                    pid=pid,
                    name=info.get("name", "unknown"),
                    details=f"PID {pid} started",
                ))
            else:
                # Check resource thresholds
                cpu = info.get("cpu_percent", 0.0) or 0.0
                if cpu > self._config.cpu_alert_threshold:
                    self._emit(ProcessEvent(
                        timestamp=time.time(),
                        event_type="high_cpu",
                        pid=pid,
                        name=info.get("name", "unknown"),
                        details=f"CPU: {cpu:.1f}%",
                    ))
                mem_info = info.get("memory_info")
                if mem_info:
                    mem_mb = mem_info.rss / 1024 / 1024
                    if mem_mb > self._config.memory_alert_threshold_mb:
                        self._emit(ProcessEvent(
                            timestamp=time.time(),
                            event_type="high_memory",
                            pid=pid,
                            name=info.get("name", "unknown"),
                            details=f"Memory: {mem_mb:.0f}MB",
                        ))

        # Detect terminated processes
        for pid, info in self._known.items():
            if pid not in current:
                self._emit(ProcessEvent(
                    timestamp=time.time(),
                    event_type="terminated",
                    pid=pid,
                    name=info.get("name", "unknown"),
                    details=f"PID {pid} exited",
                ))

        self._known = current

    def _emit(self, event: ProcessEvent) -> None:
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as exc:
                logger.error("Process callback failed: %s", exc)

    @property
    def is_running(self) -> bool:
        return self._running

    def get_known_processes(self) -> dict[int, dict[str, Any]]:
        return dict(self._known)


__all__ = ["ProcessEvent", "ProcessConfig", "ProcessAgent"]
