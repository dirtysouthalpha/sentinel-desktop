"""Tests for the daily digest generator."""
from core.mesh.digest import DailyDigest
from core.mesh.task_graph import Task, TaskStatus


class TestDailyDigest:
    def test_empty_digest(self):
        dd = DailyDigest()
        report = dd.generate(tasks=[], nodes=[], lessons=[])
        assert "0 completed" in report

    def test_digest_with_tasks(self):
        dd = DailyDigest()
        tasks = [
            Task(id="t1", type="reasoning", goal="plan", status=TaskStatus.COMPLETED),
            Task(id="t2", type="desktop_automation", goal="exec", status=TaskStatus.COMPLETED),
            Task(id="t3", type="monitoring", goal="check", status=TaskStatus.FAILED),
        ]
        report = dd.generate(tasks=tasks, nodes=[], lessons=[])
        assert "2 completed" in report
        assert "1 failed" in report

    def test_digest_with_nodes(self):
        dd = DailyDigest()
        nodes = [{"node_id": "prime", "status": "active", "cpu": 12.5}, {"node_id": "desktop", "status": "active", "cpu": 45.0}]
        report = dd.generate(tasks=[], nodes=nodes, lessons=[])
        assert "prime" in report
        assert "desktop" in report

    def test_digest_with_lessons(self):
        dd = DailyDigest()
        lessons = [{"content": "catbox paused uploads", "fire_count": 5}, {"content": "hackbox drifted silently", "fire_count": 3}]
        report = dd.generate(tasks=[], nodes=[], lessons=lessons)
        assert "catbox" in report
        assert "hackbox" in report
