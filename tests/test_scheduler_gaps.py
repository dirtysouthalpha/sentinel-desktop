"""Gap tests for scheduler.py — edge cases in cron parsing, execution dispatch, scheduler loop."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.scheduler import (
    TaskScheduler,
    _next_run_after,
    _parse_cron_field,
)


class TestParseCronFieldStepZero:
    """_parse_cron_field with step <= 0 continues without matching."""

    def test_step_zero_returns_false(self):
        assert _parse_cron_field("*/0", 0, (0, 59)) is False

    def test_step_negative_returns_false(self):
        assert _parse_cron_field("*/-1", 0, (0, 59)) is False


class TestNextRunAfterNoMatch:
    """_next_run_after returns far-future when nothing matches."""

    def test_impossible_cron_returns_far_future(self):
        # Feb 30 never exists, so month=2 day=30 can never match
        after = datetime(2025, 1, 1, 0, 0)
        result = _next_run_after("0 0 30 2 *", after)
        # Should return after + 730 days
        assert result.year >= 2027


class TestStartAlreadyRunning:
    """start() warns when already running."""

    def test_double_start_logs_warning(self):
        ts = TaskScheduler(engine=None, tasks_path=str(Path(__file__).parent / "_noop.json"))
        ts.start()
        with patch("core.scheduler.logger") as mock_log:
            ts.start()
            mock_log.warning.assert_called()
        ts.stop()


class TestSaveOSError:
    """save() handles OSError gracefully."""

    def test_save_oserror_does_not_raise(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        ts.add_task("T", "script", "* * * * *", path="x.py")
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            ts.save()  # Should not raise


class TestExecuteUnknownTaskType:
    """_execute_task handles unknown task types."""

    def test_unknown_type_returns_error(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = {"id": "x", "name": "Test", "type": "unknown_type"}
        result = ts._execute_task(task)
        assert result["success"] is False
        assert "Unknown task type" in result["error"]

    def test_exception_during_execution(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = {"id": "x", "name": "Test", "type": "goal", "goal": "do stuff"}
        engine = MagicMock()
        engine.run.side_effect = RuntimeError("boom")
        ts.engine = engine
        result = ts._execute_task(task)
        assert result["success"] is False
        assert "boom" in result["error"]


class TestExecScriptWithEngine:
    """_exec_script delegates to engine.script_engine."""

    def test_with_script_engine(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        sr = MagicMock(success=True, error="", steps_completed=2, steps_total=3, duration_ms=100)
        engine.script_engine.run_script.return_value = sr
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = ts.add_task("S", "script", "* * * * *", path="test.json")
        result = ts.run_task_now(task["id"])
        assert result["success"] is True
        assert result["output"]["steps_completed"] == 2
        ts.stop()


class TestExecGoalWithEngine:
    """_exec_goal delegates to engine.run."""

    def test_goal_with_engine(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.run.return_value = {"success": True, "error": None}
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = ts.add_task("G", "goal", "* * * * *", goal="Open Chrome")
        result = ts.run_task_now(task["id"])
        assert result["success"] is True
        engine.run.assert_called_once_with("Open Chrome")
        ts.stop()

    def test_goal_no_goal_specified(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=MagicMock(), tasks_path=path)
        task = ts.add_task("G", "goal", "* * * * *", goal=None)
        result = ts.run_task_now(task["id"])
        assert result["success"] is False
        assert "no goal" in result["error"].lower()
        ts.stop()


class TestExecPowerShellEdgeCases:
    """_exec_powershell edge cases."""

    def test_with_path(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        ps = MagicMock()
        ps.run_script.return_value = MagicMock(
            success=True, exit_code=0, stdout="", stderr="", objects=[]
        )
        engine.powershell = ps
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = ts.add_task("PS", "powershell", "* * * * *", path="script.ps1")
        result = ts.run_task_now(task["id"])
        assert result["success"] is True
        ps.run_script.assert_called_once_with("script.ps1")
        ts.stop()

    def test_no_path_no_command(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.powershell = MagicMock()
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = ts.add_task("PS", "powershell", "* * * * *")
        result = ts.run_task_now(task["id"])
        assert result["success"] is False
        assert "needs" in result["error"].lower()
        ts.stop()


class TestSchedulerLoopException:
    """_scheduler_loop handles tick exceptions."""

    def test_tick_exception_does_not_crash_loop(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        call_count = 0

        def fake_tick():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("tick failed")
            ts._stop_event.set()

        with patch.object(ts, "_tick", side_effect=fake_tick), \
             patch.object(ts._stop_event, "wait", return_value=False):
            ts._scheduler_loop()
        assert call_count == 2


class TestTickInvalidCron:
    """_tick handles invalid cron expressions."""

    def test_invalid_cron_skips_task(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = ts.add_task("T", "script", "* * * * *", path="x.py")
        # Corrupt cron_expr
        ts._tasks[task["id"]]["cron_expr"] = "bad"
        results = []
        ts.set_on_task_complete(lambda r: results.append(r))
        ts._tick()
        assert len(results) == 0
        ts.stop()

    def test_empty_cron_skips_task(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = ts.add_task("T", "script", "* * * * *", path="x.py")
        ts._tasks[task["id"]]["cron_expr"] = ""
        results = []
        ts.set_on_task_complete(lambda r: results.append(r))
        ts._tick()
        assert len(results) == 0
        ts.stop()


class TestOnTaskCompleteCallbackException:
    """on_task_complete callback exceptions are caught."""

    def test_callback_exception_does_not_crash_tick(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        ts.add_task("T", "script", "* * * * *", path="x.py")
        ts.set_on_task_complete(lambda r: (_ for _ in ()).throw(RuntimeError("cb fail")))
        ts._tick()  # Should not raise
        ts.stop()
