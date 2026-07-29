"""Conflict resolution and vector clocks for fleet partition handling."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VectorClock:
    clocks: dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str) -> None:
        self.clocks[node_id] = self.clocks.get(node_id, 0) + 1

    def merge(self, other: VectorClock) -> VectorClock:
        merged = {}
        for node in set(self.clocks) | set(other.clocks):
            merged[node] = max(self.clocks.get(node, 0), other.clocks.get(node, 0))
        return VectorClock(merged)

    def compare(self, other: VectorClock) -> int:
        all_nodes = set(self.clocks) | set(other.clocks)
        self_lte = all(self.clocks.get(n, 0) <= other.clocks.get(n, 0) for n in all_nodes)
        other_lte = all(other.clocks.get(n, 0) <= self.clocks.get(n, 0) for n in all_nodes)
        if self_lte and not other_lte:
            return -1
        if other_lte and not self_lte:
            return 1
        return 0


class ConflictResolver:
    def resolve(self, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        clock_a = VectorClock(a.get("clock", {}))
        clock_b = VectorClock(b.get("clock", {}))
        cmp = clock_a.compare(clock_b)
        if cmp == -1:
            return b
        if cmp == 1:
            return a
        # Concurrent: last-writer-wins by timestamp
        if b.get("timestamp", "") > a.get("timestamp", ""):
            return b
        return a
