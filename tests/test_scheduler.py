"""Tests for core/scheduler.py — cron matching and TaskScheduler CRUD."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.scheduler import (
    PRESETS,
    TaskScheduler,
    _next_run_after,
    _parse_cron_field,
    cron_matches,
    resolve_cron,
)

# ---------------------------------------------------------------------------
# _parse_cron_field
# ---------------------------------------------------------------------------


class TestParseCronField:
    def test_wildcard_matches_any(self):
        assert _parse_cron_field("*", 5, (0, 59)) is True
        assert _parse_cron_field("*", 0, (0, 59)) is True

    def test_step_divisible(self):
        assert _parse_cron_field("*/5", 0, (0, 59)) is True
        assert _parse_cron_field("*/5", 5, (0, 59)) is True
        assert _parse_cron_field("*/5", 10, (0, 59)) is True
        assert _parse_cron_field("*/5", 3, (0, 59)) is False

    def test_step_on_one_based_field_starts_at_minimum(self):
        # day-of-month is 1-based: standard cron */N means "every Nth value
        # starting from the field minimum", so */2 = days 1,3,5,... not 2,4,6,...
        assert _parse_cron_field("*/2", 1, (1, 31)) is True
        assert _parse_cron_field("*/2", 2, (1, 31)) is False
        assert _parse_cron_field("*/2", 3, (1, 31)) is True
        # month is 1-based: */3 = months 1,4,7,10
        assert _parse_cron_field("*/3", 1, (1, 12)) is True
        assert _parse_cron_field("*/3", 3, (1, 12)) is False
        assert _parse_cron_field("*/3", 4, (1, 12)) is True

    def test_step_on_zero_based_field_unchanged(self):
        # minute/hour are 0-based: */2 still means 0,2,4,...
        assert _parse_cron_field("*/2", 0, (0, 59)) is True
        assert _parse_cron_field("*/2", 1, (0, 59)) is False
        assert _parse_cron_field("*/2", 2, (0, 59)) is True

    def test_exact_value(self):
        assert _parse_cron_field("15", 15, (0, 59)) is True
        assert _parse_cron_field("15", 14, (0, 59)) is False

    def test_range(self):
        assert _parse_cron_field("1-5", 1, (0, 59)) is True
        assert _parse_cron_field("1-5", 3, (0, 59)) is True
        assert _parse_cron_field("1-5", 5, (0, 59)) is True
        assert _parse_cron_field("1-5", 6, (0, 59)) is False
        assert _parse_cron_field("1-5", 0, (0, 59)) is False

    def test_comma_list(self):
        assert _parse_cron_field("1,15,30", 1, (0, 59)) is True
        assert _parse_cron_field("1,15,30", 15, (0, 59)) is True
        assert _parse_cron_field("1,15,30", 30, (0, 59)) is True
        assert _parse_cron_field("1,15,30", 7, (0, 59)) is False

    def test_comma_with_spaces(self):
        assert _parse_cron_field("1, 15, 30", 15, (0, 59)) is True


# ---------------------------------------------------------------------------
# cron_matches
# ---------------------------------------------------------------------------


class TestCronMatches:
    def test_every_minute(self):
        assert cron_matches("* * * * *", datetime(2025, 1, 1, 12, 30)) is True

    def test_specific_minute(self):
        assert cron_matches("30 * * * *", datetime(2025, 1, 1, 12, 30)) is True
        assert cron_matches("30 * * * *", datetime(2025, 1, 1, 12, 31)) is False

    def test_specific_hour_and_minute(self):
        assert cron_matches("0 9 * * *", datetime(2025, 1, 1, 9, 0)) is True
        assert cron_matches("0 9 * * *", datetime(2025, 1, 1, 10, 0)) is False

    def test_specific_month(self):
        assert cron_matches("* * 1 1 *", datetime(2025, 1, 1, 0, 0)) is True
        assert cron_matches("* * 1 1 *", datetime(2025, 2, 1, 0, 0)) is False

    def test_day_of_week_sunday(self):
        # 2025-01-05 is a Sunday
        assert cron_matches("* * * * 0", datetime(2025, 1, 5, 12, 0)) is True
        # 2025-01-06 is a Monday
        assert cron_matches("* * * * 0", datetime(2025, 1, 6, 12, 0)) is False

    def test_day_of_week_monday(self):
        # 2025-01-06 is a Monday — dow field 1
        assert cron_matches("* * * * 1", datetime(2025, 1, 6, 12, 0)) is True

    def test_step_every_5_minutes(self):
        assert cron_matches("*/5 * * * *", datetime(2025, 1, 1, 12, 0)) is True
        assert cron_matches("*/5 * * * *", datetime(2025, 1, 1, 12, 5)) is True
        assert cron_matches("*/5 * * * *", datetime(2025, 1, 1, 12, 3)) is False

    def test_step_every_other_day_matches_from_first(self):
        # "0 0 */2 * *" = midnight every other day. */2 in day-of-month is
        # 1-based, so it matches the 1st, 3rd, 5th... of the month, not the
        # 2nd, 4th, 6th...
        assert cron_matches("0 0 */2 * *", datetime(2025, 1, 1, 0, 0)) is True
        assert cron_matches("0 0 */2 * *", datetime(2025, 1, 2, 0, 0)) is False
        assert cron_matches("0 0 */2 * *", datetime(2025, 1, 3, 0, 0)) is True

    def test_invalid_cron_raises(self):
        with pytest.raises(ValueError, match="expected 5 fields"):
            cron_matches("* * *")

    def test_uses_current_time_by_default(self):
        result = cron_matches("* * * * *")
        assert result is True


# ---------------------------------------------------------------------------
# resolve_cron
# ---------------------------------------------------------------------------


class TestResolveCron:
    def test_preset_resolved(self):
        assert resolve_cron("every_5m") == "*/5 * * * *"
        assert resolve_cron("daily_9am") == "0 9 * * *"

    def test_unknown_passed_through(self):
        assert resolve_cron("30 8 * * 1-5") == "30 8 * * 1-5"

    def test_all_presets_are_valid_cron(self):
        for _name, expr in PRESETS.items():
            # Should not raise
            cron_matches(expr, datetime(2025, 1, 1, 0, 0))


# ---------------------------------------------------------------------------
# TaskScheduler — CRUD
# ---------------------------------------------------------------------------


@pytest.fixture
def scheduler(tmp_path):
    path = str(tmp_path / "tasks.json")
    ts = TaskScheduler(engine=None, tasks_path=path)
    yield ts
    ts.stop()


class TestTaskSchedulerAdd:
    def test_add_returns_task_dict(self, scheduler):
        task = scheduler.add_task("Test", "script", "*/5 * * * *", path="test.py")
        assert task["name"] == "Test"
        assert task["type"] == "script"
        assert task["enabled"] is True
        assert "id" in task
        assert "cron_expr" in task

    def test_add_presolves_preset(self, scheduler):
        task = scheduler.add_task("Daily", "goal", "daily_9am", goal="Do stuff")
        assert task["cron_expr"] == "0 9 * * *"

    def test_add_invalid_type_raises(self, scheduler):
        with pytest.raises(ValueError, match="Invalid task type"):
            scheduler.add_task("Bad", "invalid_type", "* * * * *")

    def test_add_invalid_cron_raises(self, scheduler):
        with pytest.raises(ValueError):
            scheduler.add_task("Bad", "script", "bad cron", path="x.py")


class TestTaskSchedulerRemove:
    def test_remove_existing(self, scheduler):
        task = scheduler.add_task("Remove me", "script", "*/5 * * * *", path="x.py")
        assert scheduler.remove_task(task["id"]) is True

    def test_remove_nonexistent(self, scheduler):
        assert scheduler.remove_task("nope") is False


class TestTaskSchedulerUpdate:
    def test_update_name(self, scheduler):
        task = scheduler.add_task("Old", "script", "*/5 * * * *", path="x.py")
        updated = scheduler.update_task(task["id"], name="New")
        assert updated["name"] == "New"

    def test_update_nonexistent_returns_none(self, scheduler):
        assert scheduler.update_task("nope", name="X") is None

    def test_update_schedule_recomputes_cron(self, scheduler):
        task = scheduler.add_task("T", "script", "*/5 * * * *", path="x.py")
        updated = scheduler.update_task(task["id"], schedule="daily_9am")
        assert updated["cron_expr"] == "0 9 * * *"

    def test_update_invalid_type_raises(self, scheduler):
        task = scheduler.add_task("T", "script", "* * * * *", path="x.py")
        with pytest.raises(ValueError, match="Invalid task type"):
            scheduler.update_task(task["id"], type="bad")


class TestTaskSchedulerGetList:
    def test_get_task(self, scheduler):
        task = scheduler.add_task("Find me", "script", "* * * * *", path="x.py")
        found = scheduler.get_task(task["id"])
        assert found is not None
        assert found["name"] == "Find me"

    def test_get_nonexistent(self, scheduler):
        assert scheduler.get_task("nope") is None

    def test_list_tasks(self, scheduler):
        scheduler.add_task("A", "script", "* * * * *", path="a.py")
        scheduler.add_task("B", "script", "* * * * *", path="b.py")
        tasks = scheduler.list_tasks()
        assert len(tasks) == 2

    def test_list_enabled_only(self, scheduler):
        t1 = scheduler.add_task("On", "script", "* * * * *", path="a.py")
        scheduler.add_task("Off", "script", "* * * * *", path="b.py", enabled=False)
        scheduler.disable_task(t1["id"])
        enabled = scheduler.list_tasks(enabled_only=True)
        assert len(enabled) == 0


class TestTaskSchedulerEnableDisable:
    def test_disable_task(self, scheduler):
        task = scheduler.add_task("T", "script", "* * * * *", path="x.py")
        assert scheduler.disable_task(task["id"]) is True
        assert scheduler.get_task(task["id"])["enabled"] is False

    def test_enable_task(self, scheduler):
        task = scheduler.add_task("T", "script", "* * * * *", path="x.py", enabled=False)
        assert scheduler.enable_task(task["id"]) is True
        assert scheduler.get_task(task["id"])["enabled"] is True

    def test_enable_nonexistent(self, scheduler):
        assert scheduler.enable_task("nope") is False


# ---------------------------------------------------------------------------
# TaskScheduler — persistence
# ---------------------------------------------------------------------------


class TestTaskSchedulerPersistence:
    def test_save_and_load(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts1 = TaskScheduler(engine=None, tasks_path=path)
        ts1.add_task("Persist", "script", "*/5 * * * *", path="x.py")
        ts1.stop()

        ts2 = TaskScheduler(engine=None, tasks_path=path)
        tasks = ts2.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["name"] == "Persist"
        ts2.stop()

    def test_load_corrupt_json(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        with Path(path).open("w") as f:
            f.write("not json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        assert ts.list_tasks() == []
        ts.stop()

    def test_load_non_array(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        with Path(path).open("w") as f:
            json.dump({"not": "a list"}, f)
        ts = TaskScheduler(engine=None, tasks_path=path)
        assert ts.list_tasks() == []
        ts.stop()

    def test_load_backfills_cron_expr(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        with Path(path).open("w") as f:
            json.dump(
                [{"id": "abc", "name": "T", "type": "script", "schedule": "every_5m"}],
                f,
            )
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = ts.get_task("abc")
        assert task["cron_expr"] == "*/5 * * * *"
        ts.stop()

    def test_save_is_atomic_write_failure_preserves_existing_file(
        self, tmp_path, monkeypatch
    ):
        # A crash/failure partway through save() must NOT truncate the live
        # tasks file — the new payload is staged in a temp and only renamed
        # into place on success. The atomic path fsyncs the temp before the
        # rename; inject the failure there so the pre-existing tasks survive
        # untouched (old code wrote the live file directly and had no fsync).
        path = tmp_path / "tasks.json"
        seed = TaskScheduler(engine=None, tasks_path=str(path))
        existing_id = seed.add_task("Existing", "script", "*/5 * * * *", path="a.py")["id"]
        seed.stop()
        assert Path(path).exists()

        ts = TaskScheduler(engine=None, tasks_path=str(path))

        def _boom(*args, **kwargs):
            raise OSError("simulated fsync failure")

        monkeypatch.setattr("os.fsync", _boom)
        # add_task persists immediately; its save() must fail atomically and
        # leave the live file holding only the pre-existing task.
        ts.add_task("New", "script", "*/5 * * * *", path="b.py")
        ts.stop()

        # The live file must still contain only the pre-existing task.
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        ids = {t["id"] for t in data}
        assert existing_id in ids
        assert not any(t.get("name") == "New" for t in data), (
            "save() overwrote the live file before atomically replacing it"
        )

    def test_load_quarantines_corrupt_json(self, tmp_path):
        # A truncated/garbled tasks file must be quarantined to .corrupt so the
        # next mutation can't silently overwrite the operator's data, mirroring
        # triggers.py / fleet.py / auth.py.
        path = tmp_path / "tasks.json"
        path.write_text("{not valid json", encoding="utf-8")
        ts = TaskScheduler(engine=None, tasks_path=str(path))
        assert ts.list_tasks() == []
        ts.stop()
        assert not path.exists(), "corrupt file was left in place"
        quarantined = tmp_path / "tasks.json.corrupt"
        assert quarantined.exists(), "corrupt file was not quarantined"


# ---------------------------------------------------------------------------
# TaskScheduler — run_task_now (no engine)
# ---------------------------------------------------------------------------


class TestTaskSchedulerRunNow:
    def test_run_script_no_engine(self, scheduler):
        task = scheduler.add_task("T", "script", "* * * * *", path="x.py")
        result = scheduler.run_task_now(task["id"])
        assert result["success"] is False
        assert "No engine" in result["error"]

    def test_run_goal_no_engine(self, scheduler):
        task = scheduler.add_task("T", "goal", "* * * * *", goal="Do it")
        result = scheduler.run_task_now(task["id"])
        assert result["success"] is False

    def test_run_nonexistent(self, scheduler):
        assert scheduler.run_task_now("nope") is None

    def test_run_updates_last_run(self, scheduler):
        task = scheduler.add_task("T", "script", "* * * * *", path="x.py")
        scheduler.run_task_now(task["id"])
        updated = scheduler.get_task(task["id"])
        assert updated["last_run"] is not None

    def test_run_task_now_does_not_call_on_complete(self, scheduler):
        # run_task_now does not invoke _on_task_complete; only the scheduler tick does.
        results = []
        scheduler.set_on_task_complete(lambda r: results.append(r))
        task = scheduler.add_task("T", "script", "* * * * *", path="x.py")
        scheduler.run_task_now(task["id"])
        assert len(results) == 0


# ---------------------------------------------------------------------------
# _next_run_after
# ---------------------------------------------------------------------------


class TestNextRunAfter:
    def test_finds_next_minute(self):
        after = datetime(2025, 1, 1, 12, 0)
        result = _next_run_after("* * * * *", after)
        assert result == datetime(2025, 1, 1, 12, 1)

    def test_finds_specific_hour(self):
        after = datetime(2025, 1, 1, 8, 30)
        result = _next_run_after("0 9 * * *", after)
        assert result == datetime(2025, 1, 1, 9, 0)

    def test_wraps_to_next_day(self):
        after = datetime(2025, 1, 1, 23, 59)
        result = _next_run_after("0 0 * * *", after)
        assert result == datetime(2025, 1, 2, 0, 0)

    def test_defaults_to_now(self):
        # Should not raise and should return a datetime
        result = _next_run_after("* * * * *")
        assert isinstance(result, datetime)


# ---------------------------------------------------------------------------
# TaskScheduler — scheduler loop
# ---------------------------------------------------------------------------


class TestSchedulerLoop:
    def test_start_and_stop(self, scheduler):
        scheduler.start()
        assert scheduler._running is True
        scheduler.stop()
        assert scheduler._running is False

    def test_tick_runs_due_tasks(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)

        # Use every-minute cron so it's always due
        ts.add_task("Always", "script", "* * * * *", path="x.py")
        results = []
        ts.set_on_task_complete(lambda r: results.append(r))

        ts._tick()
        assert len(results) == 1
        assert results[0]["task_name"] == "Always"
        ts.stop()

    def test_tick_skips_disabled_tasks(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)

        task = ts.add_task("Disabled", "script", "* * * * *", path="x.py")
        ts.disable_task(task["id"])

        results = []
        ts.set_on_task_complete(lambda r: results.append(r))
        ts._tick()
        assert len(results) == 0
        ts.stop()

    def test_tick_updates_last_run(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)

        ts.add_task("T", "script", "* * * * *", path="x.py")
        ts._tick()

        updated = ts.get_task(ts.list_tasks()[0]["id"])
        assert updated["last_run"] is not None
        ts.stop()


# ---------------------------------------------------------------------------
# TaskScheduler — _handle_on_complete
# ---------------------------------------------------------------------------


class TestHandleOnComplete:
    def test_on_complete_disable(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = ts.add_task("AutoDisable", "script", "* * * * *", path="x.py", on_complete="disable")
        ts._tick()
        updated = ts.get_task(task["id"])
        assert updated["enabled"] is False
        ts.stop()

    def test_on_complete_remove(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = ts.add_task("AutoRemove", "script", "* * * * *", path="x.py", on_complete="remove")
        ts._tick()
        assert ts.get_task(task["id"]) is None
        ts.stop()


# ---------------------------------------------------------------------------
# TaskScheduler — powershell dispatch
# ---------------------------------------------------------------------------


class TestTaskSchedulerPowerShell:
    def test_run_powershell_no_engine(self, scheduler):
        task = scheduler.add_task("PS", "powershell", "* * * * *", command="Get-Date")
        result = scheduler.run_task_now(task["id"])
        assert result["success"] is False
        assert "No engine" in result["error"]

    def test_run_powershell_with_mock_engine(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        ps = MagicMock()
        ps.run_command.return_value = MagicMock(
            success=True, exit_code=0, stdout="output", stderr="", objects=[]
        )
        engine.powershell = ps
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = ts.add_task("PS", "powershell", "* * * * *", command="Get-Date")
        result = ts.run_task_now(task["id"])
        assert result["success"] is True
        ts.stop()


# ---------------------------------------------------------------------------
# Edge cases — callback exceptions and multi-task ticks
# ---------------------------------------------------------------------------


class TestSchedulerEdgeCases:
    def test_on_task_complete_exception_does_not_crash_tick(self, tmp_path):
        """An on_task_complete callback that raises must not propagate out of _tick."""
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        ts.add_task("T", "script", "* * * * *", path="x.py")

        crash_count = [0]

        def bad_callback(result):
            crash_count[0] += 1
            raise RuntimeError("callback exploded")

        ts.set_on_task_complete(bad_callback)
        ts._tick()  # must not raise
        assert crash_count[0] == 1
        ts.stop()

    def test_multiple_tasks_in_same_tick_all_run(self, tmp_path):
        """Multiple due tasks in a single _tick should all execute."""
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        ts.add_task("T1", "script", "* * * * *", path="a.py")
        ts.add_task("T2", "script", "* * * * *", path="b.py")
        ts.add_task("T3", "script", "* * * * *", path="c.py")

        ran = []
        ts.set_on_task_complete(lambda r: ran.append(r))
        ts._tick()
        assert len(ran) == 3
        ts.stop()

    def test_disabled_task_skipped_in_tick(self, tmp_path):
        """A disabled task must not run even if its cron is due."""
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = ts.add_task("Disabled", "script", "* * * * *", path="x.py")
        ts.update_task(task["id"], enabled=False)

        ran = []
        ts.set_on_task_complete(lambda r: ran.append(r))
        ts._tick()
        assert ran == []
        ts.stop()

    def test_tick_with_invalid_cron_logs_warning_and_continues(self, tmp_path):
        """A task with invalid cron must be skipped; the valid task next to it must still run."""
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        bad = ts.add_task("BadCron", "script", "* * * * *", path="x.py")
        ts.add_task("GoodCron", "script", "* * * * *", path="y.py")

        # Force the bad task to have an unparseable cron expression
        with ts._lock:
            ts._tasks[bad["id"]]["cron_expr"] = "not_a_cron"

        ran = []
        ts.set_on_task_complete(lambda r: ran.append(r))
        ts._tick()
        assert len(ran) == 1  # only the good task ran
        ts.stop()
