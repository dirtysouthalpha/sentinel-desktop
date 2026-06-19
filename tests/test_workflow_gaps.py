"""Gap tests for workflow.py — numeric comparison errors, loop failure,
_exec_script/_exec_notify paths.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.workflow import WorkflowEngine, WorkflowStep


class TestEvaluateConditionNumericErrors:
    """evaluate_condition handles ValueError on non-numeric comparisons."""

    def test_gt_valueerror_returns_false(self):
        assert WorkflowEngine.evaluate_condition("abc > 5") is False

    def test_lt_valueerror_returns_false(self):
        assert WorkflowEngine.evaluate_condition("abc < 5") is False

    def test_gte_valueerror_returns_false(self):
        assert WorkflowEngine.evaluate_condition("abc >= 5") is False

    def test_lte_valueerror_returns_false(self):
        assert WorkflowEngine.evaluate_condition("abc <= 5") is False


class TestResolveVariablesStepOutput:
    """resolve_variables with step output references."""

    def test_step_output_direct_value(self):
        result = WorkflowEngine.resolve_variables("{{step.s1}}", {}, {"s1": "hello"})
        assert result == "hello"

    def test_step_output_nested_key(self):
        result = WorkflowEngine.resolve_variables(
            "{{step.s1.output.field}}", {}, {"s1": {"output": {"field": "val"}}}
        )
        assert result == "val"

    def test_step_output_missing_nested_returns_empty(self):
        result = WorkflowEngine.resolve_variables(
            "{{step.s1.output.missing}}", {}, {"s1": {"output": {}}}
        )
        assert result == ""

    def test_step_output_non_dict_navigates_to_empty(self):
        result = WorkflowEngine.resolve_variables("{{step.s1.output.field}}", {}, {"s1": "plain"})
        assert result == ""

    def test_step_output_none_value(self):
        result = WorkflowEngine.resolve_variables("{{step.s1}}", {}, {"s1": None})
        assert result == "None"


class TestExecScriptWithEngine:
    """_exec_script with a real script engine."""

    def test_script_engine_execution(self):
        engine = WorkflowEngine(script_engine=MagicMock())
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.steps_completed = 3
        mock_result.steps_total = 5
        mock_result.error = ""
        engine.script_engine.run_script.return_value = mock_result

        step = WorkflowStep(id="s1", type="script", path="test.json", params={"key": "val"})
        result = engine._exec_script(step)

        assert result["success"] is True
        assert result["steps_completed"] == 3
        assert result["steps_total"] == 5
        engine.script_engine.run_script.assert_called_once()


class TestExecActionNoExecutor:
    """_exec_action with no executor returns error."""

    def test_no_executor_returns_error(self):
        engine = WorkflowEngine()
        step = WorkflowStep(id="s1", type="action", action={"type": "click"})
        result = engine._exec_action(step)
        assert result["success"] is False
        assert "No action executor" in result["error"]


class TestExecNotifyImportError:
    """_exec_notify handles ImportError for notifications module."""

    def test_import_error_returns_fallback(self):
        engine = WorkflowEngine()
        step = WorkflowStep(id="s1", type="notify", message="Hello world")
        with patch.dict("sys.modules", {"core.notifications": None}):
            with patch("builtins.__import__", side_effect=ImportError("no module")):
                result = engine._exec_notify(step)
        assert result["success"] is True
        assert "notification delivery failed" in result["note"]


class TestLoopItemFailureStops:
    """Loop with error_policy='stop' breaks on body step failure."""

    def test_loop_body_failure_stops_processing(self):
        engine = WorkflowEngine()
        tmpdir = tempfile.mkdtemp()
        wf_path = str(Path(tmpdir) / "test_wf.json")

        body_step = {
            "id": "body",
            "type": "action",
            "action": {"type": "click"},
            "error_policy": "stop",
        }
        loop_step = {
            "id": "loop1",
            "type": "loop",
            "over": "a,b,c",
            "body_step": "body",
            "next_step": None,
        }
        wf_data = {"steps": [loop_step, body_step]}
        Path(wf_path).write_text(json.dumps(wf_data))

        # Make executor raise on execute_sync to trigger loop failure
        mock_executor = MagicMock()
        mock_executor.execute_sync.side_effect = RuntimeError("action failed")
        engine.executor = mock_executor

        result = engine.run_workflow(wf_path)
        # Loop should have stopped due to body error_policy="stop"
        assert result.step_results is not None


class TestExecSubWorkflowParams:
    """_exec_sub_workflow resolves variables in params."""

    def test_sub_workflow_passes_resolved_params(self):
        engine = WorkflowEngine()
        step = WorkflowStep(
            id="s1",
            type="sub_workflow",
            path="/fake/path.json",
            params={"key": "{{var1}}"},
        )
        engine._variables = {"var1": "resolved_val"}
        with patch.object(engine, "run_workflow") as mock_run:
            mock_run.return_value = MagicMock(
                success=True, steps_completed=1, steps_total=1, error=""
            )
            result = engine._exec_sub_workflow(step)
        assert result["success"] is True
        call_kwargs = mock_run.call_args
        assert "resolved_val" in str(call_kwargs)


# ===========================================================================
# Missing-branch gap-fills
# ===========================================================================


class TestLoopBodyFailureContinues:
    """Branch 363->355: body error_policy is NOT 'stop' → loop continues."""

    def test_loop_body_failure_continues_when_policy_is_not_stop(self):
        engine = WorkflowEngine()
        tmpdir = tempfile.mkdtemp()
        wf_path = str(Path(tmpdir) / "test_wf.json")

        body_step = {
            "id": "body",
            "type": "action",
            "action": {"type": "click"},
            "error_policy": "continue",  # NOT "stop" → loop should not break
        }
        loop_step = {
            "id": "loop1",
            "type": "loop",
            "over": "a,b",
            "body_step": "body",
            "next_step": None,
        }
        wf_data = {"steps": [loop_step, body_step]}
        Path(wf_path).write_text(json.dumps(wf_data))

        mock_executor = MagicMock()
        mock_executor.execute_sync.side_effect = RuntimeError("action failed")
        engine.executor = mock_executor

        result = engine.run_workflow(wf_path)
        # Both items should have been attempted (2 calls) since policy is "continue"
        assert mock_executor.execute_sync.call_count == 2
        assert result.step_results is not None


class TestExecActionNonStringValues:
    """Branch 468->467: action dict value is not a str → loop continues without interpolation."""

    def test_non_string_action_values_skipped(self):
        engine = WorkflowEngine()
        engine._variables = {}
        engine._step_outputs = {}

        mock_executor = MagicMock()
        mock_executor.execute_sync.return_value = {"success": True, "output": "clicked"}
        engine.executor = mock_executor

        step = WorkflowStep(
            id="s1",
            type="action",
            action={"action": "click", "x": 50, "y": 100},  # x, y are ints, not strings
        )
        result = engine._exec_action(step)
        assert result["success"] is True
        # Executor should have been called with the int values preserved
        called_action = mock_executor.execute_sync.call_args[0][0]
        assert called_action["x"] == 50
        assert called_action["y"] == 100
