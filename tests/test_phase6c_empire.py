"""Phase 6C: Empire integration via mesh plans."""
from __future__ import annotations

import pytest

from core.mesh.task_graph import Task, TaskGraph, TaskStatus


class TestEmpireIntegration:
    def test_empire_plan_creation(self):
        """An empire plan with multiple task types can be created."""
        graph = TaskGraph()
        tasks = [
            Task(id="yt-stats", type="shell", goal="pull YT analytics"),
            Task(id="alpaca-pnl", type="shell", goal="pull Alpaca P&L"),
            Task(id="buffer-metrics", type="shell", goal="pull Buffer metrics"),
            Task(id="empire-score", type="python", goal="aggregate empire score", depends_on=["yt-stats", "alpaca-pnl", "buffer-metrics"]),
            Task(id="narrative", type="llm", goal="generate narrative summary", depends_on=["empire-score"]),
        ]
        for t in tasks:
            graph.add_task(t)
        assert len(graph.tasks) == 5

    def test_empire_plan_execution_order(self):
        """Empire tasks respect dependency order."""
        graph = TaskGraph()
        t1 = Task(id="yt-stats", type="shell", goal="pull YT analytics")
        t2 = Task(id="empire-score", type="python", goal="aggregate", depends_on=["yt-stats"])
        graph.add_task(t1)
        graph.add_task(t2)

        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "yt-stats"

        t1.status = TaskStatus.COMPLETED
        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "empire-score"

    def test_empire_plan_complete(self):
        """All empire tasks complete -> plan is complete."""
        graph = TaskGraph()
        for t in [
            Task(id="t1", type="shell", goal="a"),
            Task(id="t2", type="shell", goal="b"),
            Task(id="t3", type="shell", goal="c"),
        ]:
            graph.add_task(t)
        for t in graph.tasks.values():
            t.status = TaskStatus.COMPLETED
        assert graph.is_complete()

    def test_empire_plan_checkpoint_resume(self):
        """Empire plan checkpoint can be saved and resumed."""
        import tempfile
        graph = TaskGraph(checkpoint_dir=tempfile.mkdtemp())
        t1 = Task(id="yt-stats", type="shell", goal="pull YT analytics")
        graph.add_task(t1)
        t1.status = TaskStatus.COMPLETED
        t1.result = {"views": 1000, "subs": 50}
        graph.checkpoint("yt-stats")

        loaded = graph.load_checkpoint("yt-stats")
        assert loaded is not None
        assert loaded["status"] == "completed"
        assert loaded["result"]["views"] == 1000
