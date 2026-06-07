"""Sentinel Desktop v11.0 — Working Memory.

In-memory scratchpad for the current session. Stores temporary context:
current task, active windows, recent observations, user preferences.

Working memory is NOT persisted between sessions. It resets on restart.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maximum items per bucket to prevent unbounded growth.
MAX_BUCKET_SIZE = 100


class WorkingMemory:
    """In-memory session scratchpad.

    Usage::

        wm = WorkingMemory()
        wm.set("current_task", "Login to SonicWall")
        wm.set("active_window", "Chrome")
        task = wm.get("current_task")
        wm.push("recent_urls", "https://192.168.1.1")
        urls = wm.get("recent_urls")
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._buckets: dict[str, list[Any]] = {}

    def set(self, key: str, value: Any) -> None:
        """Set a key-value pair."""
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key."""
        return self._store.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a key exists."""
        return key in self._store

    def delete(self, key: str) -> bool:
        """Delete a key."""
        if key in self._store:
            del self._store[key]
            return True
        return False

    def push(self, bucket: str, item: Any) -> None:
        """Append an item to a list bucket (auto-trims to MAX_BUCKET_SIZE)."""
        if bucket not in self._buckets:
            self._buckets[bucket] = []
        self._buckets[bucket].append(item)
        # Trim oldest items if bucket is too large
        if len(self._buckets[bucket]) > MAX_BUCKET_SIZE:
            self._buckets[bucket] = self._buckets[bucket][-MAX_BUCKET_SIZE:]

    def get_bucket(self, bucket: str, limit: int = 20) -> list[Any]:
        """Get recent items from a bucket (most recent last)."""
        items = self._buckets.get(bucket, [])
        return items[-limit:]

    def clear_bucket(self, bucket: str) -> None:
        """Clear all items from a bucket."""
        self._buckets.pop(bucket, None)

    def snapshot(self) -> dict[str, Any]:
        """Get a snapshot of all working memory."""
        return {
            "store": dict(self._store),
            "buckets": {k: list(v) for k, v in self._buckets.items()},
        }

    def clear(self) -> None:
        """Clear all working memory."""
        self._store.clear()
        self._buckets.clear()

    def count(self) -> int:
        """Count total items (keys + bucket items)."""
        return len(self._store) + sum(len(v) for v in self._buckets.values())

    def keys(self) -> list[str]:
        """List all store keys."""
        return list(self._store.keys())

    def bucket_names(self) -> list[str]:
        """List all bucket names."""
        return list(self._buckets.keys())
