"""Phase 6B: Three-node mesh topology tests."""
from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from typing import Any

import pytest
import pytest_asyncio

from core.mesh.cache import StateCache
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.executor import TaskExecutor
from core.mesh.leader_election import LeaderElection
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority
from core.mesh.orchestrator import Orchestrator
from core.mesh.transport import PeerConnection, WebSocketTransport


async def _wait_for(predicate: Callable[[], bool], *, attempts: int = 200, interval: float = 0.1) -> bool:
    for _ in range(attempts):
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


@pytest_asyncio.fixture
async def three_nodes():
    """Three connected mesh nodes: leader (PRIME), worker1 (DESKTOP), worker2 (AGENT_ZERO)."""
    # Node A (PRIME, port 14611)
    node_a = MeshNode("leader-3", "Leader", NodePriority.PRIME, NodeCapabilities(can_orchestrate=True))
    node_a.heartbeat()
    bus_a = EventBus()
    transport_a = WebSocketTransport(node_id="leader-3", listen_port=14611, auth_token="three-test")
    await transport_a.start()
    bus_a.set_transport(transport_a)
    election_a = LeaderElection(lease_ttl=30)
    cache_a = StateCache(tempfile.mktemp(suffix=".db"))
    orch_a = Orchestrator(event_bus=bus_a, cache=cache_a, leader_election=election_a, node_id="leader-3")
    executor_a = TaskExecutor(node_id="leader-3", bus=bus_a, capabilities=node_a.capabilities)
    executor_a.start()

    # Node B (DESKTOP, port 14612)
    node_b = MeshNode("desktop-3", "Desktop", NodePriority.DESKTOP, NodeCapabilities(can_execute_desktop=True))
    node_b.heartbeat()
    bus_b = EventBus()
    transport_b = WebSocketTransport(node_id="desktop-3", listen_port=14612, auth_token="three-test")
    await transport_b.start()
    bus_b.set_transport(transport_b)
    election_b = LeaderElection(lease_ttl=30)
    cache_b = StateCache(tempfile.mktemp(suffix=".db"))
    orch_b = Orchestrator(event_bus=bus_b, cache=cache_b, leader_election=election_b, node_id="desktop-3")
    executor_b = TaskExecutor(node_id="desktop-3", bus=bus_b, capabilities=node_b.capabilities)
    executor_b.start()

    # Node C (AGENT_ZERO, port 14613)
    node_c = MeshNode("zero-3", "AgentZero", NodePriority.AGENT_ZERO, NodeCapabilities())
    node_c.heartbeat()
    bus_c = EventBus()
    transport_c = WebSocketTransport(node_id="zero-3", listen_port=14613, auth_token="three-test")
    await transport_c.start()
    bus_c.set_transport(transport_c)
    election_c = LeaderElection(lease_ttl=30)
    cache_c = StateCache(tempfile.mktemp(suffix=".db"))
    orch_c = Orchestrator(event_bus=bus_c, cache=cache_c, leader_election=election_c, node_id="zero-3")
    executor_c = TaskExecutor(node_id="zero-3", bus=bus_c, capabilities=node_c.capabilities)
    executor_c.start()

    # Full mesh: A connects to B and C
    await transport_a.connect_to_peer("desktop-3", "ws://127.0.0.1:14612")
    await transport_a.connect_to_peer("zero-3", "ws://127.0.0.1:14613")

    connected_b = await _wait_for(lambda: transport_a._peers.get("desktop-3", PeerConnection("")).connected, attempts=100)
    connected_c = await _wait_for(lambda: transport_a._peers.get("zero-3", PeerConnection("")).connected, attempts=100)
    assert connected_b, "A failed to connect to B"
    assert connected_c, "A failed to connect to C"

    nodes = dict(node_a=node_a, bus_a=bus_a, transport_a=transport_a, election_a=election_a, orch_a=orch_a, executor_a=executor_a,
                 node_b=node_b, bus_b=bus_b, transport_b=transport_b, election_b=election_b, orch_b=orch_b, executor_b=executor_b,
                 node_c=node_c, bus_c=bus_c, transport_c=transport_c, election_c=election_c, orch_c=orch_c, executor_c=executor_c)
    yield nodes

    executor_a.stop(); executor_b.stop(); executor_c.stop()
    await transport_a.stop(); await transport_b.stop(); await transport_c.stop()


class TestThreeNodeMesh:
    @pytest.mark.asyncio
    async def test_all_three_connected(self, three_nodes):
        """All three nodes are connected via the transport layer."""
        assert three_nodes["transport_a"]._peers["desktop-3"].connected
        assert three_nodes["transport_a"]._peers["zero-3"].connected

    @pytest.mark.asyncio
    async def test_event_propagates_to_all(self, three_nodes):
        """Event published on A reaches both B and C."""
        received_b: list = []
        received_c: list = []
        three_nodes["bus_b"].subscribe("test.broadcast", lambda env: received_b.append(env))
        three_nodes["bus_c"].subscribe("test.broadcast", lambda env: received_c.append(env))
        three_nodes["bus_a"].subscribe("test.broadcast", lambda env: None)
        await three_nodes["bus_a"].publish("test.broadcast", {"msg": "all nodes"})
        assert await _wait_for(lambda: len(received_b) > 0 and len(received_c) > 0)
        assert received_b[0]["data"]["msg"] == "all nodes"
        assert received_c[0]["data"]["msg"] == "all nodes"

    @pytest.mark.asyncio
    async def test_task_to_desktop_node(self, three_nodes):
        """Shell task assigned to desktop-3 executes and returns result."""
        completed: list = []
        three_nodes["bus_b"].subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))
        await three_nodes["bus_a"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "desktop-task", "plan_id": "three-plan", "node_id": "desktop-3",
            "task_type": "shell", "goal": "echo from desktop",
            "params": {"command": "echo from desktop"},
        })
        assert await _wait_for(lambda: len(completed) > 0)
        assert completed[0]["data"]["result"]["stdout"] == "from desktop"

    @pytest.mark.asyncio
    async def test_task_to_agent_zero_node(self, three_nodes):
        """Shell task assigned to agent-zero node executes and returns result."""
        completed: list = []
        three_nodes["bus_c"].subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))
        await three_nodes["bus_a"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "zero-task", "plan_id": "three-plan", "node_id": "zero-3",
            "task_type": "shell", "goal": "echo from zero",
            "params": {"command": "echo from zero"},
        })
        assert await _wait_for(lambda: len(completed) > 0)
        assert completed[0]["data"]["result"]["stdout"] == "from zero"
