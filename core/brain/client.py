"""Sentinel Desktop v18.0 — BrainClient: synchronous HTTP client for the Neuralis Brain API.

Connection:
    NEURALIS_BRAIN_URL env var (default http://100.70.240.55:8000).

Confirmed API contract (verified against live homeserver:8000/openapi.json):

    think   POST /neurons/think       body: {content, region?, source?}
    recall  GET  /recall              ?context=<str>
    search  GET  /neurons/search      ?q=<str>
    stats   GET  /brain/stats
    fire    POST /neurons/{id}/fire   path param

Graceful degradation: all ops return {"success": False, "error": "brain_unavailable"}
when the brain is unreachable. Never raises to callers — catch BrainError if you need
finer control.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BRAIN_URL = "http://100.70.240.55:8000"
_DEFAULT_TIMEOUT = 5.0

_default_client: BrainClient | None = None


class BrainError(Exception):
    """Raised on non-2xx responses or malformed JSON from the brain API."""


class BrainUnavailableError(BrainError):
    """Raised when the brain host is unreachable or the request times out."""


class BrainClient:
    """Synchronous HTTP client for the Neuralis Brain API.

    Creates a lazy httpx.Client on first use. The client is intentionally
    synchronous — brain ops are fast single calls and the executor dispatch
    table is sync (matching the _ssh_run / _dns_lookup pattern).
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("NEURALIS_BRAIN_URL", _DEFAULT_BRAIN_URL)
        ).rstrip("/")
        self.timeout = timeout
        self._client: Any = None  # lazy httpx.Client

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self._client

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Central HTTP wrapper. Raises BrainUnavailableError on network failures,
        BrainError on non-2xx responses."""
        import httpx
        try:
            resp = self._get_client().request(method, path, **kwargs)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise BrainUnavailableError(f"Brain unreachable ({self.base_url}): {exc}") from exc
        except Exception as exc:
            raise BrainUnavailableError(f"Brain request failed: {exc}") from exc
        if not resp.is_success:
            raise BrainError(f"Brain API {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except Exception as exc:
            raise BrainError(f"Brain response not JSON: {exc}") from exc

    def think(
        self,
        content: str,
        region: str = "knowledge",
        source: str = "sentinel-desktop",
    ) -> dict[str, Any]:
        """Persist a thought to the fleet brain (POST /neurons/think)."""
        return self._request(
            "POST",
            "/neurons/think",
            json={"content": content, "region": region, "source": source},
        )

    def recall(self, context: str) -> dict[str, Any]:
        """Retrieve thoughts most relevant to a context string (GET /recall)."""
        return self._request("GET", "/recall", params={"context": context})

    def search(self, q: str) -> dict[str, Any]:
        """Free-text search across brain neurons (GET /neurons/search)."""
        return self._request("GET", "/neurons/search", params={"q": q})

    def stats(self) -> dict[str, Any]:
        """Return brain health stats — neuron/synapse counts, regions (GET /brain/stats)."""
        return self._request("GET", "/brain/stats")

    def fire(self, neuron_id: int) -> dict[str, Any]:
        """Fire (reinforce) a neuron by ID (POST /neurons/{id}/fire)."""
        return self._request("POST", f"/neurons/{neuron_id}/fire")

    def is_available(self) -> bool:
        """Quick liveness check. Never raises."""
        try:
            self._request("GET", "/health")
            return True
        except (BrainError, BrainUnavailableError):
            return False

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def get_default_client() -> BrainClient:
    """Return the module-level lazy singleton BrainClient."""
    global _default_client
    if _default_client is None:
        _default_client = BrainClient()
    return _default_client


def think(
    content: str,
    region: str = "knowledge",
    source: str = "sentinel-desktop",
) -> dict[str, Any]:
    """Module-level convenience: persist a thought to the fleet brain."""
    return get_default_client().think(content=content, region=region, source=source)


def recall(context: str) -> dict[str, Any]:
    """Module-level convenience: recall thoughts relevant to context."""
    return get_default_client().recall(context=context)


def search(q: str) -> dict[str, Any]:
    """Module-level convenience: free-text search across the brain."""
    return get_default_client().search(q=q)


def stats() -> dict[str, Any]:
    """Module-level convenience: get brain stats."""
    return get_default_client().stats()


def fire(neuron_id: int) -> dict[str, Any]:
    """Module-level convenience: fire (reinforce) a neuron."""
    return get_default_client().fire(neuron_id=neuron_id)


def is_available() -> bool:
    """Module-level convenience: check if the brain is reachable."""
    return get_default_client().is_available()
