"""Lease-based priority-ordered leader election."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from time import time

from core.mesh.node import MeshNode

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    leader_id: str
    expires_at: float
    priority: int = 0

    def is_valid(self) -> bool:
        return time() < self.expires_at


class LeaderElection:
    def __init__(self, lease_ttl: float = 30.0) -> None:
        self.lease_ttl = lease_ttl
        self._current_lease: Lease | None = None

    def elect_leader(self, nodes: list[MeshNode]) -> MeshNode | None:
        candidates = [n for n in nodes if n.is_leader_candidate and n.is_alive(timeout_seconds=self.lease_ttl)]
        if not candidates:
            if self._current_lease and self._current_lease.is_valid():
                return None
            self._current_lease = None
            return None
        candidates.sort(key=lambda n: n.priority, reverse=True)
        winner = candidates[0]
        if self._current_lease is None or self._current_lease.leader_id != winner.node_id:
            self._current_lease = Lease(leader_id=winner.node_id, expires_at=time() + self.lease_ttl, priority=winner.priority)
            logger.info("New leader elected: %s (priority %d)", winner.node_id, winner.priority)
        return winner

    def renew_lease(self, node_id: str) -> bool:
        if self._current_lease is None or self._current_lease.leader_id != node_id or not self._current_lease.is_valid():
            return False
        self._current_lease.expires_at = time() + self.lease_ttl
        return True

    @property
    def current_leader(self) -> str | None:
        if self._current_lease and self._current_lease.is_valid():
            return self._current_lease.leader_id
        return None
