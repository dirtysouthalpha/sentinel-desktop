"""Sentinel Desktop vNext — Fleet Mesh Orchestration.

Distributed mesh connecting all fleet nodes (Prime, Neuralis, Desktop,
CNS, Agent Zero) via a WebSocket event bus. Any node can lead
orchestrations. Neuralis serves as the memory backbone.

Modules:
  event_bus    — WebSocket pub/sub event layer
  node         — Node identity, capabilities, heartbeat
  leader_election — Lease-based priority-ordered leader election
  task_graph   — Task model, dependencies, checkpointing
  orchestrator — Plan→delegate→execute→remember loop
  cache        — Local SQLite state cache
  recovery     — Self-recovery ladder
  digest       — Daily digest generation
  budget       — Task budget caps
  trust_dial   — Per-action-type autonomy levels
  partition    — Conflict resolution, vector clocks
"""

from core.mesh.event_bus import EventBus
from core.mesh.leader_election import LeaderElection
from core.mesh.node import MeshNode, NodeCapabilities
from core.mesh.orchestrator import Orchestrator

__all__ = [
    "EventBus",
    "MeshNode",
    "NodeCapabilities",
    "LeaderElection",
    "Orchestrator",
]
