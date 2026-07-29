"""Phase 6A: Prove the mesh does real work end-to-end."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
import pytest_asyncio

import tempfile

from core.mesh.cache import StateCache
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.executor import TaskExecutor
from core.mesh.leader_election import LeaderElection
from core.mesh.metrics import FleetMetricsAggregator, MetricsCollector
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority
from core.mesh.orchestrator import Orchestrator
from core.mesh.task_graph import Task, TaskStatus
from core.mesh.transport import PeerConnection, WebSocketTransport


async def _wait_for(predicate: Callable[[], bool], *, attempts: int = 200, interval: float = 0.1) -> bool:
    for _ in range(attempts):
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


@pytest_asyncio.fixture
async def mesh_pair():
    """Two connected mesh nodes: leader (PRIME, port 14601) and worker (DESKTOP, port 14602)."""
    node_a = MeshNode("leader-1", "Leader", NodePriority.PRIME, NodeCapabilities(can_orchestrate=True, can_reason=True))
    node_a.heartbeat()
    bus_a = EventBus()
    transport_a = WebSocketTransport(node_id="leader-1", listen_port=14601, auth_token="phase6-test")
    await transport_a.start()
    bus_a.set_transport(transport_a)
    election_a = LeaderElection(lease_ttl=30)
    cache_a = StateCache(tempfile.mktemp(suffix=".db"))
    orch_a = Orchestrator(event_bus=bus_a, cache=cache_a, leader_election=election_a, node_id="leader-1")
    executor_a = TaskExecutor(node_id="leader-1", bus=bus_a, capabilities=node_a.capabilities)
    executor_a.start()

    node_b = MeshNode("worker-1", "Worker", NodePriority.DESKTOP, NodeCapabilities(can_execute_desktop=True))
    node_b.heartbeat()
    bus_b = EventBus()
    transport_b = WebSocketTransport(node_id="worker-1", listen_port=14602, auth_token="phase6-test")
    await transport_b.start()
    bus_b.set_transport(transport_b)
    election_b = LeaderElection(lease_ttl=30)
    cache_b = StateCache(tempfile.mktemp(suffix=".db"))
    orch_b = Orchestrator(event_bus=bus_b, cache=cache_b, leader_election=election_b, node_id="worker-1")
    executor_b = TaskExecutor(node_id="worker-1", bus=bus_b, capabilities=node_b.capabilities)
    executor_b.start()

    await transport_a.connect_to_peer("worker-1", "ws://127.0.0.1:14602")
    connected = await _wait_for(lambda: transport_a._peers.get("worker-1", PeerConnection("")).connected, attempts=100)
    assert connected, "Transport failed to connect leader -> worker"

    nodes = dict(node_a=node_a, bus_a=bus_a, transport_a=transport_a, election_a=election_a, orch_a=orch_a, executor_a=executor_a,
                 node_b=node_b, bus_b=bus_b, transport_b=transport_b, election_b=election_b, orch_b=orch_b, executor_b=executor_b)
    yield nodes

    executor_a.stop()
    executor_b.stop()
    await transport_a.stop()
    await transport_b.stop()


class TestPhase6AProof:
    @pytest.mark.asyncio
    async def test_shell_task_cross_node(self, mesh_pair):
        """Shell task assigned to worker executes and returns stdout to leader."""
        completed: list[dict[str, Any]] = []
        mesh_pair["bus_b"].subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))
        await mesh_pair["bus_a"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "shell-1", "plan_id": "proof-1", "node_id": "worker-1",
            "task_type": "shell", "goal": "echo hello from worker",
            "params": {"command": "echo hello from worker"},
        })
        assert await _wait_for(lambda: len(completed) > 0), "TASK_COMPLETED never arrived"
        assert completed[0]["data"]["result"]["stdout"] == "hello from worker"
        assert completed[0]["data"]["node_id"] == "worker-1"

    @pytest.mark.asyncio
    async def test_python_task_cross_node(self, mesh_pair):
        """Python task assigned to worker executes and returns result."""
        completed: list[dict[str, Any]] = []
        mesh_pair["bus_b"].subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))
        await mesh_pair["bus_a"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "py-1", "plan_id": "proof-1", "node_id": "worker-1",
            "task_type": "python", "goal": "compute 2+2",
            "params": {"module": "operator", "function": "add", "args": [2, 2]},
        })
        assert await _wait_for(lambda: len(completed) > 0), "TASK_COMPLETED never arrived"
        assert completed[0]["data"]["result"]["return_value"] == "4"

    @pytest.mark.asyncio
    async def test_failed_task_triggers_retry_event(self, mesh_pair):
        """A shell task that exits non-zero publishes TASK_FAILED with error info."""
        failed: list[dict[str, Any]] = []
        mesh_pair["bus_b"].subscribe(FleetEvent.TASK_FAILED, lambda env: failed.append(env))
        await mesh_pair["bus_a"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "fail-1", "plan_id": "proof-fail", "node_id": "worker-1",
            "task_type": "shell", "goal": "exit 1",
            "params": {"command": "exit 1"},
        })
        assert await _wait_for(lambda: len(failed) > 0), "TASK_FAILED never arrived"
        assert failed[0]["data"]["task_id"] == "fail-1"
        assert "exit 1" in failed[0]["data"]["error"] or "exit code" in failed[0]["data"]["error"].lower()

    @pytest.mark.asyncio
    async def test_metrics_flow_cross_node(self, mesh_pair):
        """NODE_METRICS event from worker is received by leader."""
        received: list[dict[str, Any]] = []
        mesh_pair["bus_a"].subscribe(FleetEvent.NODE_METRICS, lambda env: received.append(env))
        # Worker must have a local subscriber for the event to forward to transport
        mesh_pair["bus_b"].subscribe(FleetEvent.NODE_METRICS, lambda env: None)
        await mesh_pair["bus_b"].publish(FleetEvent.NODE_METRICS, {
            "node_id": "worker-1", "cpu_percent": 42.0, "memory_percent": 58.0,
        })
        assert await _wait_for(lambda: len(received) > 0), "NODE_METRICS never propagated"
        assert received[0]["data"]["node_id"] == "worker-1"
        assert received[0]["data"]["cpu_percent"] == 42.0

    @pytest.mark.asyncio
    async def test_leader_election_priority(self, mesh_pair):
        """PRIME node wins over DESKTOP in leader election."""
        result = mesh_pair["election_a"].elect_leader([mesh_pair["node_a"], mesh_pair["node_b"]])
        assert result is not None, "No leader elected"
        leader_id = mesh_pair["election_a"].current_leader
        assert leader_id == "leader-1", f"Expected leader-1 (PRIME) but got {leader_id}"

    @pytest.mark.asyncio
    async def test_orchestrator_checkpoint(self, mesh_pair):
        """Orchestrator stores plan in cache and can retrieve status."""
        task = Task(id="t1", type="shell", goal="echo test", status=TaskStatus.COMPLETED)
        plan_id = mesh_pair["orch_a"].create_plan("Proof Plan", [task])
        status = mesh_pair["orch_a"].get_plan_status(plan_id)
        assert status is not None
        assert status["total"] == 1
        assert status["completed"] == 1
        assert status["is_complete"] is True
