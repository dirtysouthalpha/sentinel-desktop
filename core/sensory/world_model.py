"""World model — the persistent sensory memory.

Combines long-term memory (LongTermMemory) with current sensory state
to give the AI a full picture: what happened + what's happening now.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class WorldModel:
    """Maintains a persistent model of the machine's world."""

    def __init__(self, memory: Any = None) -> None:
        self._memory = memory

    def record_observation(self, category: str, observation: str) -> None:
        """Store a significant observation in long-term memory."""
        if self._memory is not None:
            try:
                key = f"obs:{category}:{int(time.time())}"
                self._memory.store(key, observation, category="observations")
            except Exception as exc:
                logger.debug("Failed to record observation: %s", exc)

    def record_episode(self, event_type: str, details: str) -> None:
        """Record a notable episode (something worth remembering)."""
        if self._memory is not None:
            try:
                import json
                key = f"episode:{event_type}:{int(time.time())}"
                value = json.dumps({
                    "type": event_type,
                    "details": details,
                    "timestamp": time.time(),
                })
                self._memory.store(key, value, category="episodes")
            except Exception as exc:
                logger.debug("Failed to record episode: %s", exc)

    def query_memory(self, query: str, limit: int = 20) -> list[Any]:
        """Query relevant memories."""
        if self._memory is None:
            return []
        try:
            if hasattr(self._memory, 'search'):
                return self._memory.search(category="", limit=limit)
        except Exception:
            pass
        return []

    def get_full_context(self, sensory_state: Any = None) -> str:
        """Build a full context string for LLM reasoning."""
        lines = []
        if sensory_state:
            lines.append(f"Current State: {getattr(sensory_state, 'summary', 'unknown')}")
        recent = self.query_memory("", limit=10)
        if recent:
            lines.append("Recent Memories:")
            for entry in recent[-5:]:
                if hasattr(entry, 'value'):
                    lines.append(f"  - {entry.value}")
        return "\n".join(lines)


__all__ = ["WorldModel"]
