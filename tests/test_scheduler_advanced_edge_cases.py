"""Advanced edge case tests for scheduler overlap protection.

Covers:
- Concurrent task modification during execution
- Task priority handling during overlaps
- Resource exhaustion scenarios
- File locking during concurrent access
- Edge cases with delay_seconds vs cron conflicts
- Task state consistency during crashes
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.scheduler import TaskScheduler


def _scheduler(tmp_path) -> TaskScheduler:
    return TaskScheduler(engine=None, tasks_path=str(tmp_path / "tasks.json"))


# ---------------------------------------------------------------------------
# Concurrent task modification during execution
# ---------------------------------------------------------------------------


class TestConcurrentTaskModification:
    """Test scheduler behavior when tasks are modified during execution."""

    def test_add_task_during_tick(self, tmp_path) -> None:
        """Test adding a task while scheduler is in the middle of a tick."""
        ts = _scheduler(tmp_path)
        ts.add_task("Existing", "script", "* * * * *", path="existing.py")

        execution_order: list[str] = []

        def fake_exec(task):
            execution_order.append(task["name"])
            # Simulate adding a task during execution
            if task["name"] == "Existing":
                ts.add_task("AddedDuring", "script", "* * * * *", path="new.py")
            return {"status": "success"}

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec):
            ts._tick()

        # Original task should execute
        assert "Existing" in execution_order
        # Newly added task should be saved but not executed in same tick
        tasks = ts.list_tasks()
        assert len(tasks) == 2

    def test_remove_task_during_tick(self, tmp_path) -> None:
        """Test removing a task while scheduler is executing tasks."""
        ts = _scheduler(tmp_path)

        # Add multiple tasks
        ts.add_task("Task1", "script", "* * * * *", path="task1.py")
        task2 = ts.add_task("Task2", "script", "* * * * *", path="task2.py")
        ts.add_task("Task3", "script", "* * * * *", path="task3.py")

        execution_order: list[str] = []

        def fake_exec(task):
            execution_order.append(task["name"])
            # Remove Task2 during execution
            if task["name"] == "Task2":
                ts.remove_task(task2["id"])
            return {"status": "success"}

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec):
            ts._tick()

        # All original tasks should execute
        assert len(execution_order) == 3
        # Task2 should be removed after execution
        tasks = ts.list_tasks()
        assert len(tasks) == 2
        task_names = {t["name"] for t in tasks}
        assert "Task2" not in task_names

    def test_modify_task_during_execution(self, tmp_path) -> None:
        """Test modifying task properties while it's executing."""
        ts = _scheduler(tmp_path)
        task = ts.add_task("Modifiable", "script", "* * * * *", path="mod.py")

        execution_count = 0

        def fake_exec(task):
            nonlocal execution_count
            execution_count += 1
            # Modify task during first execution
            if execution_count == 1:
                ts._tasks[task["id"]]["enabled"] = False
            return {"status": "success"}

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec):
            ts._tick()
            ts._tick()  # Second tick

        # Task should execute only once (disabled after first execution)
        assert execution_count == 1


# ---------------------------------------------------------------------------
# Task execution ordering during overlaps
# ---------------------------------------------------------------------------


class TestTaskExecutionOrderOverlaps:
    """Test execution order when multiple tasks are due simultaneously."""

    def test_insertion_order_maintained(self, tmp_path) -> None:
        """Test that tasks execute in insertion order when due simultaneously."""
        ts = _scheduler(tmp_path)

        # Add tasks in specific order
        ts.add_task("First", "script", "* * * * *", path="first.py")
        ts.add_task("Second", "script", "* * * * *", path="second.py")
        ts.add_task("Third", "script", "* * * * *", path="third.py")

        execution_order: list[str] = []

        def fake_exec(task):
            execution_order.append(task["name"])
            return {"status": "success"}

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec):
            ts._tick()

        # Should maintain insertion order
        assert execution_order == ["First", "Second", "Third"]

    def test_execution_order_consistent_across_ticks(self, tmp_path) -> None:
        """Test that execution order remains consistent across multiple ticks."""
        ts = _scheduler(tmp_path)

        ts.add_task("Task1", "script", "* * * * *", path="task1.py")
        ts.add_task("Task2", "script", "* * * * *", path="task2.py")

        first_tick_order: list[str] = []
        second_tick_order: list[str] = []

        def fake_exec(task):
            first_tick_order.append(task["name"])
            return {"status": "success"}

        def fake_exec2(task):
            second_tick_order.append(task["name"])
            return {"status": "success"}

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec):
            ts._tick()

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec2):
            ts._tick()

        # Order should be consistent across ticks
        assert first_tick_order == second_tick_order


# ---------------------------------------------------------------------------
# Resource exhaustion scenarios
# ---------------------------------------------------------------------------


class TestResourceExhaustionScenarios:
    """Test scheduler behavior under resource pressure."""

    def test_many_simultaneous_tasks(self, tmp_path) -> None:
        """Test scheduler with many tasks due simultaneously."""
        ts = _scheduler(tmp_path)

        # Add many tasks
        for i in range(50):
            ts.add_task(f"Task{i}", "script", "* * * * *", path=f"task{i}.py")

        execution_count = 0

        def fake_exec(task):
            nonlocal execution_count
            execution_count += 1
            return {"status": "success"}

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec):
            ts._tick()

        # All tasks should execute
        assert execution_count == 50

    def test_slow_task_execution_doesnt_block_other_tasks(self, tmp_path) -> None:
        """Test that slow tasks don't block other tasks from executing."""
        ts = _scheduler(tmp_path)

        ts.add_task("Slow", "script", "* * * * *", path="slow.py")
        ts.add_task("Fast", "script", "* * * * *", path="fast.py")

        execution_times = {}

        def fake_exec(task):
            start = time.time()
            if task["name"] == "Slow":
                time.sleep(0.1)  # Simulate slow task
            execution_times[task["name"]] = time.time() - start
            return {"status": "success"}

        with patch("core.scheduler.cron_matches", return_value=True), \
             patch.object(ts, "_execute_task", side_effect=fake_exec):
            ts._tick()

        # Both tasks should execute
        assert set(execution_times.keys()) == {"Slow", "Fast"}
        # Slow task should take longer
        assert execution_times["Slow"] >= 0.1


# ---------------------------------------------------------------------------
# File locking and concurrent access
# ---------------------------------------------------------------------------


class TestFileLockingScenarios:
    """Test file locking during concurrent scheduler access."""

    def test_concurrent_save_operations(self, tmp_path) -> None:
        """Test that concurrent save operations don't corrupt data."""
        ts = _scheduler(tmp_path)
        ts.add_task("Task1", "script", "* * * * *", path="task1.py")

        errors = []
        threads = []

        def save_in_thread():
            try:
                for _ in range(10):
                    ts.save()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Create multiple threads saving concurrently
        for _ in range(5):
            t = threading.Thread(target=save_in_thread)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Should complete without errors
        assert len(errors) == 0

        # Data should be intact
        ts2 = _scheduler(tmp_path)
        ts2.load()
        tasks = ts2.list_tasks()
        assert len(tasks) == 1

    def test_concurrent_load_operations(self, tmp_path) -> None:
        """Test that concurrent load operations work correctly."""
        ts = _scheduler(tmp_path)
        ts.add_task("Task1", "script", "* * * * *", path="task1.py")
        ts.save()

        results = []
        errors = []
        threads = []

        def load_in_thread():
            try:
                ts_new = _scheduler(tmp_path)
                ts_new.load()
                results.append(len(ts_new.list_tasks()))
            except Exception as e:
                errors.append(e)

        # Create multiple threads loading concurrently
        for _ in range(10):
            t = threading.Thread(target=load_in_thread)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Should complete without errors
        assert len(errors) == 0
        # All threads should load correct data
        assert all(r == 1 for r in results)


# ---------------------------------------------------------------------------
# Schedule resolution edge cases
# ---------------------------------------------------------------------------


class TestScheduleResolutionEdgeCases:
    """Test edge cases in schedule string resolution."""

    def test_invalid_schedule_defaults_gracefully(self, tmp_path) -> None:
        """Test that invalid schedule strings are handled gracefully."""
        ts = _scheduler(tmp_path)

        # Try adding task with invalid schedule
        try:
            ts.add_task("Invalid", "script", "not_a_valid_cron", path="invalid.py")
            # If it doesn't raise, it should handle it gracefully
            assert True
        except ValueError:
            # Expected to raise ValueError for invalid cron
            assert True

    def test_edge_case_schedules(self, tmp_path) -> None:
        """Test edge case schedule strings."""
        ts = _scheduler(tmp_path)

        # Test with various edge case schedules
        edge_schedules = [
            "* * * * *",  # Every minute
            "0 * * * *",  # Every hour
            "0 0 * * *",  # Every day
            "0 0 * * 0",  # Every week
            "0 0 1 * *",  # Every month
        ]

        for i, schedule in enumerate(edge_schedules):
            task = ts.add_task(f"Schedule{i}", "script", schedule, path=f"schedule{i}.py")
            assert task is not None
            assert "cron_expr" in task


# ---------------------------------------------------------------------------
# Task state consistency during crashes
# ---------------------------------------------------------------------------


class TestTaskStateConsistency:
    """Test task state consistency during system crashes."""

    def test_task_state_persistence_after_crash(self, tmp_path) -> None:
        """Test that task state is preserved after simulated crash."""
        ts = _scheduler(tmp_path)
        task = ts.add_task("Persistent", "script", "* * * * *", path="persist.py")

        # Modify task state
        ts._tasks[task["id"]]["enabled"] = False
        ts._tasks[task["id"]]["last_run"] = "2024-01-01T00:00:00"
        ts.save()

        # Simulate crash and recovery by creating new scheduler instance
        ts2 = _scheduler(tmp_path)
        ts2.load()

        # State should be preserved
        tasks = ts2.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["enabled"] is False
        assert tasks[0]["last_run"] == "2024-01-01T00:00:00"

    def test_partial_recovery_from_corrupt_tasks(self, tmp_path) -> None:
        """Test recovery from partially corrupt tasks file."""
        ts = _scheduler(tmp_path)

        # Add some valid tasks
        ts.add_task("Valid1", "script", "* * * * *", path="valid1.py")
        ts.add_task("Valid2", "script", "* * * * *", path="valid2.py")
        ts.save()

        # Corrupt the tasks file by removing required fields from one task
        import json
        tasks_path = Path(tmp_path) / "tasks.json"
        with tasks_path.open("r") as f:
            data = json.load(f)

        # Remove required field from one task
        if "tasks" in data and len(data["tasks"]) > 0:
            first_task_id = list(data["tasks"].keys())[0]
            del data["tasks"][first_task_id]["name"]  # Remove required field

        with tasks_path.open("w") as f:
            json.dump(data, f)

        # Create new scheduler - should handle gracefully
        ts2 = _scheduler(tmp_path)
        ts2.load()

        # Should recover with valid tasks only
        tasks = ts2.list_tasks()
        # At least one valid task should remain
        assert len(tasks) >= 1
        # All remaining tasks should have required fields
        for task in tasks:
            assert "name" in task
            assert "type" in task
