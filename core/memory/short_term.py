"""Short-term memory for session context.

Stores recent actions, observations, and decisions during an
automation session so the agent can reference what just happened.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A single remembered observation."""

    timestamp: float
    category: str  # action, observation, decision, error, result
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ShortTermMemory:
    """In-memory ring buffer of recent events during a session."""

    def __init__(self, max_entries: int = 200) -> None:
        self._entries: deque[MemoryEntry] = deque(maxlen=max_entries)

    def remember(self, category: str, content: str, **meta: Any) -> None:
        entry = MemoryEntry(
            timestamp=time.time(),
            category=category,
            content=content,
            metadata=meta,
        )
        self._entries.append(entry)

    def recall(self, category: str = "", limit: int = 20) -> list[MemoryEntry]:
        """Retrieve most recent entries, optionally filtered by category."""
        entries = list(self._entries)
        if category:
            entries = [e for e in entries if e.category == category]
        return entries[-limit:]

    def last_action(self) -> MemoryEntry | None:
        for entry in reversed(self._entries):
            if entry.category == "action":
                return entry
        return None

    def last_error(self) -> MemoryEntry | None:
        for entry in reversed(self._entries):
            if entry.category == "error":
                return entry
        return None

    def format_context(self, limit: int = 10) -> str:
        """Format recent memory as context for LLM prompt."""
        entries = list(self._entries)[-limit:]
        lines = []
        for e in entries:
            lines.append(f"[{e.category}] {e.content}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)


__all__ = ["MemoryEntry", "ShortTermMemory"]
