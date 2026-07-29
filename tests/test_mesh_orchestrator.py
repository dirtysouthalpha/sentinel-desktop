"""Tests for the orchestration loop."""
import pytest
from core.mesh.orchestrator import Orchestrator
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.task_graph import Task, TaskGraph, TaskStatus
from core.mesh.leader_election import LeaderElection
from core.mesh.cache import StateCache
import os
import tempfile


def make_orchestrator(tmp_dir):
    bus = EventBus()
    cache = StateCache(db_path=os.path.join(tmp_dir, "cache.db"))
    election = LeaderElection(lease_ttl=30)
    return Orchestrator(event_bus=bus, cache=cache, leader_election=election, node_id="test-leader"), bus, cache


class TestOrchestrator:
    def test_create_plan(self, tmp_path):
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test goal")
        plan_id = orch.create_plan("test plan", [task])
        assert plan_id is not None
        assert orch.get_plan(plan_id) is not None

    def test_assign_task_to_node(self, tmp_path):
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test")
        plan_id = orch.create_plan("test", [task])
        orch.assign_task(plan_id, "t1", "node-1")
        assert task.status == TaskStatus.ASSIGNED
        assert task.assigned_node == "node-1"

    def test_complete_task(self, tmp_path):
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test")
        plan_id = orch.create_plan("test", [task])
        orch.complete_task(plan_id, "t1", {"result": "ok"})
        assert task.status == TaskStatus.COMPLETED
        assert task.result["result"] == "ok"

    def test_fail_task_with_retry(self, tmp_path):
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test", max_retries=3)
        plan_id = orch.create_plan("test", [task])
        orch.fail_task(plan_id, "t1", "timeout")
        assert task.retry_count == 1
        assert task.status == TaskStatus.PENDING

    def test_fail_task_exhausted_retries(self, tmp_path):
        orch, bus, cache = make_orchestrator(str(tmp_path))
        task = Task(id="t1", type="reasoning", goal="test", max_retries=1, retry_count=1)
        plan_id = orch.create_plan("test", [task])
        orch.fail_task(plan_id, "t1", "permanent error")
        assert task.status == TaskStatus.FAILED
