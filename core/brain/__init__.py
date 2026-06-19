"""Sentinel Desktop v18.0 — Neuralis Brain bridge.

Direct HTTP client to the Neuralis Brain API (shared fleet memory at homeserver:8000).
Mirrors the shape of core/netops/. Degrades gracefully when the brain is unreachable.

Usage::

    from core import brain

    if brain.is_available():
        brain.think("fortigate fix", "rebooted cluster to resolve HA split-brain")
        results = brain.recall("fortigate ha failover")
"""

from core.brain.client import (
    BrainClient,
    BrainError,
    BrainUnavailableError,
    fire,
    get_default_client,
    is_available,
    recall,
    search,
    stats,
    think,
)

__all__ = [
    "BrainClient",
    "BrainError",
    "BrainUnavailableError",
    "fire",
    "get_default_client",
    "is_available",
    "recall",
    "search",
    "stats",
    "think",
]
