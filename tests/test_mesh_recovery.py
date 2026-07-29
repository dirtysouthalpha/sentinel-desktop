"""Tests for the self-recovery ladder."""
import pytest
from core.mesh.recovery import RecoveryManager, FailureType
from core.mesh.task_graph import Task, TaskGraph, TaskStatus
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority


def make_node(node_id, priority=NodePriority.DESKTOP):
    return MeshNode(node_id=node_id, name=node_id, priority=priority,
                    capabilities=NodeCapabilities(can_orchestrate=True, can_execute_desktop=True))


class TestRecoveryManager:
    def test_classify_transient_failure(self):
        assert RecoveryManager().classify_failure("Connection timeout") == FailureType.TRANSIENT

    def test_classify_permanent_failure(self):
        assert RecoveryManager().classify_failure("Authentication failed: invalid token") == FailureType.PERMANENT

    def test_classify_resource_failure(self):
        assert RecoveryManager().classify_failure("No space left on device") == FailureType.RESOURCE

    def test_should_retry_transient(self):
        task = Task(id="t1", type="reasoning", goal="test", retry_count=0, max_retries=3)
        assert RecoveryManager().should_retry(task, FailureType.TRANSIENT) is True

    def test_no_retry_permanent(self):
        task = Task(id="t1", type="reasoning", goal="test", retry_count=0, max_retries=3)
        assert RecoveryManager().should_retry(task, FailureType.PERMANENT) is False

    def test_no_retry_exhausted(self):
        task = Task(id="t1", type="reasoning", goal="test", retry_count=3, max_retries=3)
        assert RecoveryManager().should_retry(task, FailureType.TRANSIENT) is False

    def test_select_fallback_node(self):
        mgr = RecoveryManager()
        n1, n2, n3 = make_node("n1"), make_node("n2"), make_node("n3")
        for n in [n1, n2, n3]:
            n.heartbeat()
        fallback = mgr.select_fallback_node(current_node_id="n1", available_nodes=[n1, n2, n3])
        assert fallback is not None
        assert fallback.node_id != "n1"

    def test_select_fallback_no_alternatives(self):
        mgr = RecoveryManager()
        n1 = make_node("n1")
        n1.heartbeat()
        assert mgr.select_fallback_node(current_node_id="n1", available_nodes=[n1]) is None

    def test_retry_delay_exponential(self):
        mgr = RecoveryManager()
        assert mgr.get_retry_delay(0) == 1.0
        assert mgr.get_retry_delay(1) == 2.0
        assert mgr.get_retry_delay(2) == 4.0
        assert mgr.get_retry_delay(3) == 8.0
