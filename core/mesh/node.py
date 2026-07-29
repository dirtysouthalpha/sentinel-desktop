"""Node identity, capabilities, and heartbeat."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from time import time
from typing import Any

logger = logging.getLogger(__name__)


class NodePriority(IntEnum):
    """Leader election priority. Higher = more likely to lead."""
    NEURALIS = -1
    AGENT_ZERO = 0
    DESKTOP = 10
    PRIME = 20
    CNS = 30


@dataclass
class NodeCapabilities:
    """What this node can do in the fleet."""
    can_orchestrate: bool = False
    can_execute_desktop: bool = False
    can_reason: bool = False
    can_remember: bool = False
    can_display: bool = False
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class MeshNode:
    """A single node in the fleet mesh."""
    node_id: str
    name: str
    priority: NodePriority
    capabilities: NodeCapabilities
    status: str = "initializing"
    last_heartbeat: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def heartbeat(self) -> None:
        self.last_heartbeat = time()
        if self.status == "initializing":
            self.status = "active"

    def is_alive(self, timeout_seconds: float = 30) -> bool:
        if self.last_heartbeat is None:
            return False
        return (time() - self.last_heartbeat) < timeout_seconds

    def stop(self) -> None:
        self.status = "stopped"

    @property
    def is_leader_candidate(self) -> bool:
        return self.priority >= 0 and self.capabilities.can_orchestrate
