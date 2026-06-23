"""Sentinel Desktop v22.0 — Event triggers.

Fire executor actions on spoken keywords, file changes, process events,
or custom named signals.

Usage::

    from core.triggers import EventType, Trigger, TriggerRegistry, TriggerEngine

    registry = TriggerRegistry()
    t = Trigger(
        name="alert_on_sentinel",
        event_type=EventType.SPOKEN_KEYWORD,
        condition={"keyword": "sentinel"},
        action={"action": "speak", "text": "Yes?"},
    )
    registry.add(t)

    engine = TriggerEngine(registry, executor_fn=my_executor.execute)
    engine.start()
    engine.fire_custom("my_event")
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core.utils import restrict_file_perms

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    SPOKEN_KEYWORD = "spoken_keyword"
    FILE_CHANGE = "file_change"
    PROCESS_START = "process_start"
    PROCESS_STOP = "process_stop"
    SCHEDULE = "schedule"
    CUSTOM = "custom"


@dataclass
class Trigger:
    """A named rule that maps an event condition to an executor action payload."""

    name: str
    event_type: EventType
    condition: dict[str, Any]
    action: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    enabled: bool = True
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "event_type": self.event_type.value,
            "condition": self.condition,
            "action": self.action,
            "enabled": self.enabled,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trigger:
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data["name"],
            event_type=EventType(data["event_type"]),
            condition=data.get("condition", {}),
            action=data.get("action", {}),
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
        )


class TriggerRegistry:
    """Persistent store of Trigger definitions (JSON file in ~/.sentinel/triggers/)."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._dir = storage_dir or (Path.home() / ".sentinel" / "triggers")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "triggers.json"
        self._triggers: dict[str, Trigger] = {}
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            return
        # Trigger actions carry executor payloads that may include credentials
        # for automated flows; heal perms on legacy world-readable files.
        restrict_file_perms(self._file)
        try:
            data = json.loads(self._file.read_text())
            for item in data:
                t = Trigger.from_dict(item)
                self._triggers[t.id] = t
        except Exception as exc:
            logger.warning("TriggerRegistry load failed: %s", exc)

    def _save(self) -> None:
        try:
            self._file.write_text(
                json.dumps([t.to_dict() for t in self._triggers.values()], indent=2)
            )
            restrict_file_perms(self._file)
        except Exception as exc:
            logger.warning("TriggerRegistry save failed: %s", exc)

    def add(self, trigger: Trigger) -> Trigger:
        """Register a new trigger, persisting it to disk."""
        self._triggers[trigger.id] = trigger
        self._save()
        return trigger

    def remove(self, trigger_id: str) -> bool:
        """Delete trigger by ID. Returns True if found and removed."""
        if trigger_id not in self._triggers:
            return False
        del self._triggers[trigger_id]
        self._save()
        return True

    def get(self, trigger_id: str) -> Trigger | None:
        return self._triggers.get(trigger_id)

    def list_all(self) -> list[Trigger]:
        return list(self._triggers.values())

    def enable(self, trigger_id: str) -> bool:
        t = self._triggers.get(trigger_id)
        if t is None:
            return False
        t.enabled = True
        self._save()
        return True

    def disable(self, trigger_id: str) -> bool:
        t = self._triggers.get(trigger_id)
        if t is None:
            return False
        t.enabled = False
        self._save()
        return True

    def find_by_event(self, event_type: EventType) -> list[Trigger]:
        """Return enabled triggers matching a given event type."""
        return [t for t in self._triggers.values() if t.event_type == event_type and t.enabled]


class TriggerEngine:
    """Background engine that evaluates registered triggers and fires their actions.

    Custom events are the primary built-in path: call ``fire_custom(event_name)``
    and any CUSTOM trigger whose condition ``event_name`` matches will have its
    action dispatched via *executor_fn*.
    """

    def __init__(
        self,
        registry: TriggerRegistry,
        executor_fn: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self._registry = registry
        self._executor_fn = executor_fn
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pending_custom: list[str] = []
        self._custom_lock = threading.Lock()
        self._has_events = threading.Event()

    def start(self) -> None:
        """Start the background evaluation loop (idempotent)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="TriggerEngine")
        self._thread.start()
        logger.info("TriggerEngine started")

    def stop(self) -> None:
        """Stop the background loop and join the thread."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("TriggerEngine stopped")

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def fire_custom(self, event_name: str) -> None:
        """Queue a named custom event to be processed on the next engine tick."""
        with self._custom_lock:
            self._pending_custom.append(event_name)
        self._has_events.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._has_events.wait(timeout=0.5)
            self._has_events.clear()
            self._process_custom_events()

    def _process_custom_events(self) -> None:
        with self._custom_lock:
            events = self._pending_custom[:]
            self._pending_custom.clear()
        for event_name in events:
            for trigger in self._registry.find_by_event(EventType.CUSTOM):
                if trigger.condition.get("event_name") == event_name:
                    self._fire(trigger)

    def _fire(self, trigger: Trigger) -> None:
        logger.info("Trigger fired: '%s' (id=%s)", trigger.name, trigger.id)
        if self._executor_fn and trigger.action:
            try:
                self._executor_fn(trigger.action)
            except Exception as exc:
                logger.warning("Trigger '%s' action error: %s", trigger.name, exc)


# Process-wide singleton (lazy-init)
_engine: TriggerEngine | None = None
_registry: TriggerRegistry | None = None


def get_trigger_registry() -> TriggerRegistry:
    global _registry
    if _registry is None:
        _registry = TriggerRegistry()
    return _registry


def get_trigger_engine(
    executor_fn: Callable[[dict[str, Any]], Any] | None = None,
) -> TriggerEngine:
    global _engine
    if _engine is None:
        _engine = TriggerEngine(get_trigger_registry(), executor_fn=executor_fn)
    elif executor_fn is not None and _engine._executor_fn is None:
        _engine._executor_fn = executor_fn
    return _engine
