"""Event-driven automation bus.

React to system events: file changes, schedules, webhooks,
systemd events, window creation, process start/stop.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Event types
EVENT_FILE_CREATED = "file.created"
EVENT_FILE_MODIFIED = "file.modified"
EVENT_FILE_DELETED = "file.deleted"
EVENT_SCHEDULE_FIRED = "schedule.fired"
EVENT_WEBHOOK_RECEIVED = "webhook.received"
EVENT_PROCESS_STARTED = "process.started"
EVENT_PROCESS_STOPPED = "process.stopped"
EVENT_WINDOW_CREATED = "window.created"
EVENT_WINDOW_CLOSED = "window.closed"
EVENT_CUSTOM = "custom"


@dataclass
class Event:
    """A system or custom event."""

    event_type: str
    source: str = ""  # what produced it
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class EventRule:
    """Maps an event pattern to a handler."""

    name: str
    event_type: str  # can be "*" for all
    filter_fn: Callable[[Event], bool] | None = None
    handler: Callable[[Event], None] | None = None
    enabled: bool = True


class EventBus:
    """Publish/subscribe event bus for system events."""

    def __init__(self) -> None:
        self._rules: list[EventRule] = []
        self._lock = threading.Lock()
        self._running = False
        self._poll_thread: threading.Thread | None = None

    def on(
        self,
        event_type: str,
        handler: Callable[[Event], None],
        filter_fn: Callable[[Event], bool] | None = None,
        name: str = "",
    ) -> EventRule:
        """Register a handler for events of the given type."""
        rule = EventRule(
            name=name or f"handler-{len(self._rules)}", event_type=event_type, filter_fn=filter_fn, handler=handler
        )
        with self._lock:
            self._rules.append(rule)
        return rule

    def off(self, rule: EventRule) -> None:
        with self._lock:
            self._rules = [r for r in self._rules if r is not rule]

    def emit(self, event: Event) -> int:
        """Dispatch an event to all matching handlers. Returns count of matched handlers."""
        matched = 0
        with self._lock:
            rules = list(self._rules)
        for rule in rules:
            if not rule.enabled:
                continue
            if rule.event_type != "*" and rule.event_type != event.event_type:
                continue
            if rule.filter_fn and not rule.filter_fn(event):
                continue
            if rule.handler:
                matched += 1
                try:
                    rule.handler(event)
                except Exception as exc:
                    logger.error("Event handler %s failed: %s", rule.name, exc)
        return matched

    def emit_simple(self, event_type: str, **data: Any) -> int:
        """Convenience: emit an event with keyword data."""
        return self.emit(Event(event_type=event_type, data=data))

    # -- file watcher -----------------------------------------------------

    def watch_file(self, path: str, event_type: str = EVENT_FILE_MODIFIED, poll_interval: float = 2.0) -> None:
        """Watch a single file for changes."""
        last_mtime: dict[str, float] = {}

        def _poll() -> None:
            while self._running:
                try:
                    mtime = os.path.getmtime(path)
                    if path in last_mtime and last_mtime[path] != mtime:
                        self.emit(Event(event_type=event_type, source=path, data={"path": path, "mtime": mtime}))
                    last_mtime[path] = mtime
                except FileNotFoundError:
                    if path in last_mtime:
                        self.emit(Event(event_type=EVENT_FILE_DELETED, source=path, data={"path": path}))
                        del last_mtime[path]
                except Exception as exc:
                    logger.debug("file watch poll error: %s", exc)
                time.sleep(poll_interval)

        self._running = True
        t = threading.Thread(target=_poll, daemon=True)
        t.start()

    def watch_dir(
        self, dirpath: str, event_type: str = EVENT_FILE_CREATED, pattern: str = "", poll_interval: float = 3.0
    ) -> None:
        """Watch a directory for new files."""
        seen: set[str] = set()

        def _poll() -> None:
            while self._running:
                try:
                    for fname in os.listdir(dirpath):
                        full = os.path.join(dirpath, fname)
                        if full in seen:
                            continue
                        if pattern and not fname.endswith(pattern):
                            continue
                        seen.add(full)
                        self.emit(Event(event_type=event_type, source=dirpath, data={"path": full, "filename": fname}))
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    logger.debug("dir watch error: %s", exc)
                time.sleep(poll_interval)

        self._running = True
        t = threading.Thread(target=_poll, daemon=True)
        t.start()

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


__all__ = [
    "Event",
    "EventRule",
    "EventBus",
    "EVENT_FILE_CREATED",
    "EVENT_FILE_MODIFIED",
    "EVENT_FILE_DELETED",
    "EVENT_SCHEDULE_FIRED",
    "EVENT_WEBHOOK_RECEIVED",
    "EVENT_PROCESS_STARTED",
    "EVENT_PROCESS_STOPPED",
    "EVENT_WINDOW_CREATED",
    "EVENT_WINDOW_CLOSED",
    "EVENT_CUSTOM",
]
