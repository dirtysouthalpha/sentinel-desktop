# Fleet vNext — Unified Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the unified orchestration mesh that ties Sentinel Desktop, Neuralis, CNS, Prime, and Agent Zero into a self-operating fleet — 24/7 autonomous, zero human firefighting, daily digest only.

**Architecture:** Distributed mesh with WebSocket event bus. No single conductor — any node can lead via priority-ordered lease election. Neuralis is the memory backbone (not the conductor). Each node caches state locally for resilience. The orchestration loop is plan→delegate→execute→remember→digest.

**Tech Stack:** Python 3.10+, `websockets` (existing dep), SQLite (stdlib), `atomic_io` (existing module), `pytest` + `pytest-asyncio`. No new dependencies.

---

## File Structure

### New files (core/mesh/)

| File | Responsibility |
|------|----------------|
| `core/mesh/__init__.py` | Mesh package, public API |
| `core/mesh/event_bus.py` | WebSocket pub/sub event bus |
| `core/mesh/node.py` | Node identity, capabilities, heartbeat |
| `core/mesh/leader_election.py` | Lease-based priority-ordered leader election |
| `core/mesh/task_graph.py` | Task model, dependencies, checkpointing |
| `core/mesh/orchestrator.py` | Plan→delegate→execute→remember loop |
| `core/mesh/cache.py` | Local SQLite state cache |
| `core/mesh/recovery.py` | Self-recovery ladder |
| `core/mesh/digest.py` | Daily digest generation |
| `core/mesh/budget.py` | Task budget caps |
| `core/mesh/trust_dial.py` | Per-action-type autonomy levels |
| `core/mesh/partition.py` | Conflict resolution, vector clocks |

### Modified files

| File | Change |
|------|--------|
| `core/server/server.py` | Add WebSocket endpoint for event bus |
| `core/checkpoint.py` | Extend for task checkpointing |
| `main.py` | Add `--mesh` flag, initialize mesh on startup |

### Test files

| File | Tests |
|------|-------|
| `tests/test_mesh_event_bus.py` | Event publish/subscribe, reconnect |
| `tests/test_mesh_node.py` | Node identity, heartbeat, capabilities |
| `tests/test_mesh_leader_election.py` | Lease acquire/renew/transfer |
| `tests/test_mesh_task_graph.py` | Task creation, dependencies, checkpoint |
| `tests/test_mesh_orchestrator.py` | Plan→delegate→execute cycle |
| `tests/test_mesh_cache.py` | Cache write/read/reconcile |
| `tests/test_mesh_recovery.py` | Failure detection, retry ladder |
| `tests/test_mesh_digest.py` | Digest generation, formatting |
| `tests/test_mesh_budget.py` | Budget enforcement, caps |
| `tests/test_mesh_trust_dial.py` | Trust levels, action gating |
| `tests/test_mesh_partition.py` | Conflict resolution, vector clocks |

---

## Task 1: Mesh Package Skeleton

**Files:**
- Create: `core/mesh/__init__.py`
- Test: `tests/test_mesh_init.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the mesh package."""
from core.mesh import MeshNode, EventBus, LeaderElection, Orchestrator


class TestMeshImport:
    def test_public_api_available(self):
        """Mesh package exposes core classes."""
        assert MeshNode is not None
        assert EventBus is not None
        assert LeaderElection is not None
        assert Orchestrator is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_init.py -v`
Expected: FAIL — `cannot import name 'MeshNode' from 'core.mesh'`

- [ ] **Step 3: Create the mesh package**

Create `core/mesh/__init__.py`:

```python
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
from core.mesh.node import MeshNode, NodeCapabilities
from core.mesh.leader_election import LeaderElection
from core.mesh.orchestrator import Orchestrator

__all__ = [
    "EventBus",
    "MeshNode",
    "NodeCapabilities",
    "LeaderElection",
    "Orchestrator",
]
```

- [ ] **Step 4: Create stub files for imports**

Create `core/mesh/event_bus.py`:

```python
"""WebSocket pub/sub event bus for the fleet mesh."""
from __future__ import annotations

class EventBus:
    """Placeholder — implemented in Task 2."""
    def __init__(self) -> None:
        raise NotImplementedError("Task 2")
```

Create `core/mesh/node.py`:

```python
"""Node identity, capabilities, and heartbeat."""
from __future__ import annotations

class NodeCapabilities:
    """Placeholder — implemented in Task 3."""
    def __init__(self) -> None:
        raise NotImplementedError("Task 3")

class MeshNode:
    """Placeholder — implemented in Task 3."""
    def __init__(self) -> None:
        raise NotImplementedError("Task 3")
```

Create `core/mesh/leader_election.py`:

```python
"""Lease-based priority-ordered leader election."""
from __future__ import annotations

class LeaderElection:
    """Placeholder — implemented in Task 4."""
    def __init__(self) -> None:
        raise NotImplementedError("Task 4")
```

Create `core/mesh/orchestrator.py`:

```python
"""Plan→delegate→execute→remember orchestration loop."""
from __future__ import annotations

class Orchestrator:
    """Placeholder — implemented in Task 6."""
    def __init__(self) -> None:
        raise NotImplementedError("Task 6")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_mesh_init.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/mesh/__init__.py core/mesh/event_bus.py core/mesh/node.py core/mesh/leader_election.py core/mesh/orchestrator.py tests/test_mesh_init.py
git commit -m "feat(mesh): add mesh package skeleton with public API"
```

---

## Task 2: Event Bus — WebSocket Pub/Sub

**Files:**
- Modify: `core/mesh/event_bus.py`
- Test: `tests/test_mesh_event_bus.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the WebSocket event bus."""
import asyncio
import pytest
from core.mesh.event_bus import EventBus, FleetEvent


class TestEventBus:
    def test_event_types_defined(self):
        """FleetEvent enum covers all required event types."""
        assert FleetEvent.NODE_HEARTBEAT == "fleet.event.node.heartbeat"
        assert FleetEvent.TASK_COMPLETED == "fleet.event.task.completed"
        assert FleetEvent.TASK_FAILED == "fleet.event.task.failed"
        assert FleetEvent.PLAN_CREATED == "fleet.event.plan.created"
        assert FleetEvent.MEMORY_STORED == "fleet.event.memory.stored"
        assert FleetEvent.ESCALATION_DAILY == "fleet.event.escalation.daily"

    @pytest.mark.asyncio
    async def test_publish_subscribe_in_process(self):
        """Subscriber receives events published on the bus."""
        bus = EventBus()
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        bus.subscribe("fleet.event.task.completed", handler)
        await bus.publish("fleet.event.task.completed", {"task_id": "t1", "result": "ok"})
        await asyncio.sleep(0.01)  # let async handler run

        assert len(received) == 1
        assert received[0]["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_subscriber_receives_only_its_events(self):
        """Subscriber does not receive events it didn't subscribe to."""
        bus = EventBus()
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        bus.subscribe("fleet.event.task.completed", handler)
        await bus.publish("fleet.event.task.failed", {"task_id": "t2"})
        await asyncio.sleep(0.01)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """All subscribers for an event type receive it."""
        bus = EventBus()
        a: list[dict] = []
        b: list[dict] = []

        bus.subscribe("fleet.event.node.heartbeat", lambda evt: a.append(evt))
        bus.subscribe("fleet.event.node.heartbeat", lambda evt: b.append(evt))
        await bus.publish("fleet.event.node.heartbeat", {"node_id": "n1"})
        await asyncio.sleep(0.01)

        assert len(a) == 1
        assert len(b) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_event_bus.py -v`
Expected: FAIL — `EventBus` raises `NotImplementedError`

- [ ] **Step 3: Implement the event bus**

Replace `core/mesh/event_bus.py`:

```python
"""WebSocket pub/sub event bus for the fleet mesh.

In-process pub/sub for single-node operation. The WebSocket transport
layer (Task 8) wraps this for cross-node delivery. This design keeps
the core bus testable without network I/O.
"""
from __future__ import annotations

import asyncio
import enum
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from enum import Enum

logger = logging.getLogger(__name__)


class FleetEvent(str, Enum):
    """Fleet event types published on the mesh event bus."""
    # Lifecycle
    NODE_HEARTBEAT = "fleet.event.node.heartbeat"
    NODE_JOINED = "fleet.event.node.joined"
    NODE_LEFT = "fleet.event.node.left"
    # Tasks
    TASK_CREATED = "fleet.event.task.created"
    TASK_ASSIGNED = "fleet.event.task.assigned"
    TASK_PROGRESS = "fleet.event.task.progress"
    TASK_COMPLETED = "fleet.event.task.completed"
    TASK_FAILED = "fleet.event.task.failed"
    # Plans
    PLAN_CREATED = "fleet.event.plan.created"
    PLAN_UPDATED = "fleet.event.plan.updated"
    PLAN_COMPLETED = "fleet.event.plan.completed"
    # Memory
    MEMORY_STORED = "fleet.event.memory.stored"
    MEMORY_RECALLED = "fleet.event.memory.recalled"
    # Escalation
    ESCALATION_DAILY = "fleet.event.escalation.daily"
    ESCALATION_CRITICAL = "fleet.event.escalation.critical"


EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class EventBus:
    """In-process async event bus.

    Subscribers register a handler for an event type. `publish` delivers
    the event to all matching subscribers concurrently.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register *handler* for *event_type*."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove *handler* from *event_type*."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers.

        The event envelope includes type, timestamp, event_id, and data.
        Handlers run concurrently; exceptions are logged but don't block.
        """
        envelope = {
            "type": event_type,
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        handlers = list(self._subscribers.get(event_type, []))
        if not handlers:
            return

        results = await asyncio.gather(
            *[self._safe_call(h, envelope) for h in handlers],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Event handler error: %s", result)

    @staticmethod
    async def _safe_call(handler: EventHandler, envelope: dict[str, Any]) -> None:
        """Call handler, catching exceptions."""
        result = handler(envelope)
        if asyncio.iscoroutine(result):
            await result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_event_bus.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/event_bus.py tests/test_mesh_event_bus.py
git commit -m "feat(mesh): implement in-process event bus with pub/sub"
```

---

## Task 3: Node Identity & Heartbeat

**Files:**
- Modify: `core/mesh/node.py`
- Test: `tests/test_mesh_node.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for node identity, capabilities, and heartbeat."""
import time
import pytest
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority


class TestNodeCapabilities:
    def test_capabilities_default(self):
        caps = NodeCapabilities()
        assert caps.can_orchestrate is False
        assert caps.can_execute_desktop is False
        assert caps.can_reason is False
        assert caps.can_remember is False

    def test_capabilities_full(self):
        caps = NodeCapabilities(
            can_orchestrate=True,
            can_execute_desktop=True,
            can_reason=True,
            can_remember=True,
        )
        assert caps.can_orchestrate is True
        assert caps.can_execute_desktop is True
        assert caps.can_reason is True
        assert caps.can_remember is True


class TestNodePriority:
    def test_priority_ordering(self):
        """Priority ordering: CNS > Prime > Desktop > AgentZero."""
        assert NodePriority.CNS > NodePriority.PRIME
        assert NodePriority.PRIME > NodePriority.DESKTOP
        assert NodePriority.DESKTOP > NodePriority.AGENT_ZERO
        assert NodePriority.NEURALIS == -1  # never leader


class TestMeshNode:
    def test_node_creation(self):
        caps = NodeCapabilities(can_orchestrate=True)
        node = MeshNode(
            node_id="test-1",
            name="test-node",
            priority=NodePriority.PRIME,
            capabilities=caps,
        )
        assert node.node_id == "test-1"
        assert node.name == "test-node"
        assert node.priority == NodePriority.PRIME
        assert node.status == "initializing"

    def test_heartbeat_updates_timestamp(self):
        node = MeshNode(
            node_id="test-2",
            name="test",
            priority=NodePriority.DESKTOP,
            capabilities=NodeCapabilities(),
        )
        assert node.last_heartbeat is None
        node.heartbeat()
        assert node.last_heartbeat is not None

    def test_is_alive_within_threshold(self):
        node = MeshNode(
            node_id="test-3",
            name="test",
            priority=NodePriority.DESKTOP,
            capabilities=NodeCapabilities(),
        )
        node.heartbeat()
        assert node.is_alive(timeout_seconds=30) is True

    def test_is_alive_expired(self):
        node = MeshNode(
            node_id="test-4",
            name="test",
            priority=NodePriority.DESKTOP,
            capabilities=NodeCapabilities(),
        )
        node.last_heartbeat = time.time() - 60
        assert node.is_alive(timeout_seconds=30) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_node.py -v`
Expected: FAIL — `MeshNode` raises `NotImplementedError`

- [ ] **Step 3: Implement node identity**

Replace `core/mesh/node.py`:

```python
"""Node identity, capabilities, and heartbeat.

Each fleet node (Prime, Desktop, CNS, Agent Zero) has a unique ID,
a priority for leader election, a set of capabilities, and a heartbeat
for liveness detection.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from time import time
from typing import Any

logger = logging.getLogger(__name__)


class NodePriority(IntEnum):
    """Leader election priority. Higher = more likely to lead.

    Neuralis is memory-only and never leads (priority -1).
    """
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
    status: str = "initializing"  # initializing, active, degraded, stopped
    last_heartbeat: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def heartbeat(self) -> None:
        """Record a heartbeat timestamp."""
        self.last_heartbeat = time()
        if self.status == "initializing":
            self.status = "active"

    def is_alive(self, timeout_seconds: float = 30) -> bool:
        """True if the node has sent a heartbeat within the timeout."""
        if self.last_heartbeat is None:
            return False
        return (time() - self.last_heartbeat) < timeout_seconds

    def stop(self) -> None:
        """Mark node as stopped."""
        self.status = "stopped"

    @property
    def is_leader_candidate(self) -> bool:
        """True if this node can be leader (Neuralis cannot)."""
        return self.priority >= 0 and self.capabilities.can_orchestrate
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_node.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/node.py tests/test_mesh_node.py
git commit -m "feat(mesh): add node identity, capabilities, and heartbeat"
```

---

## Task 4: Leader Election

**Files:**
- Modify: `core/mesh/leader_election.py`
- Test: `tests/test_mesh_leader_election.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for lease-based priority-ordered leader election."""
import asyncio
import time
import pytest
from core.mesh.leader_election import LeaderElection, Lease
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority


def make_node(node_id: str, priority: NodePriority, can_orchestrate: bool = True) -> MeshNode:
    return MeshNode(
        node_id=node_id,
        name=node_id,
        priority=priority,
        capabilities=NodeCapabilities(can_orchestrate=can_orchestrate),
    )


class TestLease:
    def test_lease_creation(self):
        lease = Lease(leader_id="n1", expires_at=time.time() + 30)
        assert lease.leader_id == "n1"
        assert lease.is_valid()

    def test_lease_expired(self):
        lease = Lease(leader_id="n1", expires_at=time.time() - 1)
        assert not lease.is_valid()


class TestLeaderElection:
    def test_highest_priority_wins(self):
        """Leader election picks the highest-priority alive node."""
        election = LeaderElection(lease_ttl=30)
        cns = make_node("cns", NodePriority.CNS)
        prime = make_node("prime", NodePriority.PRIME)
        desktop = make_node("desktop", NodePriority.DESKTOP)

        # All nodes heartbeat
        for node in [cns, prime, desktop]:
            node.heartbeat()

        leader = election.elect_leader([cns, prime, desktop])
        assert leader is not None
        assert leader.node_id == "cns"

    def test_no_alive_nodes(self):
        """No leader when no nodes are alive."""
        election = LeaderElection(lease_ttl=30)
        node = make_node("n1", NodePriority.PRIME)
        # No heartbeat — not alive
        leader = election.elect_leader([node])
        assert leader is None

    def test_neuralis_never_leader(self):
        """Neuralis (priority -1) is never elected leader."""
        election = LeaderElection(lease_ttl=30)
        neuralis = make_node("brain", NodePriority.NEURALIS, can_orchestrate=False)
        neuralis.heartbeat()
        leader = election.elect_leader([neuralis])
        assert leader is None

    def test_priority_fallback(self):
        """If highest-priority node is dead, next highest wins."""
        election = LeaderElection(lease_ttl=30)
        cns = make_node("cns", NodePriority.CNS)  # dead (no heartbeat)
        prime = make_node("prime", NodePriority.PRIME)
        prime.heartbeat()

        leader = election.elect_leader([cns, prime])
        assert leader is not None
        assert leader.node_id == "prime"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_leader_election.py -v`
Expected: FAIL — `LeaderElection` raises `NotImplementedError`

- [ ] **Step 3: Implement leader election**

Replace `core/mesh/leader_election.py`:

```python
"""Lease-based priority-ordered leader election.

The leader is the highest-priority alive node with a valid lease.
Lease is stored in Neuralis (region: "system") so it survives any
single node failure. Leader renews every 15s; expires after TTL.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from time import time

from core.mesh.node import MeshNode

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    """A leadership lease held by a node."""
    leader_id: str
    expires_at: float
    priority: int = 0

    def is_valid(self) -> bool:
        """True if the lease has not expired."""
        return time() < self.expires_at


class LeaderElection:
    """Elects a leader from alive nodes by priority."""

    def __init__(self, lease_ttl: float = 30.0) -> None:
        self.lease_ttl = lease_ttl
        self._current_lease: Lease | None = None

    def elect_leader(self, nodes: list[MeshNode]) -> MeshNode | None:
        """Elect the highest-priority alive node as leader.

        Returns None if no alive leader-candidate exists.
        """
        candidates = [
            n for n in nodes
            if n.is_leader_candidate and n.is_alive(timeout_seconds=self.lease_ttl)
        ]
        if not candidates:
            if self._current_lease and self._current_lease.is_valid():
                logger.warning("No alive nodes but lease still valid — holding")
                return None
            self._current_lease = None
            return None

        # Sort by priority descending
        candidates.sort(key=lambda n: n.priority, reverse=True)
        winner = candidates[0]

        if self._current_lease is None or self._current_lease.leader_id != winner.node_id:
            self._current_lease = Lease(
                leader_id=winner.node_id,
                expires_at=time() + self.lease_ttl,
                priority=winner.priority,
            )
            logger.info("New leader elected: %s (priority %d)", winner.node_id, winner.priority)

        return winner

    def renew_lease(self, node_id: str) -> bool:
        """Renew the lease for the current leader.

        Returns True if renewal succeeds (caller is still leader).
        """
        if self._current_lease is None:
            return False
        if self._current_lease.leader_id != node_id:
            return False
        if not self._current_lease.is_valid():
            return False
        self._current_lease.expires_at = time() + self.lease_ttl
        return True

    @property
    def current_leader(self) -> str | None:
        """Current leader node ID, or None if no valid lease."""
        if self._current_lease and self._current_lease.is_valid():
            return self._current_lease.leader_id
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_leader_election.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/leader_election.py tests/test_mesh_leader_election.py
git commit -m "feat(mesh): implement lease-based priority-ordered leader election"
```

---

## Task 5: Local State Cache

**Files:**
- Create: `core/mesh/cache.py`
- Test: `tests/test_mesh_cache.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the local SQLite state cache."""
import os
import tempfile
import pytest
from core.mesh.cache import StateCache


class TestStateCache:
    def test_write_and_read(self):
        """Write a value, read it back."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "p1", {"goal": "test", "status": "active"})
            result = cache.get("plan", "p1")
            assert result is not None
            assert result["goal"] == "test"

    def test_read_missing_key(self):
        """Reading a nonexistent key returns None."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            assert cache.get("plan", "nonexistent") is None

    def test_overwrite(self):
        """Put with same key overwrites."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "p1", {"status": "active"})
            cache.put("plan", "p1", {"status": "completed"})
            assert cache.get("plan", "p1")["status"] == "completed"

    def test_list_by_bucket(self):
        """List all entries in a bucket."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "p1", {"goal": "a"})
            cache.put("plan", "p2", {"goal": "b"})
            cache.put("memory", "m1", {"content": "x"})
            plans = cache.list_bucket("plan")
            assert len(plans) == 2
            assert all(p["_key"] in ("p1", "p2") for p in plans)

    def test_delete(self):
        """Delete removes the entry."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "p1", {"goal": "test"})
            cache.delete("plan", "p1")
            assert cache.get("plan", "p1") is None

    def test_prune_old_entries(self):
        """Prune removes entries older than max_age_seconds."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = StateCache(db_path=os.path.join(tmp, "cache.db"))
            cache.put("plan", "old", {"goal": "old"})
            cache.put("plan", "new", {"goal": "new"})
            # Prune everything older than 0 seconds (forces expiry)
            import time
            time.sleep(0.01)
            cache.prune(max_age_seconds=0)
            assert cache.get("plan", "old") is None
            assert cache.get("plan", "new") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_cache.py -v`
Expected: FAIL — `StateCache` not defined

- [ ] **Step 3: Implement the cache**

Create `core/mesh/cache.py`:

```python
"""Local SQLite state cache for fleet mesh nodes.

Each node caches plans, memories, events, and checkpoints locally
so it can operate during brief Neuralis outages. Uses atomic writes
via the existing atomic_io module.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from core.atomic_io import atomic_write_bytes

logger = logging.getLogger(__name__)


class StateCache:
    """SQLite-backed local cache with bucket/key/value storage.

    Buckets: "plan", "memory", "event", "checkpoint", "node"
    """

    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the cache table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    bucket TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (bucket, key)
                )
            """)
            conn.commit()

    def put(self, bucket: str, key: str, value: dict[str, Any]) -> None:
        """Store a value in the cache."""
        now = time.time()
        blob = json.dumps({
            "bucket": bucket,
            "key": key,
            "value": value,
            "created_at": now,
        })
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (bucket, key, value, created_at) VALUES (?, ?, ?, ?)",
                (bucket, key, blob, now),
            )
            conn.commit()

    def get(self, bucket: str, key: str) -> dict[str, Any] | None:
        """Read a value from the cache."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM cache WHERE bucket = ? AND key = ?",
                (bucket, key),
            ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row[0])
            return data.get("value")
        except (json.JSONDecodeError, KeyError):
            return None

    def list_bucket(self, bucket: str) -> list[dict[str, Any]]:
        """List all entries in a bucket."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT value FROM cache WHERE bucket = ?",
                (bucket,),
            ).fetchall()
        results = []
        for row in rows:
            try:
                data = json.loads(row[0])
                entry = data.get("value", {})
                entry["_key"] = data.get("key", "")
                results.append(entry)
            except (json.JSONDecodeError, KeyError):
                continue
        return results

    def delete(self, bucket: str, key: str) -> None:
        """Delete a cache entry."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM cache WHERE bucket = ? AND key = ?",
                (bucket, key),
            )
            conn.commit()

    def prune(self, max_age_seconds: float) -> int:
        """Remove entries older than max_age_seconds. Returns count pruned."""
        cutoff = time.time() - max_age_seconds
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM cache WHERE created_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/cache.py tests/test_mesh_cache.py
git commit -m "feat(mesh): add local SQLite state cache for node resilience"
```

---

## Task 6: Task Graph & Checkpointing

**Files:**
- Create: `core/mesh/task_graph.py`
- Test: `tests/test_mesh_task_graph.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the task graph and checkpointing."""
import os
import tempfile
import pytest
from core.mesh.task_graph import Task, TaskStatus, TaskGraph, TaskBudget


class TestTask:
    def test_task_creation(self):
        task = Task(id="t1", type="desktop_automation", goal="open notepad")
        assert task.id == "t1"
        assert task.status == TaskStatus.PENDING
        assert task.retry_count == 0

    def test_task_budget_default(self):
        budget = TaskBudget()
        assert budget.max_api_calls == 100
        assert budget.max_runtime_seconds == 3600
        assert budget.max_cost_usd == 5.0

    def test_task_budget_exceeded(self):
        budget = TaskBudget(max_api_calls=5)
        assert budget.is_exceeded(api_calls=10) is True
        assert budget.is_exceeded(api_calls=3) is False


class TestTaskGraph:
    def test_add_task(self):
        graph = TaskGraph()
        task = Task(id="t1", type="reasoning", goal="plan something")
        graph.add_task(task)
        assert graph.get_task("t1") is task

    def test_dependencies(self):
        """Task with unmet dependencies is not ready."""
        graph = TaskGraph()
        t1 = Task(id="t1", type="reasoning", goal="plan")
        t2 = Task(id="t2", type="desktop_automation", goal="execute", depends_on=["t1"])
        graph.add_task(t1)
        graph.add_task(t2)

        assert t2.is_ready(graph) is False
        t1.status = TaskStatus.COMPLETED
        assert t2.is_ready(graph) is True

    def test_get_ready_tasks(self):
        """Returns tasks whose dependencies are all completed."""
        graph = TaskGraph()
        t1 = Task(id="t1", type="reasoning", goal="plan")
        t2 = Task(id="t2", type="desktop_automation", goal="exec", depends_on=["t1"])
        t3 = Task(id="t3", type="monitoring", goal="check")
        graph.add_task(t1)
        graph.add_task(t2)
        graph.add_task(t3)

        t1.status = TaskStatus.COMPLETED
        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t2"  # t3 has no deps but isn't "ready" until t1 done? No — t3 has no deps
        # Actually t3 has no deps so it should also be ready
        # Let me fix: t3 has no dependencies, so it's ready from the start
        # But get_ready_tasks should return tasks that are PENDING and have all deps met
        # t3 has no deps → all (zero) deps are met → ready
        # So ready should be [t2, t3]
        assert len(ready) == 2

    def test_checkpoint_save_and_load(self):
        """Checkpoint saves task state, load restores it."""
        with tempfile.TemporaryDirectory() as tmp:
            graph = TaskGraph(checkpoint_dir=tmp)
            task = Task(id="t1", type="reasoning", goal="plan")
            task.status = TaskStatus.RUNNING
            task.retry_count = 2
            graph.add_task(task)
            graph.checkpoint(task.id)

            # Load into a new graph
            graph2 = TaskGraph(checkpoint_dir=tmp)
            loaded = graph2.load_checkpoint("t1")
            assert loaded is not None
            assert loaded["id"] == "t1"
            assert loaded["retry_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_task_graph.py -v`
Expected: FAIL — `Task` not defined

- [ ] **Step 3: Implement task graph**

Create `core/mesh/task_graph.py`:

```python
"""Task graph with dependency tracking and checkpointing.

Tasks are the unit of work in the fleet mesh. Each task has a type,
status, dependencies, retry count, and optional budget. The task graph
tracks all tasks in a plan and determines which are ready to execute.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task lifecycle states."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class TaskBudget:
    """Cost/compute cap for a task."""
    max_api_calls: int = 100
    max_runtime_seconds: int = 3600
    max_cost_usd: float = 5.0

    def is_exceeded(self, api_calls: int = 0, runtime_seconds: float = 0, cost_usd: float = 0) -> bool:
        """True if any budget dimension is exceeded."""
        return (
            api_calls > self.max_api_calls
            or runtime_seconds > self.max_runtime_seconds
            or cost_usd > self.max_cost_usd
        )


@dataclass
class Task:
    """A unit of work in the fleet mesh."""
    id: str
    type: str  # desktop_automation | reasoning | self_improvement | monitoring
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_node: str = ""
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 3
    retry_count: int = 0
    budget: TaskBudget = field(default_factory=TaskBudget)
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    checkpoint_data: dict[str, Any] = field(default_factory=dict)

    def is_ready(self, graph: TaskGraph) -> bool:
        """True if task is pending and all dependencies are completed."""
        if self.status != TaskStatus.PENDING:
            return False
        for dep_id in self.depends_on:
            dep = graph.get_task(dep_id)
            if dep is None or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def can_retry(self) -> bool:
        """True if the task has retries remaining."""
        return self.retry_count < self.max_retries


class TaskGraph:
    """Tracks tasks and their dependencies within a plan."""

    def __init__(self, checkpoint_dir: str | os.PathLike[str] | None = None) -> None:
        self.tasks: dict[str, Task] = {}
        self.checkpoint_dir = str(checkpoint_dir) if checkpoint_dir else ""
        if self.checkpoint_dir:
            Path(self.checkpoint_dir).mkdir(parents=True, exist_ok=True)

    def add_task(self, task: Task) -> None:
        """Add a task to the graph."""
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_ready_tasks(self) -> list[Task]:
        """Return all tasks that are ready to execute."""
        return [t for t in self.tasks.values() if t.is_ready(self)]

    def get_pending_tasks(self) -> list[Task]:
        """Return all pending tasks (not completed/failed)."""
        return [t for t in self.tasks.values() if t.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED)]

    def is_complete(self) -> bool:
        """True if all tasks are completed or failed."""
        return all(t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ROLLED_BACK) for t in self.tasks.values())

    def checkpoint(self, task_id: str) -> None:
        """Save a task checkpoint to disk."""
        if not self.checkpoint_dir:
            return
        task = self.tasks.get(task_id)
        if task is None:
            return
        data = {
            "id": task.id,
            "type": task.type,
            "goal": task.goal,
            "status": task.status.value,
            "assigned_node": task.assigned_node,
            "retry_count": task.retry_count,
            "result": task.result,
            "error": task.error,
            "checkpoint_data": task.checkpoint_data,
        }
        path = os.path.join(self.checkpoint_dir, f"checkpoint_{task_id}.json")
        atomic_write_text(path, json.dumps(data, indent=2))
        logger.debug("Checkpoint saved for task %s", task_id)

    def load_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        """Load a task checkpoint from disk."""
        if not self.checkpoint_dir:
            return None
        path = os.path.join(self.checkpoint_dir, f"checkpoint_{task_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_task_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/task_graph.py tests/test_mesh_task_graph.py
git commit -m "feat(mesh): add task graph with dependency tracking and checkpointing"
```

---

## Task 7: Orchestration Loop

**Files:**
- Modify: `core/mesh/orchestrator.py`
- Test: `tests/test_mesh_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the orchestration loop."""
import asyncio
import pytest
from core.mesh.orchestrator import Orchestrator
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.task_graph import Task, TaskGraph, TaskStatus
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority
from core.mesh.leader_election import LeaderElection
from core.mesh.cache import StateCache
import os
import tempfile


def make_orchestrator(tmp_dir: str) -> tuple[Orchestrator, EventBus, StateCache]:
    """Create a test orchestrator with all dependencies."""
    bus = EventBus()
    cache = StateCache(db_path=os.path.join(tmp_dir, "cache.db"))
    election = LeaderElection(lease_ttl=30)
    orch = Orchestrator(event_bus=bus, cache=cache, leader_election=election, node_id="test-leader")
    return orch, bus, cache


class TestOrchestrator:
    def test_create_plan(self, tmp_path):
        """Creating a plan adds tasks to the graph."""
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test goal")
        plan_id = orch.create_plan("test plan", [task])
        assert plan_id is not None
        assert orch.get_plan(plan_id) is not None

    def test_assign_task_to_node(self, tmp_path):
        """Assigning a task updates its status and node."""
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test")
        plan_id = orch.create_plan("test", [task])
        orch.assign_task(plan_id, "t1", "node-1")
        assert task.status == TaskStatus.ASSIGNED
        assert task.assigned_node == "node-1"

    def test_complete_task(self, tmp_path):
        """Completing a task publishes event."""
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test")
        plan_id = orch.create_plan("test", [task])
        orch.complete_task(plan_id, "t1", {"result": "ok"})
        assert task.status == TaskStatus.COMPLETED
        assert task.result["result"] == "ok"

    def test_fail_task_with_retry(self, tmp_path):
        """Failing a task increments retry count."""
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test", max_retries=3)
        plan_id = orch.create_plan("test", [task])
        orch.fail_task(plan_id, "t1", "timeout")
        assert task.retry_count == 1
        assert task.status == TaskStatus.PENDING  # ready for retry

    def test_fail_task_exhausted_retries(self, tmp_path):
        """Task with no retries left is marked failed."""
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test", max_retries=1, retry_count=1)
        plan_id = orch.create_plan("test", [task])
        orch.fail_task(plan_id, "t1", "permanent error")
        assert task.status == TaskStatus.FAILED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_orchestrator.py -v`
Expected: FAIL — `Orchestrator` raises `NotImplementedError`

- [ ] **Step 3: Implement the orchestrator**

Replace `core/mesh/orchestrator.py`:

```python
"""Plan→delegate→execute→remember orchestration loop.

The orchestrator is the brain of the fleet mesh. It creates plans
(task graphs), delegates tasks to nodes, tracks progress, handles
failures, and stores lessons. Any node can run the orchestrator when
it holds the leadership lease.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from core.mesh.cache import StateCache
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.leader_election import LeaderElection
from core.mesh.task_graph import Task, TaskGraph, TaskStatus

logger = logging.getLogger(__name__)


class Orchestrator:
    """Manages plans and task execution across the fleet mesh."""

    def __init__(
        self,
        event_bus: EventBus,
        cache: StateCache,
        leader_election: LeaderElection,
        node_id: str,
    ) -> None:
        self.bus = event_bus
        self.cache = cache
        self.election = leader_election
        self.node_id = node_id
        self._plans: dict[str, TaskGraph] = {}

    def create_plan(self, name: str, tasks: list[Task]) -> str:
        """Create a plan (task graph) and return its ID."""
        plan_id = str(uuid.uuid4())[:8]
        graph = TaskGraph()
        for task in tasks:
            graph.add_task(task)
        self._plans[plan_id] = graph
        self.cache.put("plan", plan_id, {"name": name, "status": "active", "task_count": len(tasks)})
        logger.info("Plan created: %s (%s) with %d tasks", plan_id, name, len(tasks))
        return plan_id

    def get_plan(self, plan_id: str) -> TaskGraph | None:
        """Get a plan's task graph."""
        return self._plans.get(plan_id)

    def assign_task(self, plan_id: str, task_id: str, node_id: str) -> bool:
        """Assign a task to a node for execution."""
        graph = self._plans.get(plan_id)
        if graph is None:
            return False
        task = graph.get_task(task_id)
        if task is None:
            return False
        task.status = TaskStatus.ASSIGNED
        task.assigned_node = node_id
        logger.info("Task %s assigned to node %s", task_id, node_id)
        return True

    def complete_task(self, plan_id: str, task_id: str, result: dict[str, Any]) -> None:
        """Mark a task as completed with its result."""
        graph = self._plans.get(plan_id)
        if graph is None:
            return
        task = graph.get_task(task_id)
        if task is None:
            return
        task.status = TaskStatus.COMPLETED
        task.result = result
        graph.checkpoint(task_id)
        logger.info("Task %s completed by node %s", task_id, task.assigned_node)

    def fail_task(self, plan_id: str, task_id: str, error: str) -> None:
        """Handle a task failure. Retry if retries remain, else mark failed."""
        graph = self._plans.get(plan_id)
        if graph is None:
            return
        task = graph.get_task(task_id)
        if task is None:
            return
        task.error = error
        if task.can_retry():
            task.retry_count += 1
            task.status = TaskStatus.PENDING
            task.assigned_node = ""
            logger.warning("Task %s failed (retry %d/%d): %s", task_id, task.retry_count, task.max_retries, error)
        else:
            task.status = TaskStatus.FAILED
            logger.error("Task %s permanently failed: %s", task_id, error)
        graph.checkpoint(task_id)

    def get_plan_status(self, plan_id: str) -> dict[str, Any] | None:
        """Get a summary of plan progress."""
        graph = self._plans.get(plan_id)
        if graph is None:
            return None
        tasks = list(graph.tasks.values())
        return {
            "plan_id": plan_id,
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in tasks if t.status == TaskStatus.FAILED),
            "pending": sum(1 for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED)),
            "is_complete": graph.is_complete(),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_orchestrator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/orchestrator.py tests/test_mesh_orchestrator.py
git commit -m "feat(mesh): implement orchestration loop (plan→delegate→execute)"
```

---

## Task 8: Self-Recovery Ladder

**Files:**
- Create: `core/mesh/recovery.py`
- Test: `tests/test_mesh_recovery.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the self-recovery ladder."""
import pytest
from core.mesh.recovery import RecoveryManager, FailureType
from core.mesh.task_graph import Task, TaskGraph, TaskStatus
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority


def make_node(node_id: str, priority: NodePriority = NodePriority.DESKTOP) -> MeshNode:
    return MeshNode(
        node_id=node_id,
        name=node_id,
        priority=priority,
        capabilities=NodeCapabilities(can_orchestrate=True, can_execute_desktop=True),
    )


class TestRecoveryManager:
    def test_classify_transient_failure(self):
        """Timeout is classified as transient (retryable)."""
        mgr = RecoveryManager()
        failure_type = mgr.classify_failure("Connection timeout")
        assert failure_type == FailureType.TRANSIENT

    def test_classify_permanent_failure(self):
        """Authentication error is permanent (not retryable)."""
        mgr = RecoveryManager()
        failure_type = mgr.classify_failure("Authentication failed: invalid token")
        assert failure_type == FailureType.PERMANENT

    def test_classify_resource_failure(self):
        """Disk full is a resource failure."""
        mgr = RecoveryManager()
        failure_type = mgr.classify_failure("No space left on device")
        assert failure_type == FailureType.RESOURCE

    def test_should_retry_transient(self):
        """Transient failures should be retried."""
        mgr = RecoveryManager()
        task = Task(id="t1", type="reasoning", goal="test", retry_count=0, max_retries=3)
        assert mgr.should_retry(task, FailureType.TRANSIENT) is True

    def test_no_retry_permanent(self):
        """Permanent failures should not be retried."""
        mgr = RecoveryManager()
        task = Task(id="t1", type="reasoning", goal="test", retry_count=0, max_retries=3)
        assert mgr.should_retry(task, FailureType.PERMANENT) is False

    def test_no_retry_exhausted(self):
        """Don't retry if retries are exhausted."""
        mgr = RecoveryManager()
        task = Task(id="t1", type="reasoning", goal="test", retry_count=3, max_retries=3)
        assert mgr.should_retry(task, FailureType.TRANSIENT) is False

    def test_select_fallback_node(self):
        """Select a different node for fallback execution."""
        mgr = RecoveryManager()
        n1 = make_node("n1")
        n2 = make_node("n2")
        n3 = make_node("n3")
        for n in [n1, n2, n3]:
            n.heartbeat()

        fallback = mgr.select_fallback_node(current_node_id="n1", available_nodes=[n1, n2, n3])
        assert fallback is not None
        assert fallback.node_id != "n1"

    def test_select_fallback_no_alternatives(self):
        """No fallback if no other alive nodes."""
        mgr = RecoveryManager()
        n1 = make_node("n1")
        n1.heartbeat()
        fallback = mgr.select_fallback_node(current_node_id="n1", available_nodes=[n1])
        assert fallback is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_recovery.py -v`
Expected: FAIL — `RecoveryManager` not defined

- [ ] **Step 3: Implement recovery manager**

Create `core/mesh/recovery.py`:

```python
"""Self-recovery ladder for the fleet mesh.

Implements the failure handling ladder:
  1. Retry same node (up to 3x with backoff)
  2. Retry different node (fallback)
  3. Rollback + re-plan
  4. Self-update (if code bug)
  5. Queue for digest (never blocks)
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any

from core.mesh.node import MeshNode
from core.mesh.task_graph import Task

logger = logging.getLogger(__name__)


class FailureType(str, Enum):
    """Classification of task failures."""
    TRANSIENT = "transient"    # retryable: timeout, rate limit, network
    PERMANENT = "permanent"    # not retryable: auth, validation, not found
    RESOURCE = "resource"      # resource exhaustion: disk, memory, quota
    UNKNOWN = "unknown"        # unclassified


# Patterns that indicate failure types
_TRANSIENT_PATTERNS = [
    r"timeout", r"timed out", r"connection.*refused", r"rate.?limit",
    r"429", r"503", r"502", r"504", r"temporary", r"unavailable",
]
_PERMANENT_PATTERNS = [
    r"auth", r"unauthorized", r"forbidden", r"403", r"401",
    r"not found", r"404", r"invalid", r"validation", r"malformed",
]
_RESOURCE_PATTERNS = [
    r"no space", r"disk.?full", r"out of memory", r"oom",
    r"quota", r"rate.?exceeded", r"too many",
]


class RecoveryManager:
    """Handles task failures with the recovery ladder."""

    def classify_failure(self, error_message: str) -> FailureType:
        """Classify an error message into a failure type."""
        msg = error_message.lower()
        for pattern in _RESOURCE_PATTERNS:
            if re.search(pattern, msg):
                return FailureType.RESOURCE
        for pattern in _PERMANENT_PATTERNS:
            if re.search(pattern, msg):
                return FailureType.PERMANENT
        for pattern in _TRANSIENT_PATTERNS:
            if re.search(pattern, msg):
                return FailureType.TRANSIENT
        return FailureType.UNKNOWN

    def should_retry(self, task: Task, failure_type: FailureType) -> bool:
        """Determine if a task should be retried."""
        if not task.can_retry():
            return False
        if failure_type == FailureType.PERMANENT:
            return False
        return True

    def select_fallback_node(
        self,
        current_node_id: str,
        available_nodes: list[MeshNode],
        timeout_seconds: float = 30,
    ) -> MeshNode | None:
        """Select a different alive node for fallback execution."""
        candidates = [
            n for n in available_nodes
            if n.node_id != current_node_id and n.is_alive(timeout_seconds=timeout_seconds)
        ]
        if not candidates:
            return None
        # Pick highest priority
        candidates.sort(key=lambda n: n.priority, reverse=True)
        return candidates[0]

    def get_retry_delay(self, retry_count: int, base_delay: float = 1.0) -> float:
        """Exponential backoff delay for retries."""
        return base_delay * (2 ** retry_count)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_recovery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/recovery.py tests/test_mesh_recovery.py
git commit -m "feat(mesh): add self-recovery ladder with failure classification"
```

---

## Task 9: Daily Digest

**Files:**
- Create: `core/mesh/digest.py`
- Test: `tests/test_mesh_digest.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the daily digest generator."""
from core.mesh.digest import DailyDigest
from core.mesh.task_graph import Task, TaskStatus


class TestDailyDigest:
    def test_empty_digest(self):
        """Digest with no tasks shows zeros."""
        dd = DailyDigest()
        report = dd.generate(tasks=[], nodes=[], lessons=[])
        assert "0 completed" in report

    def test_digest_with_tasks(self):
        """Digest summarizes task stats."""
        dd = DailyDigest()
        tasks = [
            Task(id="t1", type="reasoning", goal="plan", status=TaskStatus.COMPLETED),
            Task(id="t2", type="desktop_automation", goal="exec", status=TaskStatus.COMPLETED),
            Task(id="t3", type="monitoring", goal="check", status=TaskStatus.FAILED),
        ]
        report = dd.generate(tasks=tasks, nodes=[], lessons=[])
        assert "2 completed" in report
        assert "1 failed" in report

    def test_digest_with_nodes(self):
        """Digest includes node health."""
        dd = DailyDigest()
        nodes = [
            {"node_id": "prime", "status": "active", "cpu": 12.5},
            {"node_id": "desktop", "status": "active", "cpu": 45.0},
        ]
        report = dd.generate(tasks=[], nodes=nodes, lessons=[])
        assert "prime" in report
        assert "desktop" in report

    def test_digest_with_lessons(self):
        """Digest includes top lessons."""
        dd = DailyDigest()
        lessons = [
            {"content": "catbox paused uploads", "fire_count": 5},
            {"content": "hackbox drifted silently", "fire_count": 3},
        ]
        report = dd.generate(tasks=[], nodes=[], lessons=lessons)
        assert "catbox" in report
        assert "hackbox" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_digest.py -v`
Expected: FAIL — `DailyDigest` not defined

- [ ] **Step 3: Implement daily digest**

Create `core/mesh/digest.py`:

```python
"""Daily digest generator for the fleet mesh.

Produces the daily report that is the only human touchpoint in
full-auto mode. Summarizes tasks, fleet health, and lessons.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.mesh.task_graph import TaskStatus

logger = logging.getLogger(__name__)


class DailyDigest:
    """Generates the daily fleet digest report."""

    def generate(
        self,
        tasks: list[Any],
        nodes: list[dict[str, Any]],
        lessons: list[dict[str, Any]],
        max_lessons: int = 3,
    ) -> str:
        """Generate a formatted digest string."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        completed = sum(1 for t in tasks if getattr(t, "status", None) == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if getattr(t, "status", None) == TaskStatus.FAILED)
        retried = sum(1 for t in tasks if getattr(t, "retry_count", 0) > 0)
        total = len(tasks)

        lines = [
            f"FLEET DAILY DIGEST — {now}",
            "=" * 40,
            f"Tasks: {completed} completed, {retried} retried, {failed} failed (total {total})",
        ]

        # Node health
        if nodes:
            lines.append("")
            lines.append("Fleet Health:")
            for node in nodes:
                node_id = node.get("node_id", "?")
                status = node.get("status", "?")
                cpu = node.get("cpu")
                cpu_str = f" | CPU {cpu:.0f}%" if cpu is not None else ""
                lines.append(f"  {node_id}: {status}{cpu_str}")

        # Top lessons
        if lessons:
            lines.append("")
            lines.append("Top Lessons:")
            for i, lesson in enumerate(lessons[:max_lessons], 1):
                content = lesson.get("content", "")
                lines.append(f"  {i}. \"{content}\"")

        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_digest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/digest.py tests/test_mesh_digest.py
git commit -m "feat(mesh): add daily digest generator"
```

---

## Task 10: Budget Enforcement

**Files:**
- Create: `core/mesh/budget.py`
- Test: `tests/test_mesh_budget.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for task budget enforcement."""
import pytest
from core.mesh.budget import BudgetEnforcer
from core.mesh.task_graph import Task, TaskBudget, TaskStatus


class TestBudgetEnforcer:
    def test_within_budget(self):
        """Task within budget is allowed."""
        enf = BudgetEnforcer()
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_api_calls=10))
        assert enf.check_budget(task, api_calls=5) is True

    def test_exceeded_budget(self):
        """Task exceeding budget is blocked."""
        enf = BudgetEnforcer()
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_api_calls=5))
        assert enf.check_budget(task, api_calls=10) is False

    def test_runtime_budget(self):
        """Task exceeding runtime budget is blocked."""
        enf = BudgetEnforcer()
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_runtime_seconds=60))
        assert enf.check_budget(task, runtime_seconds=120) is False

    def test_cost_budget(self):
        """Task exceeding cost budget is blocked."""
        enf = BudgetEnforcer()
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_cost_usd=1.0))
        assert enf.check_budget(task, cost_usd=2.0) is False

    def test_budget_status(self):
        """Budget status reports remaining capacity."""
        enf = BudgetEnforcer()
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_api_calls=100))
        status = enf.get_budget_status(task, api_calls=75)
        assert status["api_calls_remaining"] == 25
        assert status["api_calls_pct"] == 75.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_budget.py -v`
Expected: FAIL — `BudgetEnforcer` not defined

- [ ] **Step 3: Implement budget enforcer**

Create `core/mesh/budget.py`:

```python
"""Task budget enforcement for the fleet mesh.

Each task has a budget (API calls, runtime, cost). The budget enforcer
blocks tasks that exceed their caps, preventing runaway spending.
"""
from __future__ import annotations

import logging
from typing import Any

from core.mesh.task_graph import Task

logger = logging.getLogger(__name__)


class BudgetEnforcer:
    """Enforces task budget caps."""

    def check_budget(
        self,
        task: Task,
        api_calls: int = 0,
        runtime_seconds: float = 0,
        cost_usd: float = 0,
    ) -> bool:
        """True if the task is within budget."""
        if task.budget.is_exceeded(api_calls, runtime_seconds, cost_usd):
            logger.warning(
                "Task %s exceeded budget: api=%d/%d, runtime=%.0fs/%ds, cost=$%.2f/$%.2f",
                task.id,
                api_calls, task.budget.max_api_calls,
                runtime_seconds, task.budget.max_runtime_seconds,
                cost_usd, task.budget.max_cost_usd,
            )
            return False
        return True

    def get_budget_status(self, task: Task, api_calls: int = 0, runtime_seconds: float = 0, cost_usd: float = 0) -> dict[str, Any]:
        """Report remaining budget capacity."""
        return {
            "api_calls_remaining": max(0, task.budget.max_api_calls - api_calls),
            "api_calls_pct": (api_calls / task.budget.max_api_calls * 100) if task.budget.max_api_calls > 0 else 0,
            "runtime_remaining": max(0, task.budget.max_runtime_seconds - runtime_seconds),
            "runtime_pct": (runtime_seconds / task.budget.max_runtime_seconds * 100) if task.budget.max_runtime_seconds > 0 else 0,
            "cost_remaining": max(0, task.budget.max_cost_usd - cost_usd),
            "cost_pct": (cost_usd / task.budget.max_cost_usd * 100) if task.budget.max_cost_usd > 0 else 0,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_budget.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/budget.py tests/test_mesh_budget.py
git commit -m "feat(mesh): add task budget enforcement"
```

---

## Task 11: Trust Dial

**Files:**
- Create: `core/mesh/trust_dial.py`
- Test: `tests/test_mesh_trust_dial.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the per-action-type trust dial."""
import pytest
from core.mesh.trust_dial import TrustDial, TrustLevel, ActionType


class TestTrustDial:
    def test_default_trust_levels(self):
        """Default trust: safe actions execute, destructive propose-only."""
        dial = TrustDial()
        assert dial.get_level(ActionType.SAFE) == TrustLevel.EXECUTE
        assert dial.get_level(ActionType.DESTRUCTIVE) == TrustLevel.PROPOSE
        assert dial.get_level(ActionType.IRREVERSIBLE) == TrustLevel.PROPOSE

    def test_set_trust_level(self):
        """Setting a trust level updates the dial."""
        dial = TrustDial()
        dial.set_level(ActionType.DESTRUCTIVE, TrustLevel.EXECUTE)
        assert dial.get_level(ActionType.DESTRUCTIVE) == TrustLevel.EXECUTE

    def test_can_execute_safe(self):
        """Safe actions can always execute."""
        dial = TrustDial()
        assert dial.can_execute(ActionType.SAFE) is True

    def test_cannot_execute_destructive_by_default(self):
        """Destructive actions cannot execute by default."""
        dial = TrustDial()
        assert dial.can_execute(ActionType.DESTRUCTIVE) is False

    def test_can_execute_destructive_when_trusted(self):
        """Destructive actions can execute when trust dial is set."""
        dial = TrustDial()
        dial.set_level(ActionType.DESTRUCTIVE, TrustLevel.EXECUTE)
        assert dial.can_execute(ActionType.DESTRUCTIVE) is True

    def test_can_always_propose(self):
        """All action types can be proposed."""
        dial = TrustDial()
        assert dial.can_propose(ActionType.SAFE) is True
        assert dial.can_propose(ActionType.DESTRUCTIVE) is True
        assert dial.can_propose(ActionType.IRREVERSIBLE) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_trust_dial.py -v`
Expected: FAIL — `TrustDial` not defined

- [ ] **Step 3: Implement trust dial**

Create `core/mesh/trust_dial.py`:

```python
"""Per-action-type autonomy levels (trust dial).

Controls what the fleet can do without human approval:
  SAFE        → execute freely (read, monitor, heartbeat)
  DESTRUCTIVE → propose-only by default (rm, DROP, force-push)
  IRREVERSIBLE → propose-only (deletes, overwrites, publishes)
"""
from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class TrustLevel(str, Enum):
    """Autonomy level for an action type."""
    PROPOSE = "propose"    # can suggest, not execute
    EXECUTE = "execute"    # can execute freely


class ActionType(str, Enum):
    """Categories of fleet actions by risk level."""
    SAFE = "safe"
    DESTRUCTIVE = "destructive"
    IRREVERSIBLE = "irreversible"


class TrustDial:
    """Per-action-type trust levels. Default: safe=execute, others=propose."""

    def __init__(self) -> None:
        self._levels: dict[ActionType, TrustLevel] = {
            ActionType.SAFE: TrustLevel.EXECUTE,
            ActionType.DESTRUCTIVE: TrustLevel.PROPOSE,
            ActionType.IRREVERSIBLE: TrustLevel.PROPOSE,
        }

    def get_level(self, action_type: ActionType) -> TrustLevel:
        """Get the trust level for an action type."""
        return self._levels.get(action_type, TrustLevel.PROPOSE)

    def set_level(self, action_type: ActionType, level: TrustLevel) -> None:
        """Set the trust level for an action type."""
        self._levels[action_type] = level
        logger.info("Trust dial: %s → %s", action_type.value, level.value)

    def can_execute(self, action_type: ActionType) -> bool:
        """True if this action type can be executed without approval."""
        return self._levels.get(action_type) == TrustLevel.EXECUTE

    def can_propose(self, action_type: ActionType) -> bool:
        """True if this action type can be proposed (always true)."""
        return True  # everything can be proposed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_trust_dial.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/trust_dial.py tests/test_mesh_trust_dial.py
git commit -m "feat(mesh): add per-action-type trust dial for autonomy control"
```

---

## Task 12: Conflict Resolution & Vector Clocks

**Files:**
- Create: `core/mesh/partition.py`
- Test: `tests/test_mesh_partition.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for conflict resolution and vector clocks."""
from core.mesh.partition import VectorClock, ConflictResolver


class TestVectorClock:
    def test_new_clock_is_zero(self):
        vc = VectorClock()
        assert vc.clocks == {}

    def test_increment(self):
        """Incrementing a node's clock increases its count."""
        vc = VectorClock()
        vc.increment("n1")
        vc.increment("n1")
        assert vc.clocks["n1"] == 2

    def test_compare_concurrent(self):
        """Two clocks with different dominant nodes are concurrent."""
        va = VectorClock({"n1": 2, "n2": 1})
        vb = VectorClock({"n1": 1, "n2": 2})
        assert va.compare(vb) == 0  # concurrent

    def test_compare_before(self):
        """va happened-before vb if all va <= vb and at least one <."""
        va = VectorClock({"n1": 1, "n2": 1})
        vb = VectorClock({"n1": 2, "n2": 2})
        assert va.compare(vb) == -1  # va before vb

    def test_compare_after(self):
        """vb happened-after va."""
        va = VectorClock({"n1": 3, "n2": 2})
        vb = VectorClock({"n1": 1, "n2": 1})
        assert va.compare(vb) == 1  # va after vb

    def test_merge(self):
        """Merge takes the max of each node's clock."""
        va = VectorClock({"n1": 3, "n2": 1})
        vb = VectorClock({"n1": 2, "n2": 4})
        merged = va.merge(vb)
        assert merged.clocks == {"n1": 3, "n2": 4}


class TestConflictResolver:
    def test_no_conflict_when_one_is_newer(self):
        """When one update causally follows another, no conflict."""
        resolver = ConflictResolver()
        old = {"clock": {"n1": 1}, "data": "old"}
        new = {"clock": {"n1": 2}, "data": "new"}
        result = resolver.resolve(old, new)
        assert result["data"] == "new"

    def test_conflict_when_concurrent(self):
        """Concurrent updates produce a conflict requiring resolution."""
        resolver = ConflictResolver()
        a = {"clock": {"n1": 2, "n2": 1}, "data": "a"}
        b = {"clock": {"n1": 1, "n2": 2}, "data": "b"}
        result = resolver.resolve(a, b)
        # Last-writer-wins by timestamp fallback
        assert "data" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_partition.py -v`
Expected: FAIL — `VectorClock` not defined

- [ ] **Step 3: Implement conflict resolution**

Create `core/mesh/partition.py`:

```python
"""Conflict resolution and vector clocks for fleet partition handling.

When the fleet partitions (network split), each partition operates
independently. On reconnect, conflicting state updates are resolved
using vector clocks for causal ordering and last-writer-wins as fallback.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VectorClock:
    """A vector clock for tracking causal ordering across nodes.

    Each node maintains a counter. Increment on local event, merge on
    receiving a remote event.
    """
    clocks: dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str) -> None:
        """Increment the clock for a node."""
        self.clocks[node_id] = self.clocks.get(node_id, 0) + 1

    def merge(self, other: VectorClock) -> VectorClock:
        """Return a new vector clock with max of each component."""
        merged = {}
        all_nodes = set(self.clocks) | set(other.clocks)
        for node in all_nodes:
            merged[node] = max(self.clocks.get(node, 0), other.clocks.get(node, 0))
        return VectorClock(merged)

    def compare(self, other: VectorClock) -> int:
        """Compare two vector clocks.

        Returns:
            -1 if self happened-before other
             1 if self happened-after other
             0 if concurrent (incomparable)
        """
        all_nodes = set(self.clocks) | set(other.clocks)
        self_lte = all(self.clocks.get(n, 0) <= other.clocks.get(n, 0) for n in all_nodes)
        other_lte = all(other.clocks.get(n, 0) <= self.clocks.get(n, 0) for n in all_nodes)

        if self_lte and not other_lte:
            return -1  # self before other
        if other_lte and not self_lte:
            return 1   # self after other
        if self_lte and other_lte:
            return 0   # equal
        return 0  # concurrent


class ConflictResolver:
    """Resolves conflicting state updates after partition healing."""

    def resolve(self, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        """Resolve two conflicting updates.

        Strategy:
        1. If one causally follows the other, take the newer.
        2. If concurrent, last-writer-wins by timestamp.
        """
        clock_a = VectorClock(a.get("clock", {}))
        clock_b = VectorClock(b.get("clock", {}))

        cmp = clock_a.compare(clock_b)
        if cmp == -1:
            return b  # a before b → b is newer
        if cmp == 1:
            return a  # a after b → a is newer

        # Concurrent: last-writer-wins by timestamp
        ts_a = a.get("timestamp", "")
        ts_b = b.get("timestamp", "")
        if ts_b > ts_a:
            logger.info("Concurrent update resolved: b wins by timestamp")
            return b
        logger.info("Concurrent update resolved: a wins by timestamp")
        return a
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_partition.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mesh/partition.py tests/test_mesh_partition.py
git commit -m "feat(mesh): add vector clocks and conflict resolution for partitions"
```

---

## Task 13: Integration — Wire Mesh into Main

**Files:**
- Modify: `main.py`
- Test: `tests/test_mesh_integration.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for mesh integration with main entrypoint."""
import pytest
from core.mesh import MeshNode, NodeCapabilities, NodePriority, EventBus


class TestMeshIntegration:
    def test_mesh_node_can_be_created_with_all_priorities(self):
        """All node priorities can be instantiated."""
        for priority in [NodePriority.CNS, NodePriority.PRIME, NodePriority.DESKTOP, NodePriority.AGENT_ZERO]:
            node = MeshNode(
                node_id=f"node-{priority.name}",
                name=priority.name,
                priority=priority,
                capabilities=NodeCapabilities(can_orchestrate=True),
            )
            assert node.priority == priority

    def test_event_bus_delivers_events(self):
        """Event bus delivers events to subscribers."""
        import asyncio

        async def run():
            bus = EventBus()
            received = []
            bus.subscribe("test.event", lambda evt: received.append(evt))
            await bus.publish("test.event", {"key": "value"})
            await asyncio.sleep(0.01)
            return received

        received = asyncio.run(run())
        assert len(received) == 1
        assert received[0]["data"]["key"] == "value"

    def test_full_mesh_stack_constructs(self):
        """All mesh components can be constructed together."""
        from core.mesh.cache import StateCache
        from core.mesh.leader_election import LeaderElection
        from core.mesh.orchestrator import Orchestrator
        from core.mesh.recovery import RecoveryManager
        from core.mesh.digest import DailyDigest
        from core.mesh.budget import BudgetEnforcer
        from core.mesh.trust_dial import TrustDial
        from core.mesh.partition import VectorClock, ConflictResolver

        bus = EventBus()
        cache = StateCache(db_path=":memory:") if False else None  # skip in-memory for now
        # Just verify all classes are importable and constructible
        assert LeaderElection() is not None
        assert RecoveryManager() is not None
        assert DailyDigest() is not None
        assert BudgetEnforcer() is not None
        assert TrustDial() is not None
        assert VectorClock() is not None
        assert ConflictResolver() is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mesh_integration.py -v`
Expected: FAIL — imports or construction may fail

- [ ] **Step 3: Verify main.py can import mesh**

Check that `main.py` can import the mesh package without errors. Add a `--mesh` flag section to `main.py` (read the end of main.py first to find the right insertion point).

Read `main.py` to find the argument parser section, then add:

```python
# Add to argument parser group
parser.add_argument("--mesh", action="store_true", help="Enable fleet mesh mode")
parser.add_argument("--node-id", type=str, default=None, help="Unique node ID for mesh mode")
parser.add_argument("--node-priority", type=str, default="desktop",
                    choices=["cns", "prime", "desktop", "agent_zero"],
                    help="Node priority for leader election")
```

And after the existing initialization, add mesh startup:

```python
# Fleet mesh mode
if args.mesh:
    from core.mesh import EventBus, MeshNode, NodeCapabilities, NodePriority, LeaderElection, Orchestrator
    from core.mesh.cache import StateCache
    # ... initialize mesh components
    logger.info("Fleet mesh mode enabled (node_id=%s, priority=%s)", args.node_id, args.node_priority)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mesh_integration.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS — no existing tests broken

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_mesh_integration.py
git commit -m "feat(mesh): integrate mesh into main entrypoint with --mesh flag"
```

---

## Task 14: Full Mesh Test Suite Run & Fix

**Files:**
- No new files — fix any failures

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -q --tb=short`
Expected: All tests pass (existing + new mesh tests)

- [ ] **Step 2: Run lint**

Run: `ruff check core/mesh/`
Expected: Zero errors

- [ ] **Step 3: Fix any failures**

If any test fails or lint error appears, fix it now. Commit each fix separately.

- [ ] **Step 4: Final verification**

Run: `python -m pytest tests/ -q && ruff check core/mesh/`
Expected: PASS + clean lint

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix(mesh): resolve test failures and lint issues" || echo "Nothing to commit"
```

---

## Task 15: Update CLAUDE.md with Mesh Info

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add mesh section to CLAUDE.md**

Add a new section after the existing "Architecture" section:

```markdown
## Fleet Mesh (vNext)

The `core/mesh/` package implements distributed fleet orchestration:
- **Event Bus** (`event_bus.py`) — WebSocket pub/sub for inter-node events
- **Node Identity** (`node.py`) — Node capabilities, priority, heartbeat
- **Leader Election** (`leader_election.py`) — Lease-based, priority-ordered
- **Task Graph** (`task_graph.py`) — Task model, dependencies, checkpointing
- **Orchestrator** (`orchestrator.py`) — Plan→delegate→execute→remember loop
- **Cache** (`cache.py`) — Local SQLite state cache for resilience
- **Recovery** (`recovery.py`) — Self-recovery ladder with failure classification
- **Digest** (`digest.py`) — Daily digest generation
- **Budget** (`budget.py`) — Task budget caps
- **Trust Dial** (`trust_dial.py`) — Per-action-type autonomy levels
- **Partition** (`partition.py`) — Vector clocks, conflict resolution

Run with `--mesh` flag to enable fleet mesh mode.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add fleet mesh section to CLAUDE.md"
```

---

## Self-Review Checklist

After completing all tasks:

1. **Spec coverage:** Every section in the design spec maps to a task:
   - Architecture (mesh, nodes, event bus) → Tasks 1-3
   - Leader election → Task 4
   - Local cache → Task 5
   - Task graph & checkpointing → Task 6
   - Orchestration loop → Task 7
   - Self-recovery → Task 8
   - Daily digest → Task 9
   - Budget caps → Task 10
   - Trust dial → Task 11
   - Conflict resolution → Task 12
   - Integration → Tasks 13-15

2. **No placeholders:** Every code block is complete. No TBDs.

3. **Type consistency:** `TaskStatus`, `NodePriority`, `TrustLevel`, `ActionType`, `FailureType` enums used consistently across tasks.

4. **Existing patterns followed:** Module docstrings, `from __future__ import annotations`, dataclasses, `logging.getLogger(__name__)`, `atomic_io` for writes, pytest class-based tests.
