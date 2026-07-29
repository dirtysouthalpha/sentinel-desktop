"""Sentinel Desktop vNext — Fleet Mesh Orchestration.

Distributed mesh connecting all fleet nodes (Prime, Neuralis, Desktop,
CNS, Agent Zero) via a WebSocket event bus. Any node can lead
orchestrations. Neuralis serves as the memory backbone.

Modules:
  event_bus         — WebSocket pub/sub event layer
  node              — Node identity, capabilities, heartbeat
  leader_election   — Lease-based priority-ordered leader election
  task_graph        — Task model, dependencies, checkpointing
  orchestrator      — Plan→delegate→execute→remember loop
  cache             — Local SQLite state cache
  recovery          — Self-recovery ladder
  self_recovery     — Full self-recovery orchestration (watcher + recovery)
  digest            — Daily digest generation
  digest_scheduler  — Scheduled digest pipeline
  budget            — Task budget caps
  trust_dial        — Per-action-type autonomy levels
  partition         — Conflict resolution, vector clocks
  transport         — WebSocket full-mesh transport
  executor          — Task execution (shell/python/action/llm)
  memory            — Neuralis memory adapter
  metrics           — Node metrics collection and aggregation
  cli               — Fleet CLI
  watcher           — Self-healing watcher
  mcp_server        — MCP server exposing fleet operations
"""

from core.mesh.digest_scheduler import DigestPipeline
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.executor import TaskExecutor
from core.mesh.leader_election import LeaderElection
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority
from core.mesh.orchestrator import Orchestrator
from core.mesh.self_recovery import SelfRecoveryLadder
from core.mesh.transport import WebSocketTransport

__all__ = [
    "EventBus",
    "FleetEvent",
    "MeshNode",
    "NodeCapabilities",
    "NodePriority",
    "LeaderElection",
    "Orchestrator",
    "WebSocketTransport",
    "TaskExecutor",
    "DigestPipeline",
    "SelfRecoveryLadder",
]
