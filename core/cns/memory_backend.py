"""CNS Memory Backend — read/write to the Neuralis brain.

The memory backend provides a pluggable interface for the CNS to persist
and retrieve knowledge. Two implementations are provided:

  - NeuralisBackend — hits the Neuralis brain REST API
  - InMemoryBackend — dict-based fallback for testing/offline use

If the Neuralis brain is unreachable, the NeuralisBackend degrades
gracefully to an InMemoryBackend so the agent loop can continue.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class MemoryBackend(ABC):
    """Abstract interface for CNS memory backends.

    Implementations must provide remember/recall/search so the agent
    loop can persist and retrieve knowledge across iterations.
    """

    @abstractmethod
    def remember(self, key: str, value: Any) -> bool:
        """Store a value under the given key.

        Args:
            key: The storage key.
            value: The value to store (must be JSON-serializable).

        Returns:
            True if the store succeeded.
        """
        ...

    @abstractmethod
    def recall(self, key: str) -> Any | None:
        """Retrieve a value by key.

        Args:
            key: The storage key.

        Returns:
            The stored value, or None if not found.
        """
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search for entries matching a query.

        Args:
            query: The search string.
            limit: Maximum number of results.

        Returns:
            A list of matching entries (dicts with at least 'key').
        """
        ...


class InMemoryBackend(MemoryBackend):
    """Dict-based memory backend for testing and offline use.

    All data lives in memory and is lost when the process exits.
    Search performs simple substring matching on stored keys and values.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def remember(self, key: str, value: Any) -> bool:
        """Store a value in the in-memory dict."""
        self._store[key] = value
        return True

    def recall(self, key: str) -> Any | None:
        """Retrieve a value from the in-memory dict."""
        return self._store.get(key)

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search stored entries by substring match on key or value."""
        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        for k, v in self._store.items():
            if query_lower in k.lower() or query_lower in str(v).lower():
                results.append({"key": k, "value": v})
                if len(results) >= limit:
                    break
        return results

    def clear(self) -> None:
        """Clear all stored entries."""
        self._store.clear()

    def __len__(self) -> int:
        """Number of stored entries."""
        return len(self._store)


class NeuralisBackend(MemoryBackend):
    """Memory backend that hits the Neuralis brain REST API.

    Communicates with the brain at a configurable base URL. If the
    brain is unreachable, operations degrade gracefully to an
    InMemoryBackend so the agent can continue operating.

    The brain exposes:
      POST /memory/remember  {key, value}
      GET  /memory/recall?key=...
      GET  /neurons/search?q=...&limit=...
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        api_key: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._fallback = InMemoryBackend()
        self._online: bool | None = None  # None = unknown

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Make an HTTP request to the brain API.

        Returns the parsed JSON response, or None on failure.
        """
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.debug("Neuralis backend request failed: %s", e)
            return None

    @property
    def is_online(self) -> bool:
        """True if the brain was reachable on the last check.

        Lazily checks connectivity on first access.
        """
        if self._online is None:
            self._check_connectivity()
        return self._online is True

    def _check_connectivity(self) -> None:
        """Ping the brain to determine if it is reachable."""
        resp = self._request("GET", "/health")
        self._online = resp is not None
        if not self._online:
            logger.info("Neuralis brain unreachable — using in-memory fallback")

    def remember(self, key: str, value: Any) -> bool:
        """Store a value in the brain's memory.

        Falls back to in-memory if the brain is unreachable.
        """
        resp = self._request(
            "POST", "/memory/remember", body={"key": key, "value": value}
        )
        if resp is not None:
            self._online = True
            # Also cache locally for fast recall.
            self._fallback.remember(key, value)
            return True
        # Degraded mode: use fallback.
        self._online = False
        return self._fallback.remember(key, value)

    def recall(self, key: str) -> Any | None:
        """Retrieve a value from the brain's memory.

        Falls back to in-memory if the brain is unreachable.
        """
        resp = self._request("GET", "/memory/recall", query={"key": key})
        if resp is not None:
            self._online = True
            return resp.get("value", resp.get("data"))
        # Degraded mode: use fallback.
        self._online = False
        return self._fallback.recall(key)

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search the brain's neurons for matching entries.

        Falls back to in-memory search if the brain is unreachable.
        """
        resp = self._request(
            "GET", "/neurons/search", query={"q": query, "limit": str(limit)}
        )
        if resp is not None:
            self._online = True
            # Normalize response: brain returns {"results": [...]} or a list.
            if isinstance(resp, dict):
                results = resp.get("results", resp.get("neurons", []))
            elif isinstance(resp, list):
                results = resp
            else:
                results = []
            return [
                {"key": r.get("id", r.get("key", "")), "value": r}
                for r in results
            ]
        # Degraded mode: use fallback.
        self._online = False
        return self._fallback.search(query, limit=limit)
