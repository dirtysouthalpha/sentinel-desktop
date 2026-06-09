"""Gap tests for scheduler.py — _exec_goal no-success-key, _exec_powershell command, load
OSError.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.scheduler import TaskScheduler


class TestExecGoalNoSuccessKey:
    """_exec_goal handles engine.run() returning dict without 'success' key."""

    def test_missing_success_key_defaults_to_true(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        # Dict without "success" key — should default to True
        engine.run.return_value = {"steps": 3, "output": "done"}
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = ts.add_task("G", "goal", "* * * * *", goal="Open Chrome")
        result = ts.run_task_now(task["id"])
        assert result["success"] is True
        assert result["output"]["steps"] == 3
        ts.stop()

    def test_success_false_returns_false(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        engine.run.return_value = {"success": False, "error": "timeout"}
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = ts.add_task("G", "goal", "* * * * *", goal="Open Chrome")
        result = ts.run_task_now(task["id"])
        assert result["success"] is False
        assert result["error"] == "timeout"
        ts.stop()


class TestExecPowershellCommand:
    """_exec_powershell with command field (not path)."""

    def test_command_branch_calls_run_command(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        ps = MagicMock()
        ps.run_command.return_value = MagicMock(
            success=True, exit_code=0, stdout="OK", stderr="", objects=[{"Name": "Test"}]
        )
        engine.powershell = ps
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = ts.add_task("PS", "powershell", "* * * * *", command="Get-Process")
        result = ts.run_task_now(task["id"])
        assert result["success"] is True
        ps.run_command.assert_called_once_with("Get-Process")
        assert result["output"]["objects"] == [{"Name": "Test"}]
        ts.stop()

    def test_command_failure_returns_error(self, tmp_path):
        path = str(tmp_path / "tasks.json")
        engine = MagicMock()
        ps = MagicMock()
        ps.run_command.return_value = MagicMock(
            success=False, exit_code=1, stdout="", stderr="Access denied", objects=[]
        )
        engine.powershell = ps
        ts = TaskScheduler(engine=engine, tasks_path=path)
        task = ts.add_task("PS", "powershell", "* * * * *", command="Remove-Item")
        result = ts.run_task_now(task["id"])
        assert result["success"] is False
        assert result["error"] == "Access denied"
        ts.stop()


class TestLoadOSError:
    """load() handles OSError when reading the file."""

    def test_load_oserror_clears_tasks(self, tmp_path):
        path = tmp_path / "tasks.json"
        path.write_text("not valid json anyway", encoding="utf-8")
        ts = TaskScheduler(engine=None, tasks_path=str(path))
        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            ts.load()  # Should not raise
        assert len(ts.list_tasks()) == 0
        ts.stop()


class TestLoadCorruptJson:
    """load() handles corrupt JSON."""

    def test_load_corrupt_json_clears_tasks(self, tmp_path):
        path = tmp_path / "tasks.json"
        path.write_text("{bad json", encoding="utf-8")
        ts = TaskScheduler(engine=None, tasks_path=str(path))
        ts.load()
        assert len(ts.list_tasks()) == 0
        ts.stop()

    def test_load_non_array_json_clears_tasks(self, tmp_path):
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps({"not": "an array"}), encoding="utf-8")
        ts = TaskScheduler(engine=None, tasks_path=str(path))
        ts.load()
        assert len(ts.list_tasks()) == 0
        ts.stop()
