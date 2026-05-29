"""Edge-case tests for scheduler overlap and multi-task tick behaviour.

Covers:
- Multiple tasks simultaneously due all execute in one tick
- Disabled tasks are skipped even when cron matches
- on_task_complete callback exception is handled gracefully
- _tick with no due tasks does not save
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.scheduler import TaskScheduler


def _scheduler(tmp_path) -> TaskScheduler:
    return TaskScheduler(engine=None, tasks_path=str(tmp_path / "tasks.json"))


class TestMultipleTasksInOneTick:
    """When multiple tasks are due, all of them execute in a single _tick call."""

    def test_all_due_tasks_execute(self, tmp_path) -> None:
        ts = _scheduler(tmp_path)
        ts.add_task("A", "script", "* * * * *", path="a.py")
        ts.add_task("B", "script", "* * * * *", path="b.py")

        executed: list[str] = []

        def fake_exec(task):
            executed.append(task["name"])
            return {"status": "success"}

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec):
            ts._tick()

        assert set(executed) == {"A", "B"}


class TestDisabledTaskSkipped:
    """A disabled task is never executed even when its cron expression matches."""

    def test_disabled_task_not_executed(self, tmp_path) -> None:
        ts = _scheduler(tmp_path)
        task = ts.add_task("X", "script", "* * * * *", path="x.py")
        tid = task["id"]
        ts._tasks[tid]["enabled"] = False

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task") as mock_exec:
            ts._tick()

        mock_exec.assert_not_called()


class TestOnTaskCompleteCallbackException:
    """on_task_complete callback raising should not propagate out of _tick."""

    def test_callback_exception_does_not_raise(self, tmp_path) -> None:
        ts = _scheduler(tmp_path)
        ts._on_task_complete = MagicMock(side_effect=RuntimeError("callback boom"))
        ts.add_task("Y", "script", "* * * * *", path="y.py")

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", return_value={"status": "success"}):
            ts._tick()  # Should not raise

        ts._on_task_complete.assert_called_once()


class TestTickNoTasksSaveNotCalled:
    """When no tasks are due, _tick should not call save."""

    def test_no_due_tasks_no_save(self, tmp_path) -> None:
        ts = _scheduler(tmp_path)
        ts.add_task("Z", "script", "* * * * *", path="z.py")

        with patch("core.scheduler.cron_matches", return_value=False), \
             patch.object(ts, "save") as mock_save:
            ts._tick()

        mock_save.assert_not_called()


class TestTaskWithMissingCronExprSkipped:
    """A task without a cron_expr is silently skipped."""

    def test_missing_cron_skipped(self, tmp_path) -> None:
        ts = _scheduler(tmp_path)
        task = ts.add_task("W", "script", "* * * * *", path="w.py")
        tid = task["id"]
        ts._tasks[tid]["cron_expr"] = ""  # clear it

        with patch.object(ts, "_execute_task") as mock_exec:
            ts._tick()

        mock_exec.assert_not_called()
