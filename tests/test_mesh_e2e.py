"""End-to-end integration test for the fleet mesh.

Spins up two real mesh nodes on localhost (A=PRIME, B=DESKTOP) with
WebSocketTransport and verifies the full pipeline:
  1. Events published on A are received by B.
  2. A shell task assigned to B is executed and TASK_COMPLETED is published.
  3. MetricsCollector and FleetMetricsAggregator produce correct summaries.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
import pytest_asyncio

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.executor import TaskExecutor
from core.mesh.leader_election import LeaderElection
from core.mesh.metrics import FleetMetricsAggregator, MetricsCollector
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority
from core.mesh.orchestrator import Orchestrator
from core.mesh.transport import PeerConnection, WebSocketTransport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _wait_for(predicate: Callable[[], bool], *, attempts: int = 100, interval: float = 0.1) -> bool:
    """Poll *predicate* until true or *attempts* exhausted. Returns final value."""
    for _ in range(attempts):
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mesh_nodes():
    """Create and connect two mesh nodes: A (PRIME, port 14533) and B (DESKTOP, port 14534).

    Yields a dict with all constructed objects. Teardown stops executors and
    transports in reverse order.
    """
    # --- Node A (PRIME) ---------------------------------------------------
    node_a = MeshNode(
        node_id="node-a",
        name="Prime Node",
        priority=NodePriority.PRIME,
        capabilities=NodeCapabilities(can_orchestrate=True, can_reason=True),
    )
    node_a.heartbeat()

    bus_a = EventBus()
    transport_a = WebSocketTransport(
        node_id="node-a",
        listen_port=14533,
        auth_token="e2e-test",
    )
    await transport_a.start()
    bus_a.set_transport(transport_a)

    election_a = LeaderElection(lease_ttl=30)
    orch_a = Orchestrator(
        event_bus=bus_a,
        cache=None,
        leader_election=election_a,
        node_id="node-a",
    )
    executor_a = TaskExecutor(
        node_id="node-a",
        bus=bus_a,
        capabilities=node_a.capabilities,
    )
    executor_a.start()

    # --- Node B (DESKTOP) -------------------------------------------------
    node_b = MeshNode(
        node_id="node-b",
        name="Desktop Node",
        priority=NodePriority.DESKTOP,
        capabilities=NodeCapabilities(can_execute_desktop=True),
    )
    node_b.heartbeat()

    bus_b = EventBus()
    transport_b = WebSocketTransport(
        node_id="node-b",
        listen_port=14534,
        auth_token="e2e-test",
    )
    await transport_b.start()
    bus_b.set_transport(transport_b)

    election_b = LeaderElection(lease_ttl=30)
    orch_b = Orchestrator(
        event_bus=bus_b,
        cache=None,
        leader_election=election_b,
        node_id="node-b",
    )
    executor_b = TaskExecutor(
        node_id="node-b",
        bus=bus_b,
        capabilities=node_b.capabilities,
    )
    executor_b.start()

    # --- Connect A -> B ---------------------------------------------------
    await transport_a.connect_to_peer("node-b", "ws://127.0.0.1:14534")
    connected = await _wait_for(
        lambda: transport_a._peers.get("node-b", PeerConnection("")).connected,
        attempts=100,
    )
    assert connected, "Transport A failed to connect to Transport B"

    nodes = {
        "node_a": node_a,
        "bus_a": bus_a,
        "transport_a": transport_a,
        "orch_a": orch_a,
        "executor_a": executor_a,
        "node_b": node_b,
        "bus_b": bus_b,
        "transport_b": transport_b,
        "orch_b": orch_b,
        "executor_b": executor_b,
    }
    yield nodes

    # --- Teardown ---------------------------------------------------------
    executor_a.stop()
    executor_b.stop()
    await transport_a.stop()
    await transport_b.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMeshE2E:
    """End-to-end mesh pipeline tests using two real connected nodes."""

    @pytest.mark.asyncio
    async def test_events_propagate_a_to_b(self, mesh_nodes):
        """An event published on A is received by B across the WebSocket transport."""
        received: list[dict[str, Any]] = []

        # B subscribes to the event type.
        mesh_nodes["bus_b"].subscribe("test.hello", lambda env: received.append(env))

        # A must also have a local subscriber, otherwise EventBus.publish
        # returns early without forwarding to the transport layer.
        mesh_nodes["bus_a"].subscribe("test.hello", lambda env: None)

        await mesh_nodes["bus_a"].publish("test.hello", {"msg": "hi from A"})

        arrived = await _wait_for(lambda: len(received) > 0, attempts=100)
        assert arrived, "Event published on A was never received by B"

        assert received[0]["type"] == "test.hello"
        assert received[0]["data"]["msg"] == "hi from A"
        assert "event_id" in received[0]
        assert "timestamp" in received[0]

    @pytest.mark.asyncio
    async def test_shell_task_executed_on_b(self, mesh_nodes):
        """A shell task assigned to B is executed and TASK_COMPLETED is published."""
        completed: list[dict[str, Any]] = []
        mesh_nodes["bus_b"].subscribe(
            FleetEvent.TASK_COMPLETED, lambda env: completed.append(env)
        )

        # Publish TASK_ASSIGNED targeting node-b. A's executor is also
        # subscribed to TASK_ASSIGNED, which is what triggers transport
        # forwarding; A's executor will ignore it because node_id != "node-a".
        await mesh_nodes["bus_a"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "task-e2e-1",
            "plan_id": "plan-e2e",
            "node_id": "node-b",
            "task_type": "shell",
            "goal": "echo e2e test output",
            "params": {"command": "echo e2e test output"},
        })

        arrived = await _wait_for(lambda: len(completed) > 0, attempts=200)
        assert arrived, "TASK_COMPLETED was never published after shell task assignment"

        payload = completed[0]["data"]
        assert payload["task_id"] == "task-e2e-1"
        assert payload["node_id"] == "node-b"
        assert payload["result"]["stdout"] == "e2e test output"
        assert payload["result"]["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_metrics_collector_and_aggregator(self, mesh_nodes):
        """MetricsCollector collects node metrics; FleetMetricsAggregator summarizes them."""
        collector = MetricsCollector("node-b")

        metrics = collector.collect(tasks_active=2, tasks_completed=5)
        assert metrics.node_id == "node-b"
        assert metrics.tasks_active == 2
        assert metrics.tasks_completed == 5
        # cpu_percent should be a real value when psutil is available, else 0.
        assert metrics.cpu_percent >= 0.0
        assert metrics.memory_percent >= 0.0

        # Aggregator combines metrics from multiple nodes.
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 60.0, "memory_percent": 70.0})
        agg.update({"node_id": "n2", "cpu_percent": 40.0, "memory_percent": 50.0})

        summary = agg.get_fleet_summary()
        assert summary["total_nodes"] == 2
        assert summary["avg_cpu"] == 50.0
        assert summary["avg_memory"] == 60.0
        assert summary["total_tasks_active"] == 0
        assert summary["total_tasks_completed"] == 0

        # Healthy-node count: both nodes are under the 90% thresholds.
        assert summary["healthy_nodes"] == 2
