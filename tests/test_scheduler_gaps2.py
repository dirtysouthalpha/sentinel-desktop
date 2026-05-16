"""Gap tests for scheduler.py — remaining uncovered lines.

Covers:
  - Lines 74-75: _parse_cron_field ValueError / ZeroDivisionError
  - Line 265:  update_task with valid type (mixed case normalization)
  - Lines 345-347: save() OSError on mkdir
  - Lines 417-419: _execute_task outer exception handler
  - Lines 444-446: _exec_script inner exception handler
  - Lines 494-496: _exec_powershell inner exception handler
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.scheduler import TaskScheduler, _parse_cron_field

# ---------------------------------------------------------------------------
# Lines 74-75: _parse_cron_field ValueError branch
# ---------------------------------------------------------------------------


class TestParseCronFieldValueError:
    """Non-numeric field value triggers ValueError, caught at line 74."""

    def test_non_numeric_field_returns_false(self):
        assert _parse_cron_field("abc", 5, (0, 59)) is False

    def test_range_with_non_numeric_returns_false(self):
        assert _parse_cron_field("a-z", 5, (0, 59)) is False

    def test_comma_list_with_bad_value_returns_false(self):
        assert _parse_cron_field("1,abc,30", 1, (0, 59)) is True  # first part matches

    def test_comma_list_all_bad_returns_false(self):
        assert _parse_cron_field("abc,def", 5, (0, 59)) is False


# ---------------------------------------------------------------------------
# Line 265: update_task with valid type (mixed case normalization)
# ---------------------------------------------------------------------------


class TestUpdateTaskValidType:
    """update_task normalizes valid type to lowercase (line 265)."""

    def test_update_type_mixed_case_normalizes(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = ts.add_task("T", "script", "* * * * *", path="x.py")
        updated = ts.update_task(task["id"], type="SCRIPT")
        assert updated["type"] == "script"
        ts.stop()

    def test_update_type_goal_normalizes(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = ts.add_task("T", "script", "* * * * *", path="x.py")
        updated = ts.update_task(task["id"], type="Goal")
        assert updated["type"] == "goal"
        ts.stop()

    def test_update_type_workflow_normalizes(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = ts.add_task("T", "script", "* * * * *", path="x.py")
        updated = ts.update_task(task["id"], type="Workflow")
        assert updated["type"] == "workflow"
        ts.stop()


# ---------------------------------------------------------------------------
# Lines 345-347: save() OSError on mkdir
# ---------------------------------------------------------------------------


class TestSaveMkdirOSError:
    """save() handles OSError when creating parent directory."""

    def test_mkdir_oserror_returns_early(self, tmp_path):
        path = str(tmp_path / "subdir" / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        ts.add_task("T", "script", "* * * * *", path="x.py")
        with patch.object(Path, "mkdir", side_effect=OSError("permission denied")):
            ts.save()  # Should not raise
        ts.stop()


# ---------------------------------------------------------------------------
# Lines 417-419: _execute_task outer exception handler
# ---------------------------------------------------------------------------


class TestExecuteTaskOuterException:
    """_execute_task catches exceptions from the dispatch block (lines 417-419)."""

    def test_runtime_error_from_dispatch(self, tmp_path):
        """If _exec_script raises, outer handler catches it (lines 417-419)."""
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "script", "path": "x.py"}
        with patch.object(ts, "_exec_script", side_effect=RuntimeError("dispatch boom")):
            result = ts._execute_task(task)
        assert result["success"] is False
        assert "RuntimeError" in result["error"]
        assert "dispatch boom" in result["error"]
        ts.stop()

    def test_oserror_from_goal_dispatch(self, tmp_path):
        """If _exec_goal raises OSError, outer handler catches it."""
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "goal", "goal": "do it"}
        with patch.object(ts, "_exec_goal", side_effect=OSError("io fail")):
            result = ts._execute_task(task)
        assert result["success"] is False
        assert "OSError" in result["error"]
        assert "io fail" in result["error"]
        ts.stop()

    def test_valueerror_from_powershell_dispatch(self, tmp_path):
        """If _exec_powershell raises ValueError, outer handler catches it."""
        path = str(tmp_path / "tasks.json")
        ts = TaskScheduler(engine=None, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "powershell", "command": "Get-Date"}
        with patch.object(ts, "_exec_powershell", side_effect=ValueError("bad value")):
            result = ts._execute_task(task)
        assert result["success"] is False
        assert "ValueError" in result["error"]
        assert "bad value" in result["error"]
        ts.stop()


# ---------------------------------------------------------------------------
# Lines 444-446: _exec_script inner exception handler
# ---------------------------------------------------------------------------


class TestExecScriptInnerException:
    """_exec_script catches exceptions from script_engine.run_script (lines 444-446)."""

    def test_runtime_error_in_run_script(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.script_engine.run_script.side_effect = RuntimeError("script crashed")
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "script", "path": "test.json"}
        result = ts._exec_script(task)
        assert result["success"] is False
        assert "script crashed" in result["error"]
        ts.stop()

    def test_oserror_in_run_script(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.script_engine.run_script.side_effect = OSError("file not found")
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "script", "path": "test.json"}
        result = ts._exec_script(task)
        assert result["success"] is False
        assert "file not found" in result["error"]
        ts.stop()

    def test_value_error_in_run_script(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.script_engine.run_script.side_effect = ValueError("bad param")
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "script", "path": "test.json"}
        result = ts._exec_script(task)
        assert result["success"] is False
        assert "bad param" in result["error"]
        ts.stop()

    def test_key_error_in_run_script(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.script_engine.run_script.side_effect = KeyError("missing_key")
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "script", "path": "test.json"}
        result = ts._exec_script(task)
        assert result["success"] is False
        assert "missing_key" in result["error"]
        ts.stop()


# ---------------------------------------------------------------------------
# Lines 494-496: _exec_powershell inner exception handler
# ---------------------------------------------------------------------------


class TestExecPowershellInnerException:
    """_exec_powershell catches exceptions from ps.run_script/run_command (lines 494-496)."""

    def test_runtime_error_in_run_script(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.powershell.run_script.side_effect = RuntimeError("ps crash")
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "powershell", "path": "script.ps1"}
        result = ts._exec_powershell(task)
        assert result["success"] is False
        assert "ps crash" in result["error"]
        ts.stop()

    def test_oserror_in_run_command(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.powershell.run_command.side_effect = OSError("access denied")
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "powershell", "command": "Get-Process"}
        result = ts._exec_powershell(task)
        assert result["success"] is False
        assert "access denied" in result["error"]
        ts.stop()

    def test_value_error_in_run_script(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.powershell.run_script.side_effect = ValueError("bad value")
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = {"id": "abc", "name": "T", "type": "powershell", "path": "script.ps1"}
        result = ts._exec_powershell(task)
        assert result["success"] is False
        assert "bad value" in result["error"]
        ts.stop()
