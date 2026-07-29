"""Edge-case tests for core/scheduler.py — cron matching, overlap, task lifecycle."""

import json
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.scheduler import (
    CHECK_INTERVAL,
    PRESETS,
    VALID_TASK_TYPES,
    TaskScheduler,
    _next_run_after,
    _parse_cron_field,
    cron_matches,
    resolve_cron,
)


class TestParseCronField:
    def test_wildcard(self):
        assert _parse_cron_field("*", 0, (0, 59)) is True
        assert _parse_cron_field("*", 59, (0, 59)) is True

    def test_exact_match(self):
        assert _parse_cron_field("30", 30, (0, 59)) is True
        assert _parse_cron_field("30", 31, (0, 59)) is False

    def test_step(self):
        assert _parse_cron_field("*/15", 0, (0, 59)) is True
        assert _parse_cron_field("*/15", 15, (0, 59)) is True
        assert _parse_cron_field("*/15", 30, (0, 59)) is True
        assert _parse_cron_field("*/15", 10, (0, 59)) is False

    def test_range(self):
        assert _parse_cron_field("10-20", 15, (0, 59)) is True
        assert _parse_cron_field("10-20", 10, (0, 59)) is True
        assert _parse_cron_field("10-20", 20, (0, 59)) is True
        assert _parse_cron_field("10-20", 21, (0, 59)) is False

    def test_list(self):
        assert _parse_cron_field("5,10,15", 10, (0, 59)) is True
        assert _parse_cron_field("5,10,15", 7, (0, 59)) is False

    def test_step_zero_invalid(self):
        """*/0 should not match anything (invalid step)."""
        assert _parse_cron_field("*/0", 0, (0, 59)) is False


class TestCronMatches:
    def test_every_minute(self):
        assert cron_matches("* * * * *", datetime(2026, 1, 1, 12, 0)) is True

    def test_specific_time(self):
        expr = "30 14 7 3 *"
        assert cron_matches(expr, datetime(2026, 3, 7, 14, 30)) is True
        assert cron_matches(expr, datetime(2026, 3, 7, 14, 31)) is False

    def test_day_of_week(self):
        # Scheduler uses 0=Sun convention; Monday maps to 1
        expr = "0 9 * * 1"
        monday = datetime(2026, 1, 5, 9, 0)  # a Monday at 9:00
        tuesday = datetime(2026, 1, 6, 9, 0)  # a Tuesday at 9:00
        assert cron_matches(expr, monday) is True
        assert cron_matches(expr, tuesday) is False

    def test_invalid_cron_expression(self):
        """Malformed cron should raise ValueError."""
        with pytest.raises(ValueError):
            cron_matches("not-a-cron-expression")


class TestResolveCron:
    def test_preset_expansion(self):
        assert resolve_cron("every_5m") == "*/5 * * * *"
        assert resolve_cron("daily_9am") == "0 9 * * *"

    def test_passthrough_cron(self):
        assert resolve_cron("30 14 * * *") == "30 14 * * *"

    def test_unknown_preset_returned_as_is(self):
        assert resolve_cron("custom_expr") == "custom_expr"


class TestPresets:
    def test_all_presets_are_valid_cron(self):
        for name, expr in PRESETS.items():
            # Should not raise
            cron_matches(expr, datetime.now())


class TestNextRunAfter:
    def test_next_run_next_minute(self):
        now = datetime(2026, 1, 1, 12, 0)
        expr = "1 12 1 1 *"  # 12:01 on Jan 1
        result = _next_run_after(expr, now)
        assert result.month == 1
        assert result.day == 1
        assert result.hour == 12
        assert result.minute == 1

    def test_next_run_same_time(self):
        now = datetime(2026, 1, 1, 11, 59)
        expr = "0 12 1 1 *"
        result = _next_run_after(expr, now)
        assert result.hour == 12
        assert result.minute == 0


class TestTaskSchedulerLifecycle:
    def test_add_task(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        task = sched.add_task("Test", "goal", "every_5m", goal="do something")
        assert "id" in task
        assert task["name"] == "Test"
        assert task["type"] == "goal"
        assert task["enabled"] is True

    def test_add_task_invalid_type(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        with pytest.raises(ValueError, match="Invalid task type"):
            sched.add_task("Bad", "not_a_type", "every_5m")

    def test_add_task_invalid_cron(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        with pytest.raises(ValueError):
            sched.add_task("Bad", "goal", "not-a-valid-cron-at-all!!!")

    def test_remove_task(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        task = sched.add_task("ToRemove", "goal", "daily_9am", goal="x")
        assert sched.remove_task(task["id"]) is True
        assert sched.get_task(task["id"]) is None

    def test_remove_nonexistent(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        assert sched.remove_task("no-such-id") is False

    def test_update_task(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        task = sched.add_task("Up", "goal", "daily_9am", goal="old")
        updated = sched.update_task(task["id"], goal="new")
        assert updated["goal"] == "new"

    def test_update_task_type_validation(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        task = sched.add_task("Up", "goal", "daily_9am", goal="x")
        with pytest.raises(ValueError):
            sched.update_task(task["id"], type="invalid_type")

    def test_update_nonexistent(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        assert sched.update_task("no-such-id", goal="x") is None

    def test_list_tasks(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        sched.add_task("A", "goal", "daily_9am", goal="x")
        sched.add_task("B", "powershell", "every_1h", command="Get-Date")
        assert len(sched.list_tasks()) == 2

    def test_list_enabled_only(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        t1 = sched.add_task("A", "goal", "daily_9am", goal="x", enabled=True)
        sched.add_task("B", "goal", "daily_9am", goal="y", enabled=False)
        enabled = sched.list_tasks(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0]["id"] == t1["id"]

    def test_enable_disable(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        task = sched.add_task("Toggle", "goal", "daily_9am", goal="x")
        assert sched.disable_task(task["id"]) is True
        assert sched.get_task(task["id"])["enabled"] is False
        assert sched.enable_task(task["id"]) is True
        assert sched.get_task(task["id"])["enabled"] is True

    def test_enable_disable_nonexistent(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        assert sched.enable_task("no-such") is False
        assert sched.disable_task("no-such") is False


class TestTaskSchedulerPersistence:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        sched.add_task("Persist", "goal", "daily_9am", goal="persist me")
        assert path.exists()

        # Load into a new scheduler
        sched2 = TaskScheduler(tasks_path=str(path))
        tasks = sched2.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["name"] == "Persist"
        assert tasks[0]["goal"] == "persist me"

    def test_load_corrupted_file(self, tmp_path):
        path = tmp_path / "tasks.json"
        path.write_text("{not valid json")
        sched = TaskScheduler(tasks_path=str(path))
        assert sched.list_tasks() == []

    def test_load_nonexistent_file(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        assert sched.list_tasks() == []

    def test_load_not_a_list(self, tmp_path):
        """Task file containing a JSON object instead of array should be rejected."""
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps({"not": "a list"}))
        sched = TaskScheduler(tasks_path=str(path))
        assert sched.list_tasks() == []

    def test_load_missing_cron_expr_backcompat(self, tmp_path):
        """Tasks saved before cron_expr was added should get it computed."""
        path = tmp_path / "tasks.json"
        old_task = [{"id": "old1", "name": "Old", "type": "goal", "schedule": "daily_9am", "goal": "x", "enabled": True}]
        path.write_text(json.dumps(old_task))
        sched = TaskScheduler(tasks_path=str(path))
        loaded = sched.get_task("old1")
        assert "cron_expr" in loaded
        assert loaded["cron_expr"] == "0 9 * * *"

    def test_save_creates_parent_dir(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        sched.add_task("A", "goal", "daily_9am", goal="x")
        assert path.exists()


class TestTaskSchedulerExecution:
    def test_run_task_now_goal(self, tmp_path):
        path = tmp_path / "tasks.json"
        mock_engine = MagicMock()
        mock_engine.run.return_value = {"steps": 5, "notes": ["done"], "success": True}
        sched = TaskScheduler(engine=mock_engine, tasks_path=str(path))
        task = sched.add_task("Go", "goal", "daily_9am", goal="do it")
        result = sched.run_task_now(task["id"])
        assert result["success"] is True
        mock_engine.run.assert_called_once_with("do it")

    def test_run_task_now_powershell(self, tmp_path):
        path = tmp_path / "tasks.json"
        mock_engine = MagicMock()
        mock_ps = MagicMock()
        mock_ps.run_command.return_value = MagicMock(success=True, stdout="output", stderr="", exit_code=0)
        mock_engine.powershell = mock_ps
        sched = TaskScheduler(engine=mock_engine, tasks_path=str(path))
        task = sched.add_task("PS", "powershell", "daily_9am", command="Get-Date")
        result = sched.run_task_now(task["id"])
        assert result["success"] is True

    def test_run_task_now_no_engine(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        task = sched.add_task("Go", "goal", "daily_9am", goal="do it")
        result = sched.run_task_now(task["id"])
        assert result["success"] is False
        assert "No engine" in result["error"]

    def test_run_task_now_nonexistent(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        assert sched.run_task_now("no-such") is None

    def test_run_task_updates_last_run(self, tmp_path):
        path = tmp_path / "tasks.json"
        mock_engine = MagicMock()
        mock_engine.run.return_value = {"success": True}
        sched = TaskScheduler(engine=mock_engine, tasks_path=str(path))
        task = sched.add_task("Go", "goal", "daily_9am", goal="do it")
        assert sched.get_task(task["id"])["last_run"] is None
        sched.run_task_now(task["id"])
        assert sched.get_task(task["id"])["last_run"] is not None

    def test_run_task_now_handles_engine_exception(self, tmp_path):
        path = tmp_path / "tasks.json"
        mock_engine = MagicMock()
        mock_engine.run.side_effect = RuntimeError("Engine crashed")
        sched = TaskScheduler(engine=mock_engine, tasks_path=str(path))
        task = sched.add_task("Go", "goal", "daily_9am", goal="do it")
        result = sched.run_task_now(task["id"])
        assert result["success"] is False
        assert "Engine crashed" in result["error"]


class TestTaskSchedulerThreading:
    def test_start_stop(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        sched.start()
        assert sched._running is True
        sched.stop()
        assert sched._running is False

    def test_double_start_is_safe(self, tmp_path, caplog):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        sched.start()
        sched.start()  # should not raise or create second thread
        sched.stop()

    def test_stop_without_start(self, tmp_path):
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        sched.stop()  # should not raise


class TestOnComplete:
    def test_on_complete_disable(self, tmp_path):
        path = tmp_path / "tasks.json"
        mock_engine = MagicMock()
        mock_engine.run.return_value = {"success": True}
        sched = TaskScheduler(engine=mock_engine, tasks_path=str(path))
        task = sched.add_task("Once", "goal", "daily_9am", goal="x", on_complete="disable")
        sched.run_task_now(task["id"])
        assert sched.get_task(task["id"])["enabled"] is False

    def test_on_complete_remove(self, tmp_path):
        path = tmp_path / "tasks.json"
        mock_engine = MagicMock()
        mock_engine.run.return_value = {"success": True}
        sched = TaskScheduler(engine=mock_engine, tasks_path=str(path))
        task = sched.add_task("Once", "goal", "daily_9am", goal="x", on_complete="remove")
        sched.run_task_now(task["id"])
        assert sched.get_task(task["id"]) is None


class TestThreadSafety:
    def test_concurrent_add(self, tmp_path):
        """Multiple threads adding tasks concurrently should not corrupt state."""
        path = tmp_path / "tasks.json"
        sched = TaskScheduler(tasks_path=str(path))
        errors = []

        def add_tasks(n):
            try:
                for i in range(n):
                    sched.add_task(f"T{i}", "goal", "daily_9am", goal=f"g{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_tasks, args=(10,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(sched.list_tasks()) == 50
