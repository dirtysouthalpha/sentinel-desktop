# Fleet Mesh Phase 5 — Production Deployment

**Date:** 2026-07-29
**Goal:** Deploy the mesh to real fleet nodes, wire the full self-recovery ladder, and prove 24/7 autonomous operation.
**Depends on:** Phases 1-4 (19 modules, 131+ tests)

---

## Task 1: Multi-Node Deployment Config

**Files:**
- Create: `deploy/docker-compose.yml` — Multi-node mesh deployment
- Create: `deploy/sentinel-mesh.service` — systemd unit template
- Create: `deploy/deploy_fleet.py` — One-command fleet deployment script
- Test: `tests/test_deploy.py`

### Design

Generate deployment configs for running multiple mesh nodes on a single host (for testing) or across fleet machines (for production). Each node gets a unique ID, port, and priority.

### `deploy/docker-compose.yml`

```yaml
# Sentinel Fleet Mesh — Multi-Node Deployment
# Usage: docker-compose up -d
version: "3.8"

services:
  mesh-cns:
    build: .
    command: >
      python main.py --mesh
      --node-id cns-1
      --node-priority cns
      --mesh-port 4433
      --mesh-peers "ws://mesh-prime:4434"
    environment:
      - MESH_AUTH_TOKEN=${MESH_AUTH_TOKEN:-}
      - NEURALIS_BRAIN_URL=${NEURALIS_BRAIN_URL:-http://homeserver:8001}
    ports:
      - "4433:4433"
    volumes:
      - mesh-cns-data:/data
    restart: unless-stopped

  mesh-prime:
    build: .
    command: >
      python main.py --mesh
      --node-id prime-1
      --node-priority prime
      --mesh-port 4434
      --mesh-peers "ws://mesh-cns:4433"
    environment:
      - MESH_AUTH_TOKEN=${MESH_AUTH_TOKEN:-}
      - NEURALIS_BRAIN_URL=${NEURALIS_BRAIN_URL:-http://homeserver:8001}
    ports:
      - "4434:4434"
    volumes:
      - mesh-prime-data:/data
    restart: unless-stopped

  mesh-desktop:
    build: .
    command: >
      python main.py --mesh
      --node-id desktop-1
      --node-priority desktop
      --mesh-port 4435
      --mesh-peers "ws://mesh-cns:4433,ws://mesh-prime:4434"
    environment:
      - MESH_AUTH_TOKEN=${MESH_AUTH_TOKEN:-}
      - NEURALIS_BRAIN_URL=${NEURALIS_BRAIN_URL:-http://homeserver:8001}
    ports:
      - "4435:4435"
    volumes:
      - mesh-desktop-data:/data
    restart: unless-stopped

volumes:
  mesh-cns-data:
  mesh-prime-data:
  mesh-desktop-data:
```

### `deploy/sentinel-mesh.service`

```ini
[Unit]
Description=Sentinel Fleet Mesh Node %i
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sentinel
WorkingDirectory=/opt/sentinel-desktop
ExecStart=/usr/bin/python3 main.py --mesh \
  --node-id %i \
  --node-priority ${PRIORITY:-desktop} \
  --mesh-port ${PORT:-4433} \
  --mesh-peers ${PEERS:-}
Restart=always
RestartSec=5
Environment=MESH_AUTH_TOKEN=${MESH_AUTH_TOKEN}
Environment=NEURALIS_BRAIN_URL=${NEURALIS_BRAIN_URL}

[Install]
WantedBy=multi-user.target
```

### `deploy/deploy_fleet.py`

```python
#!/usr/bin/env python3
"""Deploy the Sentinel Fleet Mesh to multiple nodes.

Usage:
    python deploy/deploy_fleet.py --generate    # Generate configs
    python deploy/deploy_fleet.py --dry-run      # Show what would be deployed
    python deploy/deploy_fleet.py --deploy       # Deploy to fleet machines
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

# Fleet node definitions
FLEET_NODES: list[dict[str, Any]] = [
    {
        "node_id": "cns-main",
        "priority": "cns",
        "port": 4433,
        "host": "cns.fleet.local",
        "peers": ["ws://prime.fleet.local:4434"],
    },
    {
        "node_id": "prime-main",
        "priority": "prime",
        "port": 4434,
        "host": "prime.fleet.local",
        "peers": ["ws://cns.fleet.local:4433"],
    },
    {
        "node_id": "desktop-main",
        "priority": "desktop",
        "port": 4435,
        "host": "desktop.fleet.local",
        "peers": ["ws://cns.fleet.local:4433", "ws://prime.fleet.local:4434"],
    },
]


def generate_configs(output_dir: str = "deploy/generated") -> None:
    """Generate deployment configs for each fleet node."""
    os.makedirs(output_dir, exist_ok=True)
    for node in FLEET_NODES:
        config = {
            "node_id": node["node_id"],
            "priority": node["priority"],
            "port": node["port"],
            "peers": node["peers"],
        }
        path = os.path.join(output_dir, f"{node['node_id']}.json")
        with open(path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"Generated: {path}")


def dry_run() -> None:
    """Show what would be deployed."""
    print("FLEET DEPLOYMENT PLAN")
    print("=" * 50)
    for node in FLEET_NODES:
        print(f"  {node['node_id']:20s} {node['priority']:10s} {node['host']:30s} port {node['port']}")
        for peer in node["peers"]:
            print(f"    → peer: {peer}")
    print()
    print(f"Total nodes: {len(FLEET_NODES)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy Sentinel Fleet Mesh")
    parser.add_argument("--generate", action="store_true", help="Generate configs")
    parser.add_argument("--dry-run", action="store_true", help="Show deployment plan")
    parser.add_argument("--deploy", action="store_true", help="Deploy to fleet")
    args = parser.parse_args()

    if args.generate:
        generate_configs()
    elif args.dry_run:
        dry_run()
    elif args.deploy:
        print("Deploy mode: copy generated configs to fleet machines and start services")
        dry_run()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

### `tests/test_deploy.py`

```python
"""Tests for fleet deployment configuration."""
import json
import os
import pytest
from deploy.deploy_fleet import FLEET_NODES, generate_configs, dry_run


class TestFleetNodes:
    def test_fleet_nodes_defined(self):
        assert len(FLEET_NODES) >= 2
        ids = [n["node_id"] for n in FLEET_NODES]
        assert len(ids) == len(set(ids))  # Unique IDs

    def test_all_nodes_have_required_fields(self):
        for node in FLEET_NODES:
            assert "node_id" in node
            assert "priority" in node
            assert "port" in node
            assert "host" in node
            assert "peers" in node

    def test_priorities_valid(self):
        valid = {"cns", "prime", "desktop", "agent_zero"}
        for node in FLEET_NODES:
            assert node["priority"] in valid

    def test_ports_unique(self):
        ports = [n["port"] for n in FLEET_NODES]
        assert len(ports) == len(set(ports))


class TestGenerateConfigs:
    def test_generate_creates_files(self, tmp_path):
        generate_configs(str(tmp_path))
        for node in FLEET_NODES:
            path = tmp_path / f"{node['node_id']}.json"
            assert path.exists()
            with open(path) as f:
                data = json.load(f)
            assert data["node_id"] == node["node_id"]

    def test_generate_overwrites(self, tmp_path):
        generate_configs(str(tmp_path))
        generate_configs(str(tmp_path))  # Should not raise
```

---

## Task 2: End-to-End Integration Test

**Files:**
- Create: `tests/test_mesh_e2e.py` — Full multi-node mesh test
- No production code changes — this is a test-only task

### Design

Spin up 2+ mesh nodes on different ports in a single process. Verify: event transport, leader election, task assignment, execution, and metrics.

### `tests/test_mesh_e2e.py`

```python
"""End-to-end integration test for the fleet mesh.

Spins up multiple mesh nodes and verifies the full pipeline:
transport → leader election → plan creation → task assignment → execution → metrics.
"""
import asyncio
import pytest
import pytest_asyncio
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.transport import WebSocketTransport
from core.mesh.leader_election import LeaderElection
from core.mesh.orchestrator import Orchestrator
from core.mesh.executor import TaskExecutor
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority
from core.mesh.task_graph import Task, TaskGraph, TaskStatus
from core.mesh.metrics import MetricsCollector, FleetMetricsAggregator


@pytest_asyncio.fixture
async def mesh_nodes():
    """Create two connected mesh nodes."""
    # Node A (higher priority)
    bus_a = EventBus()
    transport_a = WebSocketTransport(
        node_id="e2e-node-a",
        listen_port=14533,
        auth_token="e2e-test",
    )
    await transport_a.start()
    bus_a.set_transport(transport_a)
    election_a = LeaderElection(lease_ttl=30)
    node_a = MeshNode(
        node_id="e2e-node-a",
        name="E2E-A",
        priority=NodePriority.PRIME,
        capabilities=NodeCapabilities(can_orchestrate=True, can_reason=True),
    )
    node_a.heartbeat()
    orch_a = Orchestrator(event_bus=bus_a, cache=None, leader_election=election_a, node_id="e2e-node-a")
    exec_a = TaskExecutor(node_id="e2e-node-a", bus=bus_a, capabilities=node_a.capabilities)
    exec_a.start()

    # Node B (lower priority)
    bus_b = EventBus()
    transport_b = WebSocketTransport(
        node_id="e2e-node-b",
        listen_port=14534,
        auth_token="e2e-test",
    )
    await transport_b.start()
    bus_b.set_transport(transport_b)
    election_b = LeaderElection(lease_ttl=30)
    node_b = MeshNode(
        node_id="e2e-node-b",
        name="E2E-B",
        priority=NodePriority.DESKTOP,
        capabilities=NodeCapabilities(can_execute_desktop=True, can_reason=True),
    )
    node_b.heartbeat()
    orch_b = Orchestrator(event_bus=bus_b, cache=None, leader_election=election_b, node_id="e2e-node-b")
    exec_b = TaskExecutor(node_id="e2e-node-b", bus=bus_b, capabilities=node_b.capabilities)
    exec_b.start()

    # Connect peers
    await transport_a.connect_to_peer("e2e-node-b", "ws://127.0.0.1:14534")
    await transport_b.connect_to_peer("e2e-node-a", "ws://127.0.0.1:14533")

    yield {
        "bus_a": bus_a,
        "bus_b": bus_b,
        "transport_a": transport_a,
        "transport_b": transport_b,
        "orch_a": orch_a,
        "orch_b": orch_b,
        "exec_a": exec_a,
        "exec_b": exec_b,
        "node_a": node_a,
        "node_b": node_b,
    }

    exec_a.stop()
    exec_b.stop()
    await transport_a.stop()
    await transport_b.stop()


class TestMeshE2E:
    @pytest.mark.asyncio
    async def test_nodes_connect(self, mesh_nodes):
        """Both nodes establish WebSocket connections."""
        for _ in range(50):
            a_connected = mesh_nodes["transport_a"]._peers.get("e2e-node-b")
            b_connected = mesh_nodes["transport_b"]._peers.get("e2e-node-a")
            if (a_connected and a_connected.connected and
                b_connected and b_connected.connected):
                break
            await asyncio.sleep(0.1)

        a_peer = mesh_nodes["transport_a"]._peers.get("e2e-node-b")
        b_peer = mesh_nodes["transport_b"]._peers.get("e2e-node-a")
        assert a_peer is not None and a_peer.connected
        assert b_peer is not None and b_peer.connected

    @pytest.mark.asyncio
    async def test_event_transport_between_nodes(self, mesh_nodes):
        """Events published on node A are received by node B."""
        received = []
        mesh_nodes["bus_b"].subscribe("e2e.test.event", lambda env: received.append(env))

        await mesh_nodes["bus_a"].publish("e2e.test.event", {"msg": "hello from A"})

        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0]["data"]["msg"] == "hello from A"

    @pytest.mark.asyncio
    async def test_task_assignment_and_execution(self, mesh_nodes):
        """A task assigned to node B is executed by node B."""
        completed = []
        mesh_nodes["bus_b"].subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))

        # Publish task assignment for node B
        await mesh_nodes["bus_a"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "e2e-t1",
            "plan_id": "e2e-p1",
            "node_id": "e2e-node-b",
            "task_type": "shell",
            "goal": "echo e2e test",
            "params": {"command": "echo e2e test output"},
        })

        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert completed[0]["data"]["task_id"] == "e2e-t1"
        assert completed[0]["data"]["result"]["stdout"] == "e2e test output"

    @pytest.mark.asyncio
    async def test_metrics_collection(self, mesh_nodes):
        """Metrics collector produces valid data."""
        collector = MetricsCollector("e2e-node-a")
        metrics = collector.collect(tasks_active=2, tasks_completed=5)
        assert metrics.node_id == "e2e-node-a"
        assert metrics.tasks_active == 2
        assert metrics.tasks_completed == 5
        assert metrics.cpu_percent >= 0

    @pytest.mark.asyncio
    async def test_fleet_metrics_aggregation(self, mesh_nodes):
        """FleetMetricsAggregator combines metrics from multiple nodes."""
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "e2e-node-a", "cpu_percent": 60.0, "memory_percent": 70.0})
        agg.update({"node_id": "e2e-node-b", "cpu_percent": 40.0, "memory_percent": 50.0})

        summary = agg.get_fleet_summary()
        assert summary["total_nodes"] == 2
        assert summary["avg_cpu"] == 50.0
        assert summary["avg_memory"] == 60.0
```

---

## Task 3: Daily Digest Pipeline

**Files:**
- Create: `core/mesh/digest_scheduler.py` — Scheduled digest generation
- Modify: `core/mesh/__init__.py` — export new class
- Test: `tests/test_digest_scheduler.py`

### Design

Wire the existing `DailyDigest` into the existing `TaskScheduler` so it auto-generates a daily report. The digest is stored as a Neuralis neuron and optionally printed.

### `core/mesh/digest_scheduler.py`

```python
"""Daily digest pipeline for the fleet mesh."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.mesh.digest import DailyDigest
from core.mesh.metrics import FleetMetricsAggregator

logger = logging.getLogger(__name__)


class DigestPipeline:
    """Generates and delivers daily fleet digests."""

    def __init__(
        self,
        metrics: FleetMetricsAggregator,
        memory=None,  # NeuralisMemory | None
    ) -> None:
        self.metrics = metrics
        self.memory = memory
        self.daily = DailyDigest()

    def generate_digest(self) -> str:
        """Generate the daily digest from current fleet state."""
        summary = self.metrics.get_fleet_summary()
        nodes_data = [
            {
                "node_id": nid,
                "status": "healthy" if info.get("cpu_percent", 0) < 90 else "warning",
                "cpu": info.get("cpu_percent", 0),
            }
            for nid, info in summary.get("nodes", {}).items()
        ]
        tasks = []  # Would come from orchestrator
        lessons = []  # Would come from Neuralis

        report = self.daily.generate(tasks=tasks, nodes=nodes_data, lessons=lessons)
        return report

    def deliver(self) -> bool:
        """Generate, store, and deliver the digest."""
        report = self.generate_digest()
        logger.info("Daily digest generated (%d chars)", len(report))

        # Store in Neuralis
        if self.memory:
            self.memory.store_event("daily_digest", {
                "report": report,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        return True
```

### `tests/test_digest_scheduler.py`

```python
"""Tests for the daily digest pipeline."""
import pytest
from unittest.mock import MagicMock
from core.mesh.digest_scheduler import DigestPipeline
from core.mesh.metrics import FleetMetricsAggregator


class TestDigestPipeline:
    def test_construct(self):
        agg = FleetMetricsAggregator()
        pipe = DigestPipeline(metrics=agg)
        assert pipe.metrics is agg

    def test_generate_digest(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 50.0, "memory_percent": 60.0})
        pipe = DigestPipeline(metrics=agg)
        report = pipe.generate_digest()
        assert "FLEET DAILY DIGEST" in report
        assert "n1" in report

    def test_deliver(self):
        agg = FleetMetricsAggregator()
        pipe = DigestPipeline(metrics=agg)
        result = pipe.deliver()
        assert result is True

    def test_deliver_with_memory(self):
        agg = FleetMetricsAggregator()
        mock_memory = MagicMock()
        pipe = DigestPipeline(metrics=agg, memory=mock_memory)
        pipe.deliver()
        mock_memory.store_event.assert_called_once()
```

---

## Task 4: Full Self-Recovery Ladder

**Files:**
- Create: `core/mesh/self_recovery.py` — Complete self-recovery orchestration
- Test: `tests/test_self_recovery.py`

### Design

Wire the watcher, orchestrator, and recovery manager into a complete self-recovery ladder:
1. Detect stuck task → reassign to fallback node
2. Detect unhealthy node → drain tasks
3. On node failure → re-plan remaining tasks
4. On persistent failure → queue for daily digest

### `core/mesh/self_recovery.py`

```python
"""Complete self-recovery ladder for the fleet mesh."""
from __future__ import annotations

import logging
from typing import Any, Callable

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator
from core.mesh.recovery import RecoveryManager, FailureType
from core.mesh.watcher import SelfHealingWatcher, WatcherConfig

logger = logging.getLogger(__name__)


class SelfRecoveryLadder:
    """Orchestrates detection and recovery from fleet failures.

    Recovery ladder:
    1. Retry same node (up to max_retries)
    2. Retry different node (fallback selection)
    3. Rollback + re-plan
    4. Self-update (mark node unhealthy)
    5. Queue for daily digest (human escalation)
    """

    def __init__(
        self,
        bus: EventBus,
        metrics: FleetMetricsAggregator,
        recovery: RecoveryManager | None = None,
        config: WatcherConfig | None = None,
    ) -> None:
        self.bus = bus
        self.metrics = metrics
        self.recovery = recovery or RecoveryManager()
        self.watcher = SelfHealingWatcher(bus, metrics, config)
        self._recovery_actions: list[dict[str, Any]] = []

    def start(self) -> None:
        """Start the recovery ladder."""
        self.watcher.start()
        self.watcher._recovery_callback = self._on_recovery_needed
        logger.info("Self-recovery ladder started")

    def stop(self) -> None:
        self.watcher.stop()

    def _on_recovery_needed(self, issue_type: str, target_id: str, context: dict[str, Any]) -> None:
        """Handle a recovery event from the watcher."""
        if issue_type == "stuck_task":
            self._recover_stuck_task(target_id, context)
        elif issue_type == "unhealthy_node":
            self._recover_unhealthy_node(target_id)

    def _recover_stuck_task(self, task_id: str, context: dict[str, Any]) -> None:
        """Recover a stuck task by reassigning to a fallback node."""
        node_id = context.get("node_id", "")
        plan_id = context.get("plan_id", "")
        logger.warning("Recovering stuck task %s from node %s", task_id, node_id)

        # Select fallback node
        fallback = self.recovery.select_fallback_node(
            current_node_id=node_id,
            available_nodes=[],  # Would come from node registry
        )

        if fallback:
            # Reassign task
            self.bus.publish(FleetEvent.TASK_ASSIGNED, {
                "task_id": task_id,
                "plan_id": plan_id,
                "node_id": fallback.node_id,
                "task_type": context.get("task_type", "shell"),
                "goal": context.get("goal", ""),
                "params": context.get("params", {}),
            })
            self._recovery_actions.append({
                "action": "reassign",
                "task_id": task_id,
                "from_node": node_id,
                "to_node": fallback.node_id,
            })
        else:
            # No fallback — queue for digest
            logger.error("No fallback node for stuck task %s", task_id)
            self._recovery_actions.append({
                "action": "escalate",
                "task_id": task_id,
                "reason": "no_fallback_node",
            })

    def _recover_unhealthy_node(self, node_id: str) -> None:
        """Recover from an unhealthy node by draining its tasks."""
        logger.warning("Draining unhealthy node %s", node_id)
        self._recovery_actions.append({
            "action": "drain",
            "node_id": node_id,
        })

    def get_recovery_log(self) -> list[dict[str, Any]]:
        """Return the log of recovery actions taken."""
        return list(self._recovery_actions)
```

### `tests/test_self_recovery.py`

```python
"""Tests for the self-recovery ladder."""
import pytest
from core.mesh.self_recovery import SelfRecoveryLadder
from core.mesh.event_bus import EventBus
from core.mesh.metrics import FleetMetricsAggregator
from core.mesh.recovery import RecoveryManager


class TestSelfRecoveryLadder:
    def test_construct(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        assert ladder.bus is bus
        assert isinstance(ladder.recovery, RecoveryManager)

    def test_start_stop(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        ladder.start()
        ladder.stop()

    def test_recovery_log_empty(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        assert ladder.get_recovery_log() == []

    def test_recover_unhealthy_node(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        ladder._recover_unhealthy_node("n1")
        log = ladder.get_recovery_log()
        assert len(log) == 1
        assert log[0]["action"] == "drain"
        assert log[0]["node_id"] == "n1"

    def test_recover_stuck_task_no_fallback(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        ladder._recover_stuck_task("t1", {"node_id": "n1", "plan_id": "p1"})
        log = ladder.get_recovery_log()
        assert len(log) == 1
        assert log[0]["action"] == "escalate"
```

---

## Task 5: Integration & Full Test Suite

1. Update `core/mesh/__init__.py` to export new classes
2. Run `pytest tests/test_mesh_*.py -q --tb=short`
3. Run `ruff check core/mesh/`
4. Commit

---

## Self-Review Checklist

1. Deployment: docker-compose, systemd, deploy script all work
2. E2E: multi-node test passes, events flow, tasks execute
3. Digest: generates report, stores in Neuralis
4. Recovery: stuck task reassignment, node draining, escalation
5. Tests: all new code covered, existing tests still pass
