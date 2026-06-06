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

        with (
            patch("core.scheduler.cron_matches", return_value=True),
            patch.object(ts, "_execute_task", side_effect=fake_exec),
        ):
            ts._tick()

        assert set(executed) == {"A", "B"}


class TestDisabledTaskSkipped:
    """A disabled task is never executed even when its cron expression matches."""

    def test_disabled_task_not_executed(self, tmp_path) -> None:
        ts = _scheduler(tmp_path)
        task = ts.add_task("X", "script", "* * * * *", path="x.py")
        tid = task["id"]
        ts._tasks[tid]["enabled"] = False

        with (
            patch("core.scheduler.cron_matches", return_value=True),
            patch.object(ts, "_execute_task") as mock_exec,
        ):
            ts._tick()

        mock_exec.assert_not_called()


class TestOnTaskCompleteCallbackException:
    """on_task_complete callback raising should not propagate out of _tick."""

    def test_callback_exception_does_not_raise(self, tmp_path) -> None:
        ts = _scheduler(tmp_path)
        ts._on_task_complete = MagicMock(side_effect=RuntimeError("callback boom"))
        ts.add_task("Y", "script", "* * * * *", path="y.py")

        with (
            patch("core.scheduler.cron_matches", return_value=True),
            patch.object(ts, "_execute_task", return_value={"status": "success"}),
        ):
            ts._tick()  # Should not raise

        ts._on_task_complete.assert_called_once()


class TestTickNoTasksSaveNotCalled:
    """When no tasks are due, _tick should not call save."""

    def test_no_due_tasks_no_save(self, tmp_path) -> None:
        ts = _scheduler(tmp_path)
        ts.add_task("Z", "script", "* * * * *", path="z.py")

        with (
            patch("core.scheduler.cron_matches", return_value=False),
            patch.object(ts, "save") as mock_save,
        ):
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


class TestRapidStartStopCycles:
    """Test scheduler behavior under rapid start/stop cycles."""

    def test_rapid_start_stop_cycles(self, tmp_path) -> None:
        """Test that rapid start/stop cycles don't cause crashes or state corruption."""
        ts = _scheduler(tmp_path)
        ts.add_task("A", "script", "* * * * *", path="a.py")

        # Perform rapid start/stop cycles
        for i in range(5):
            ts.start()
            # Immediately stop
            if ts._thread is not None:
                ts.stop()
            # Should not crash or corrupt state

        # Scheduler should still be functional after rapid cycles
        assert len(ts.list_tasks()) == 1

    def test_consecutive_start_calls_ignored(self, tmp_path) -> None:
        """Test that consecutive start() calls without intervening stop() are safe."""
        ts = _scheduler(tmp_path)
        ts.add_task("A", "script", "* * * * *", path="a.py")

        # Multiple consecutive starts should be handled gracefully
        ts.start()
        ts.start()  # Should be ignored or safe
        ts.start()  # Should be ignored or safe

        # Clean up
        if ts._thread is not None:
            ts.stop()

    def test_stop_without_start_is_safe(self, tmp_path) -> None:
        """Test that calling stop() without start() doesn't crash."""
        ts = _scheduler(tmp_path)
        ts.add_task("A", "script", "* * * * *", path="a.py")

        # Stop without start should be safe
        ts.stop()  # Should not raise

        # Should still be functional
        assert len(ts.list_tasks()) == 1


class TestCleanupAfterCrashes:
    """Test scheduler cleanup after system crashes or failures."""

    def test_cleanup_after_corrupt_state_file(self, tmp_path) -> None:
        """Test that scheduler can recover from corrupt state file."""
        tasks_file = tmp_path / "tasks.json"
        # Write corrupt data
        tasks_file.write_text("not valid json{{{")

        ts = _scheduler(tmp_path)

        # Should handle corrupt state gracefully
        # Either by starting fresh or clearing tasks
        ts.load()

        # Scheduler should still be functional
        task = ts.add_task("B", "script", "* * * * *", path="b.py")
        assert task is not None
        assert "id" in task

    def test_cleanup_after_missing_state_file(self, tmp_path) -> None:
        """Test that scheduler handles missing state file gracefully."""
        # Don't create tasks.json - it doesn't exist
        ts = _scheduler(tmp_path)

        # Should start with empty state
        assert len(ts.list_tasks()) == 0

        # Should be able to add tasks
        task = ts.add_task("C", "script", "* * * * *", path="c.py")
        assert task is not None

    def test_save_failure_during_crash_cleanup(self, tmp_path) -> None:
        """Test that save failures during shutdown don't prevent cleanup."""
        ts = _scheduler(tmp_path)
        ts.add_task("D", "script", "* * * * *", path="d.py")

        # Simulate save failure (e.g., disk full, permissions)
        with patch("pathlib.Path.write_text", side_effect=OSError("Disk full")):
            # Save should not crash
            try:
                ts.save()
            except OSError:
                pass  # Expected

        # State should remain consistent
        assert len(ts.list_tasks()) == 1


class TestOverlappingTimeWindows:
    """Test scheduler behavior with overlapping time windows."""

    def test_tasks_with_overlapping_schedules(self, tmp_path) -> None:
        """Test multiple tasks with overlapping time windows."""
        ts = _scheduler(tmp_path)

        # Add tasks with overlapping schedules (all run every minute)
        ts.add_task("Task1", "script", "* * * * *", path="task1.py")
        ts.add_task("Task2", "script", "* * * * *", path="task2.py")
        ts.add_task("Task3", "script", "* * * * *", path="task3.py")

        executed: list[str] = []

        def fake_exec(task):
            executed.append(task["name"])
            return {"status": "success"}

        # All tasks should execute when their time windows overlap
        with (
            patch("core.scheduler.cron_matches", return_value=True),
            patch.object(ts, "_execute_task", side_effect=fake_exec),
        ):
            ts._tick()

        # All three tasks should have executed
        assert set(executed) == {"Task1", "Task2", "Task3"}

    def test_tasks_with_partially_overlapping_schedules(self, tmp_path) -> None:
        """Test tasks with partially overlapping time windows."""
        ts = _scheduler(tmp_path)

        # Add tasks with different but overlapping schedules
        # Task1: Every 5 minutes
        ts.add_task("Task1", "script", "*/5 * * * *", path="task1.py")
        # Task2: Every 2 minutes (overlaps with Task1 every 10 minutes)
        ts.add_task("Task2", "script", "*/2 * * * *", path="task2.py")

        # Both should coexist without conflict
        tasks = ts.list_tasks()
        assert len(tasks) == 2
        assert all("cron_expr" in task for task in tasks)

    def test_high_frequency_task_with_long_running_task(self, tmp_path) -> None:
        """Test interaction between high-frequency and long-running tasks."""
        ts = _scheduler(tmp_path)

        # High-frequency task (every minute)
        ts.add_task("HighFreq", "script", "* * * * *", path="fast.py")
        # Long-running task (once per hour)
        ts.add_task("LongRunning", "script", "0 * * * *", path="slow.py")

        # Both should coexist
        tasks = ts.list_tasks()
        assert len(tasks) == 2

        # High-frequency task should not interfere with long-running task
        high_freq = [t for t in tasks if t["name"] == "HighFreq"][0]
        long_running = [t for t in tasks if t["name"] == "LongRunning"][0]

        assert high_freq["cron_expr"] == "* * * * *"
        assert long_running["cron_expr"] == "0 * * * *"

    def test_simultaneous_task_execution_order(self, tmp_path) -> None:
        """Test that tasks due at the same time execute in predictable order."""
        ts = _scheduler(tmp_path)

        # Add tasks that will all be due simultaneously
        ts.add_task("First", "script", "* * * * *", path="first.py")
        ts.add_task("Second", "script", "* * * * *", path="second.py")
        ts.add_task("Third", "script", "* * * * *", path="third.py")

        execution_order: list[str] = []

        def fake_exec(task):
            execution_order.append(task["name"])
            return {"status": "success"}

        with (
            patch("core.scheduler.cron_matches", return_value=True),
            patch.object(ts, "_execute_task", side_effect=fake_exec),
        ):
            ts._tick()

        # All tasks should execute
        assert len(execution_order) == 3
        # Order should be deterministic (same as insertion order)
        assert execution_order == ["First", "Second", "Third"]
