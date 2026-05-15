"""Edge-case tests for core/workflow.py — coverage gaps in existing test_workflow.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.workflow import WorkflowEngine


class TestCycleDetection:
    """Verify the engine stops on non-LOOP cycles instead of infinite loops."""

    def test_cycle_stops_gracefully(self, tmp_path: Path) -> None:
        wf_data = {
            "steps": [
                {"id": "s1", "type": "delay", "delay_seconds": 0.001, "next_step": "s2"},
                {"id": "s2", "type": "delay", "delay_seconds": 0.001, "next_step": "s1"},
            ]
        }
        wf = tmp_path / "cycle.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        # Each step should only run once — cycle detected, stops after 2 steps
        assert result.steps_completed == 2


class TestLoopWithVariable:
    """Loop over referenced from a variable rather than a literal."""

    def test_loop_over_variable(self, tmp_path: Path) -> None:
        wf_data = {
            "variables": {"items": "x,y,z"},
            "steps": [
                {
                    "id": "s1",
                    "type": "loop",
                    "over": "{{items}}",
                    "body_step": "s2",
                    "next_step": None,
                },
                {"id": "s2", "type": "delay", "delay_seconds": 0.001},
            ],
        }
        wf = tmp_path / "loop_var.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.success is True
        loop_output = result.outputs.get("s1", {})
        assert loop_output.get("items_processed") == 3


class TestLoopWithMissingBodyStep:
    """Loop body_step pointing to nonexistent step should degrade gracefully."""

    def test_loop_missing_body_step(self, tmp_path: Path) -> None:
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "loop",
                    "over": "a,b",
                    "body_step": "nonexistent",
                    "next_step": None,
                },
            ],
        }
        wf = tmp_path / "loop_missing_body.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.steps_completed == 1


class TestLoopBodyErrorPolicyStop:
    """Loop body that fails with stop policy should break the loop."""

    def test_loop_body_failure_stops(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.execute_sync.side_effect = RuntimeError("fail")
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "loop",
                    "over": "a,b,c",
                    "body_step": "s2",
                    "next_step": None,
                },
                {
                    "id": "s2",
                    "type": "action",
                    "action": {"type": "click"},
                    "error_policy": "stop",
                },
            ],
        }
        wf = tmp_path / "loop_fail.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine(action_executor=executor)
        result = engine.run_workflow(str(wf))
        # Loop records failure
        loop_output = result.outputs.get("s1", {})
        assert loop_output.get("success") is False


class TestRetryWithZeroMaxRetries:
    """Retry policy with max_retries=0 should fail immediately."""

    def test_retry_zero_retries(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.execute_sync.side_effect = RuntimeError("boom")
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "action",
                    "action": {"type": "click"},
                    "error_policy": "retry",
                    "max_retries": 0,
                    "next_step": None,
                },
            ],
        }
        wf = tmp_path / "retry_zero.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine(action_executor=executor)
        result = engine.run_workflow(str(wf))
        assert result.success is False
        assert "0 retries" in result.error


class TestResolveVariablesEdgeCases:
    """resolve_variables with None values and non-dict step outputs."""

    def test_none_variable_value(self) -> None:
        result = WorkflowEngine.resolve_variables("{{key}}", {"key": None}, {})
        assert result == ""

    def test_step_output_non_dict_value(self) -> None:
        result = WorkflowEngine.resolve_variables("{{step.s1.output}}", {}, {"s1": "just_a_string"})
        # Non-dict step output: key navigation fails, returns ""
        assert result == ""

    def test_step_output_int_value(self) -> None:
        result = WorkflowEngine.resolve_variables("{{step.s1.count}}", {}, {"s1": 42})
        assert result == ""

    def test_whitespace_only_expression(self) -> None:
        result = WorkflowEngine.evaluate_condition("  ")
        assert result is False

    def test_whitespace_trimmed_truthy(self) -> None:
        result = WorkflowEngine.evaluate_condition("  True ")
        assert result is True


class TestUnknownStepType:
    """_execute_step with an unrecognized type returns an error."""

    def test_unknown_type_in_workflow(self, tmp_path: Path) -> None:
        wf_data = {
            "steps": [
                {"id": "s1", "type": "nonsense", "next_step": None},
            ]
        }
        wf = tmp_path / "unknown.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.success is True  # step itself succeeded (no error_policy=stop)
        assert result.step_results[0]["success"] is False
        assert "Unknown step type" in result.step_results[0]["error"]


class TestCallbackExceptionHandling:
    """A failing callback should not crash the workflow."""

    def test_failing_callback_does_not_crash(self, tmp_path: Path) -> None:
        wf_data = {
            "steps": [
                {"id": "s1", "type": "delay", "delay_seconds": 0.001, "next_step": None},
            ]
        }
        wf = tmp_path / "cb_fail.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        engine.set_callback(
            "on_step_start", lambda sid: (_ for _ in ()).throw(RuntimeError("cb boom"))
        )
        result = engine.run_workflow(str(wf))
        assert result.success is True
        assert result.steps_completed == 1


class TestAutoGeneratedStepIds:
    """Steps without explicit IDs get auto-generated ones."""

    def test_auto_ids(self, tmp_path: Path) -> None:
        wf_data = {
            "steps": [
                {"type": "delay", "delay_seconds": 0.001, "next_step": None},
            ]
        }
        wf = tmp_path / "auto_id.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.success is True
        assert result.steps_completed == 1


class TestWorkflowTiming:
    """elapsed_seconds is populated and > 0."""

    def test_elapsed_seconds(self, tmp_path: Path) -> None:
        wf_data = {
            "steps": [
                {"id": "s1", "type": "delay", "delay_seconds": 0.01, "next_step": None},
            ]
        }
        wf = tmp_path / "timing.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.elapsed_seconds > 0


class TestListWorkflowsEdgeCases:
    """list_workflows with array-toplevel JSON and mixed files."""

    def test_array_toplevel_json(self, tmp_path: Path) -> None:
        arr = tmp_path / "arr.json"
        arr.write_text("[1, 2, 3]", encoding="utf-8")
        result = WorkflowEngine.list_workflows(str(tmp_path))
        assert result == []

    def test_mixed_json_and_nonjson(self, tmp_path: Path) -> None:
        good = tmp_path / "good.json"
        good.write_text(json.dumps({"name": "WF", "steps": [{"id": "s1"}]}), encoding="utf-8")
        txt = tmp_path / "notes.txt"
        txt.write_text("not a workflow", encoding="utf-8")
        result = WorkflowEngine.list_workflows(str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "WF"


class TestSequentialTermination:
    """Workflow stops after a step with no next_step, even if more steps exist."""

    def test_no_next_step_terminates(self, tmp_path: Path) -> None:
        wf_data = {
            "steps": [
                {"id": "s1", "type": "delay", "delay_seconds": 0.001, "next_step": "s2"},
                {"id": "s2", "type": "delay", "delay_seconds": 0.001},
                {"id": "s3", "type": "delay", "delay_seconds": 0.001},
            ]
        }
        wf = tmp_path / "seq.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.steps_completed == 2  # s1 + s2, s3 never reached


class TestVariableMerging:
    """File-level and parameter-level variables both present in merged result."""

    def test_file_and_param_variables_merge(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}
        wf_data = {
            "variables": {"file_var": "from_file", "shared": "file_wins_if_no_override"},
            "steps": [
                {
                    "id": "s1",
                    "type": "action",
                    "action": {
                        "type": "click",
                        "x": "{{file_var}}",
                        "y": "{{param_var}}",
                        "z": "{{shared}}",
                    },
                    "next_step": None,
                },
            ],
        }
        wf = tmp_path / "merge.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine(action_executor=executor)
        result = engine.run_workflow(
            str(wf), variables={"param_var": "from_param", "shared": "param_overrides"}
        )
        assert result.success is True
        call_args = executor.execute_sync.call_args[0][0]
        assert call_args["x"] == "from_file"
        assert call_args["y"] == "from_param"
        assert call_args["z"] == "param_overrides"


class TestSaveWorkflowOSError:
    """save_workflow re-raises OSError."""

    def test_save_to_readonly_dir(self, tmp_path: Path) -> None:
        import pytest

        target = tmp_path / "out.json"
        with patch.object(Path, "open", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                WorkflowEngine.save_workflow(str(target), {"steps": []})
