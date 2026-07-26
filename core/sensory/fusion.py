"""Sensory fusion engine — combines all sensory streams into a unified world model.

Takes input from ScreenAgent, ProcessAgent, and NetworkAgent and maintains
a single coherent picture of the current state of the machine.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorldState:
    """A snapshot of everything the system currently knows about itself."""

    timestamp: float
    screen_changed: bool = False
    screen_change_percent: float = 0.0
    process_count: int = 0
    new_processes: list[str] = field(default_factory=list)
    terminated_processes: list[str] = field(default_factory=list)
    cpu_alerts: list[str] = field(default_factory=list)
    memory_alerts: list[str] = field(default_factory=list)
    online_peers: list[str] = field(default_factory=list)
    offline_peers: list[str] = field(default_factory=list)
    services: dict[str, str] = field(default_factory=dict)  # hostname:port
    summary: str = ""


class SensoryFusion:
    """Combines screen, process, and network data into a world state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = WorldState(timestamp=time.time())
        self._screen_events: list[Any] = []
        self._process_events: list[Any] = []
        self._network_events: list[Any] = []

    # -- ingest ------------------------------------------------------------

    def ingest_screen(self, event: Any) -> None:
        with self._lock:
            self._screen_events.append(event)
            self._state.screen_changed = event.changed
            self._state.screen_change_percent = event.change_percent

    def ingest_process(self, event: Any) -> None:
        with self._lock:
            self._process_events.append(event)
            if event.event_type == "new":
                self._state.new_processes.append(f"{event.name} (PID {event.pid})")
            elif event.event_type == "terminated":
                self._state.terminated_processes.append(f"{event.name} (PID {event.pid})")
            elif event.event_type == "high_cpu":
                self._state.cpu_alerts.append(f"{event.name}: {event.details}")
            elif event.event_type == "high_memory":
                self._state.memory_alerts.append(f"{event.name}: {event.details}")

    def ingest_network(self, event: Any) -> None:
        with self._lock:
            self._network_events.append(event)
            if event.event_type == "peer_online":
                self._state.online_peers.append(event.hostname)
            elif event.event_type == "peer_offline":
                self._state.offline_peers.append(event.hostname)
            elif event.event_type == "service_up":
                self._state.services[event.hostname] = event.details

    # -- queries -----------------------------------------------------------

    def get_world_state(self) -> WorldState:
        with self._lock:
            return WorldState(
                timestamp=time.time(),
                screen_changed=self._state.screen_changed,
                screen_change_percent=self._state.screen_change_percent,
                process_count=len(self._process_events),
                new_processes=list(self._state.new_processes[-20:]),
                terminated_processes=list(self._state.terminated_processes[-20:]),
                cpu_alerts=list(self._state.cpu_alerts[-10:]),
                memory_alerts=list(self._state.memory_alerts[-10:]),
                online_peers=list(self._state.online_peers[-20:]),
                offline_peers=list(self._state.offline_peers[-20:]),
                services=dict(self._state.services),
                summary=self._build_summary(),
            )

    def get_recent_events(self, limit: int = 50) -> dict[str, list[Any]]:
        with self._lock:
            return {
                "screen": self._screen_events[-limit:],
                "process": self._process_events[-limit:],
                "network": self._network_events[-limit:],
            }

    def _build_summary(self) -> str:
        parts = []
        if self._state.screen_changed:
            parts.append(f"screen changed {self._state.screen_change_percent:.1%}")
        if self._state.new_processes:
            parts.append(f"{len(self._state.new_processes)} new processes")
        if self._state.terminated_processes:
            parts.append(f"{len(self._state.terminated_processes)} terminated processes")
        if self._state.cpu_alerts:
            parts.append(f"{len(self._state.cpu_alerts)} CPU alerts")
        if self._state.memory_alerts:
            parts.append(f"{len(self._state.memory_alerts)} memory alerts")
        if self._state.online_peers:
            parts.append(f"{len(self._state.online_peers)} peers online")
        if self._state.offline_peers:
            parts.append(f"{len(self._state.offline_peers)} peers offline",)
        if self._state.services:
            parts.append(f"{len(self._state.services)} services discovered")
        return "; ".join(parts) if parts else "no recent events"

    def clear(self) -> None:
        with self._lock:
            self._screen_events.clear()
            self._process_events.clear()
            self._network_events.clear()
            self._state = WorldState(timestamp=time.time())


__all__ = ["WorldState", "SensoryFusion"]
