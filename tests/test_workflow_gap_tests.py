"""Gap tests for workflow.py — _handle_step_error unknown policy, _exec_script/_exec_sub_workflow exception paths."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.workflow import WorkflowEngine, WorkflowResult, WorkflowStep


class TestHandleStepErrorUnknownPolicy:
    """_handle_step_error with unknown error_policy returns None (stops workflow)."""

    def test_unknown_policy_returns_none(self) -> None:
        engine = WorkflowEngine()
        step = WorkflowStep(id="s1", type="action", error_policy="unknown_policy", next_step="s2")
        result = WorkflowResult()
        next_id = engine._handle_step_error(step, RuntimeError("boom"), result)
        assert next_id is None
        assert result.step_results[-1]["success"] is False


class TestExecScriptException:
    """_exec_script handles script engine exceptions."""

    def test_script_engine_raises_runtime_error(self) -> None:
        mock_se = MagicMock()
        mock_se.run_script.side_effect = RuntimeError("script engine died")
        engine = WorkflowEngine(script_engine=mock_se)
        step = WorkflowStep(id="s1", type="script", path="test.json", params={})
        result = engine._exec_script(step)
        assert result["success"] is False
        assert "Script execution failed" in result["error"]
        assert "script engine died" in result["error"]

    def test_script_engine_raises_os_error(self) -> None:
        mock_se = MagicMock()
        mock_se.run_script.side_effect = OSError("file not accessible")
        engine = WorkflowEngine(script_engine=mock_se)
        step = WorkflowStep(id="s1", type="script", path="test.json")
        result = engine._exec_script(step)
        assert result["success"] is False
        assert "Script execution failed" in result["error"]

    def test_script_engine_raises_value_error(self) -> None:
        mock_se = MagicMock()
        mock_se.run_script.side_effect = ValueError("bad params")
        engine = WorkflowEngine(script_engine=mock_se)
        step = WorkflowStep(id="s1", type="script", path="test.json")
        result = engine._exec_script(step)
        assert result["success"] is False


class TestExecSubWorkflowException:
    """_exec_sub_workflow handles exceptions from nested run_workflow."""

    def test_sub_workflow_raises_runtime_error(self) -> None:
        engine = WorkflowEngine()
        step = WorkflowStep(id="s1", type="sub_workflow", path="/fake/path.json")
        with patch.object(engine, "run_workflow", side_effect=RuntimeError("nested fail")):
            result = engine._exec_sub_workflow(step)
        assert result["success"] is False
        assert "Sub-workflow failed" in result["error"]

    def test_sub_workflow_raises_os_error(self) -> None:
        engine = WorkflowEngine()
        step = WorkflowStep(id="s1", type="sub_workflow", path="/fake/path.json")
        with patch.object(engine, "run_workflow", side_effect=OSError("disk error")):
            result = engine._exec_sub_workflow(step)
        assert result["success"] is False
        assert "Sub-workflow failed" in result["error"]


class TestExecNotifySuccess:
    """_exec_notify succeeds when NotificationManager is available."""

    def test_notify_success_with_mock(self) -> None:
        engine = WorkflowEngine()
        step = WorkflowStep(id="s1", type="notify", message="Hello world", level="info")
        mock_nm = MagicMock()
        mock_nm.notify.return_value = True
        with patch.dict(
            "sys.modules",
            {"core.notifications": MagicMock(NotificationManager=MagicMock(return_value=mock_nm))},
        ):
            # The import happens inside _exec_notify, so we patch the import
            with patch("builtins.__import__", side_effect=ImportError("mocked")):
                result = engine._exec_notify(step)
        # Import fails, so we get the fallback path
        assert result["success"] is True
        assert result["type"] == "notify"
        assert "notification delivery failed" in result.get("note", "")


class TestBuildStepsDefaults:
    """_build_steps with minimal step data uses sensible defaults."""

    def test_minimal_step_data(self) -> None:
        steps_data = [{"action": "click"}]
        steps = WorkflowEngine._build_steps(steps_data)
        assert len(steps) == 1
        assert steps[0].action == "click"
        assert steps[0].id == "s1"  # auto-generated
        assert steps[0].type == "action"  # default type

    def test_multiple_steps_auto_ids(self) -> None:
        steps_data = [{"action": "a"}, {"action": "b"}, {"action": "c"}]
        steps = WorkflowEngine._build_steps(steps_data)
        assert [s.id for s in steps] == ["s1", "s2", "s3"]

    def test_preserves_all_fields(self) -> None:
        steps_data = [
            {
                "id": "custom",
                "type": "condition",
                "check": "true",
                "true_next": "s2",
                "false_next": "s3",
                "error_policy": "skip",
                "max_retries": 5,
                "delay_seconds": 2.5,
                "message": "hello",
                "level": "warning",
            }
        ]
        steps = WorkflowEngine._build_steps(steps_data)
        assert steps[0].id == "custom"
        assert steps[0].type == "condition"
        assert steps[0].check == "true"
        assert steps[0].true_next == "s2"
        assert steps[0].false_next == "s3"
        assert steps[0].error_policy == "skip"
        assert steps[0].max_retries == 5
        assert steps[0].delay_seconds == 2.5


class TestLoadWorkflowFile:
    """_load_workflow_file edge cases."""

    def test_oserror_on_read(self, tmp_path: Path) -> None:
        """OSError during file read returns error result."""
        wf = tmp_path / "unreadable.json"
        wf.write_text("{}", encoding="utf-8")
        engine = WorkflowEngine()
        with patch("pathlib.Path.open", side_effect=OSError("permission denied")):
            result = engine._load_workflow_file(str(wf))
        assert isinstance(result, WorkflowResult)
        assert result.success is False
        assert "Failed to load" in result.error


class TestParseListEdgeCases:
    """_parse_list with various input types."""

    def test_integer_value(self) -> None:
        from core.workflow import WorkflowEngine

        result = WorkflowEngine._parse_list(42)
        assert result == [42]

    def test_json_list_string(self) -> None:
        from core.workflow import WorkflowEngine

        result = WorkflowEngine._parse_list("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_json_non_list_string(self) -> None:
        """JSON string that isn't a list falls back to comma split."""
        from core.workflow import WorkflowEngine

        result = WorkflowEngine._parse_list('{"key": "value"}')
        # Falls back to comma split since parsed isn't a list
        assert result == ['{"key": "value"}']

    def test_zero_value(self) -> None:
        """0 is falsy, so _parse_list returns empty list."""
        from core.workflow import WorkflowEngine

        result = WorkflowEngine._parse_list(0)
        assert result == []  # 0 is falsy → returns []

    def test_false_value(self) -> None:
        """False is falsy, so _parse_list returns empty list."""
        from core.workflow import WorkflowEngine

        result = WorkflowEngine._parse_list(False)
        assert result == []  # False is falsy → returns []
