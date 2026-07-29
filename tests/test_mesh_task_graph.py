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
        graph = TaskGraph()
        t1 = Task(id="t1", type="reasoning", goal="plan")
        t2 = Task(id="t2", type="desktop_automation", goal="execute", depends_on=["t1"])
        graph.add_task(t1)
        graph.add_task(t2)
        assert t2.is_ready(graph) is False
        t1.status = TaskStatus.COMPLETED
        assert t2.is_ready(graph) is True

    def test_get_ready_tasks(self):
        graph = TaskGraph()
        t1 = Task(id="t1", type="reasoning", goal="plan")
        t2 = Task(id="t2", type="desktop_automation", goal="exec", depends_on=["t1"])
        t3 = Task(id="t3", type="monitoring", goal="check")
        graph.add_task(t1)
        graph.add_task(t2)
        graph.add_task(t3)
        t1.status = TaskStatus.COMPLETED
        ready = graph.get_ready_tasks()
        assert len(ready) == 2

    def test_checkpoint_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = TaskGraph(checkpoint_dir=tmp)
            task = Task(id="t1", type="reasoning", goal="plan", status=TaskStatus.RUNNING, retry_count=2)
            graph.add_task(task)
            graph.checkpoint(task.id)
            graph2 = TaskGraph(checkpoint_dir=tmp)
            loaded = graph2.load_checkpoint("t1")
            assert loaded is not None
            assert loaded["id"] == "t1"
            assert loaded["retry_count"] == 2

    def test_cycle_detection(self):
        graph = TaskGraph()
        t1 = Task(id="a", type="test", goal="a", depends_on=["b"])
        t2 = Task(id="b", type="test", goal="b", depends_on=["a"])
        graph.add_task(t1)
        with pytest.raises(ValueError, match="cycle"):
            graph.add_task(t2)

    def test_self_dependency_rejected(self):
        graph = TaskGraph()
        t = Task(id="a", type="test", goal="a", depends_on=["a"])
        with pytest.raises(ValueError, match="itself"):
            graph.add_task(t)
