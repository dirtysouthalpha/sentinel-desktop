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
        # Just verify all classes are importable and constructible
        assert LeaderElection() is not None
        assert RecoveryManager() is not None
        assert DailyDigest() is not None
        assert BudgetEnforcer() is not None
        assert TrustDial() is not None
        assert VectorClock() is not None
        assert ConflictResolver() is not None
