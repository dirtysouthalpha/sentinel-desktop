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

class TestNodePriority:
    def test_priority_ordering(self):
        assert NodePriority.CNS > NodePriority.PRIME
        assert NodePriority.PRIME > NodePriority.DESKTOP
        assert NodePriority.DESKTOP > NodePriority.AGENT_ZERO
        assert NodePriority.NEURALIS == -1

class TestMeshNode:
    def test_node_creation(self):
        caps = NodeCapabilities(can_orchestrate=True)
        node = MeshNode(node_id="test-1", name="test-node", priority=NodePriority.PRIME, capabilities=caps)
        assert node.node_id == "test-1"
        assert node.status == "initializing"

    def test_heartbeat_updates_timestamp(self):
        node = MeshNode(node_id="test-2", name="test", priority=NodePriority.DESKTOP, capabilities=NodeCapabilities())
        assert node.last_heartbeat is None
        node.heartbeat()
        assert node.last_heartbeat is not None

    def test_is_alive_within_threshold(self):
        node = MeshNode(node_id="test-3", name="test", priority=NodePriority.DESKTOP, capabilities=NodeCapabilities())
        node.heartbeat()
        assert node.is_alive(timeout_seconds=30) is True

    def test_is_alive_expired(self):
        node = MeshNode(node_id="test-4", name="test", priority=NodePriority.DESKTOP, capabilities=NodeCapabilities())
        node.last_heartbeat = time.time() - 60
        assert node.is_alive(timeout_seconds=30) is False
