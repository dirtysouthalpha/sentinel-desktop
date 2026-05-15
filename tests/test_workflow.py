"""Tests for core/workflow.py — multi-step workflow execution."""

import json
import os
from unittest.mock import MagicMock

from core.workflow import (
    ErrorPolicy,
    StepType,
    WorkflowEngine,
    WorkflowResult,
)


class TestStepType:
    def test_values(self):
        assert StepType.SCRIPT == "script"
        assert StepType.ACTION == "action"
        assert StepType.CONDITION == "condition"
        assert StepType.LOOP == "loop"
        assert StepType.SUB_WORKFLOW == "sub_workflow"
        assert StepType.DELAY == "delay"
        assert StepType.NOTIFY == "notify"


class TestErrorPolicy:
    def test_values(self):
        assert ErrorPolicy.STOP == "stop"
        assert ErrorPolicy.SKIP == "skip"
        assert ErrorPolicy.RETRY == "retry"


class TestWorkflowResult:
    def test_defaults(self):
        r = WorkflowResult()
        assert r.success is False
        assert r.steps_completed == 0
        assert r.steps_total == 0
        assert r.error == ""
        assert r.outputs == {}
        assert r.elapsed_seconds == 0.0
        assert r.step_results == []


class TestResolveVariables:
    def test_simple_variable(self):
        result = WorkflowEngine.resolve_variables("Hello {{name}}", {"name": "World"}, {})
        assert result == "Hello World"

    def test_missing_variable_returns_empty(self):
        result = WorkflowEngine.resolve_variables("Hello {{name}}", {}, {})
        assert result == "Hello "

    def test_step_output_reference(self):
        result = WorkflowEngine.resolve_variables(
            "{{step.s1.success}}", {}, {"s1": {"success": True}}
        )
        assert result == "True"

    def test_nested_step_output(self):
        step_outputs = {"s1": {"output": {"status": "ok"}}}
        result = WorkflowEngine.resolve_variables("{{step.s1.output.status}}", {}, step_outputs)
        assert result == "ok"

    def test_no_variables_returns_unchanged(self):
        result = WorkflowEngine.resolve_variables("plain text", {}, {})
        assert result == "plain text"

    def test_non_string_returns_unchanged(self):
        result = WorkflowEngine.resolve_variables(42, {}, {})
        assert result == 42

    def test_multiple_variables(self):
        result = WorkflowEngine.resolve_variables("{{a}} and {{b}}", {"a": "foo", "b": "bar"}, {})
        assert result == "foo and bar"


class TestEvaluateCondition:
    def test_true_values(self):
        for val in ("true", "yes", "1", "success"):
            assert WorkflowEngine.evaluate_condition(val) is True

    def test_false_values(self):
        for val in ("false", "no", "0", "failed"):
            assert WorkflowEngine.evaluate_condition(val) is False

    def test_equals(self):
        assert WorkflowEngine.evaluate_condition("hello == hello") is True
        assert WorkflowEngine.evaluate_condition("hello == world") is False

    def test_not_equals(self):
        assert WorkflowEngine.evaluate_condition("a != b") is True
        assert WorkflowEngine.evaluate_condition("a != a") is False

    def test_contains(self):
        assert WorkflowEngine.evaluate_condition("hello contains ell") is True
        assert WorkflowEngine.evaluate_condition("hello contains xyz") is False

    def test_greater_than(self):
        assert WorkflowEngine.evaluate_condition("10 > 5") is True
        assert WorkflowEngine.evaluate_condition("3 > 5") is False

    def test_less_than(self):
        assert WorkflowEngine.evaluate_condition("3 < 10") is True
        assert WorkflowEngine.evaluate_condition("10 < 3") is False

    def test_greater_equal(self):
        assert WorkflowEngine.evaluate_condition("5 >= 5") is True
        assert WorkflowEngine.evaluate_condition("4 >= 5") is False

    def test_less_equal(self):
        assert WorkflowEngine.evaluate_condition("5 <= 5") is True
        assert WorkflowEngine.evaluate_condition("6 <= 5") is False

    def test_non_numeric_comparison_returns_false(self):
        assert WorkflowEngine.evaluate_condition("abc > 5") is False

    def test_empty_returns_false(self):
        assert WorkflowEngine.evaluate_condition("") is False

    def test_case_insensitive(self):
        assert WorkflowEngine.evaluate_condition("True") is True
        assert WorkflowEngine.evaluate_condition("FALSE") is False


class TestParseList:
    def test_list_passthrough(self):
        assert WorkflowEngine._parse_list([1, 2, 3]) == [1, 2, 3]

    def test_json_string_list(self):
        result = WorkflowEngine._parse_list('["a", "b", "c"]')
        assert result == ["a", "b", "c"]

    def test_comma_separated_string(self):
        result = WorkflowEngine._parse_list("a, b, c")
        assert result == ["a", "b", "c"]

    def test_single_value(self):
        assert WorkflowEngine._parse_list("hello") == ["hello"]

    def test_none_returns_empty(self):
        assert WorkflowEngine._parse_list(None) == []

    def test_empty_string_returns_empty(self):
        assert WorkflowEngine._parse_list("") == []


class TestWorkflowEngine:
    def test_run_missing_file(self):
        engine = WorkflowEngine()
        result = engine.run_workflow("/nonexistent/path.json")
        assert result.success is False
        assert "not found" in result.error

    def test_run_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{{", encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(bad))
        assert result.success is False

    def test_run_empty_steps(self, tmp_path):
        wf = tmp_path / "empty.json"
        wf.write_text(json.dumps({"steps": []}), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.success is False
        assert "No steps" in result.error

    def test_run_delay_step(self, tmp_path):
        wf_data = {
            "steps": [
                {"id": "s1", "type": "delay", "delay_seconds": 0.01, "next_step": None},
            ]
        }
        wf = tmp_path / "delay.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.success is True
        assert result.steps_completed == 1

    def test_run_action_step_no_executor(self, tmp_path):
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "action",
                    "action": {"type": "click", "x": 100, "y": 200},
                    "next_step": None,
                },
            ]
        }
        wf = tmp_path / "action.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        # Engine completes the workflow but records the step-level error
        assert result.steps_completed == 1
        assert any("executor" in sr.get("error", "").lower() for sr in result.step_results)

    def test_run_script_step_no_engine(self, tmp_path):
        wf_data = {
            "steps": [
                {"id": "s1", "type": "script", "path": "test.json", "next_step": None},
            ]
        }
        wf = tmp_path / "script.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        # Engine completes but records step-level error
        assert result.steps_completed == 1
        assert any("engine" in sr.get("error", "").lower() for sr in result.step_results)

    def test_run_condition_step(self, tmp_path):
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "condition",
                    "check": "true",
                    "true_next": "s2",
                    "false_next": "s3",
                },
                {"id": "s2", "type": "delay", "delay_seconds": 0.01},
                {"id": "s3", "type": "delay", "delay_seconds": 0.01},
            ]
        }
        wf = tmp_path / "cond.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.steps_completed >= 1

    def test_set_callback(self):
        engine = WorkflowEngine()
        events = []
        engine.set_callback("on_step_start", lambda sid: events.append(("start", sid)))
        assert "on_step_start" in engine._callbacks

    def test_save_workflow(self, tmp_path):
        data = {"name": "test", "steps": [{"id": "s1", "type": "delay", "delay_seconds": 0.01}]}
        path = str(tmp_path / "saved.json")
        WorkflowEngine.save_workflow(path, data)
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["name"] == "test"

    def test_list_workflows_empty_dir(self, tmp_path):
        result = WorkflowEngine.list_workflows(str(tmp_path))
        assert result == []

    def test_list_workflows(self, tmp_path):
        wf_data = {
            "name": "Test WF",
            "steps": [{"id": "s1", "type": "delay"}],
            "variables": {"x": 1},
        }
        wf = tmp_path / "test.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        result = WorkflowEngine.list_workflows(str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "Test WF"
        assert result[0]["steps"] == 1

    def test_list_workflows_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        result = WorkflowEngine.list_workflows(str(tmp_path))
        assert result == []

    def test_list_workflows_nonexistent_dir(self):
        result = WorkflowEngine.list_workflows("/nonexistent/path")
        assert result == []

    def test_run_loop_step(self, tmp_path):
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "loop",
                    "over": "a,b,c",
                    "body_step": "s2",
                    "next_step": None,
                },
                {"id": "s2", "type": "delay", "delay_seconds": 0.01},
            ]
        }
        wf = tmp_path / "loop.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.success is True
        # Loop step + 3 body iterations counted
        assert result.steps_completed >= 1
        loop_output = result.outputs.get("s1", {})
        assert loop_output.get("success") is True
        assert loop_output.get("items_processed") == 3

    def test_run_notify_step(self, tmp_path):
        wf_data = {
            "steps": [
                {"id": "s1", "type": "notify", "message": "Hello {{name}}", "next_step": None},
            ]
        }
        wf = tmp_path / "notify.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf), variables={"name": "World"})
        assert result.success is True
        assert result.steps_completed == 1
        assert result.step_results[0]["success"] is True
        assert result.step_results[0]["type"] == "notify"

    def test_run_sub_workflow(self, tmp_path):
        # Create the sub-workflow
        sub_data = {"steps": [{"id": "s1", "type": "delay", "delay_seconds": 0.01}]}
        sub_path = tmp_path / "sub.json"
        sub_path.write_text(json.dumps(sub_data), encoding="utf-8")

        wf_data = {
            "steps": [
                {"id": "s1", "type": "sub_workflow", "path": str(sub_path), "next_step": None},
            ]
        }
        wf = tmp_path / "main.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.success is True
        assert result.steps_completed == 1
        assert result.step_results[0]["success"] is True

    def test_error_policy_skip(self, tmp_path):
        executor = MagicMock()
        executor.execute_sync.side_effect = RuntimeError("boom")
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "action",
                    "action": {"type": "click"},
                    "error_policy": "skip",
                    "next_step": "s2",
                },
                {"id": "s2", "type": "delay", "delay_seconds": 0.01},
            ]
        }
        wf = tmp_path / "skip.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine(action_executor=executor)
        result = engine.run_workflow(str(wf))
        assert result.success is True
        # Failed step not counted in steps_completed, but next step runs
        assert result.steps_completed == 1
        assert len(result.step_results) == 2

    def test_error_policy_retry(self, tmp_path):
        executor = MagicMock()
        executor.execute_sync.side_effect = RuntimeError("boom")
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "action",
                    "action": {"type": "click"},
                    "error_policy": "retry",
                    "max_retries": 2,
                    "next_step": None,
                },
            ]
        }
        wf = tmp_path / "retry.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine(action_executor=executor)
        result = engine.run_workflow(str(wf))
        assert result.success is False
        assert "retries" in result.error

    def test_error_policy_retry_succeeds(self, tmp_path):
        executor = MagicMock()
        call_count = {"n": 0}

        def fake_exec(action):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("not yet")
            return {"success": True}

        executor.execute_sync.side_effect = fake_exec
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "action",
                    "action": {"type": "click"},
                    "error_policy": "retry",
                    "max_retries": 3,
                    "next_step": None,
                },
            ]
        }
        wf = tmp_path / "retry_ok.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine(action_executor=executor)
        result = engine.run_workflow(str(wf))
        assert result.success is True

    def test_fire_callbacks_during_workflow(self, tmp_path):
        events = []
        wf_data = {
            "steps": [
                {"id": "s1", "type": "delay", "delay_seconds": 0.01, "next_step": None},
            ]
        }
        wf = tmp_path / "cb.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        engine.set_callback("on_step_start", lambda sid: events.append(("start", sid)))
        engine.set_callback("on_step_complete", lambda sid, sr: events.append(("complete", sid)))
        engine.set_callback("on_workflow_complete", lambda r: events.append(("done",)))
        engine.run_workflow(str(wf))
        assert ("start", "s1") in events
        assert ("complete", "s1") in events
        assert ("done",) in events

    def test_condition_false_branch(self, tmp_path):
        wf_data = {
            "steps": [
                {
                    "id": "s1",
                    "type": "condition",
                    "check": "false",
                    "true_next": "s2",
                    "false_next": "s3",
                },
                {"id": "s2", "type": "delay", "delay_seconds": 0.01},
                {"id": "s3", "type": "delay", "delay_seconds": 0.01},
            ]
        }
        wf = tmp_path / "cond_false.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine()
        result = engine.run_workflow(str(wf))
        assert result.success is True
        # Should have condition + s3 (false branch), not s2
        assert result.steps_completed == 2

    def test_action_with_executor_and_variables(self, tmp_path):
        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True, "x": 1, "y": 2}
        wf_data = {
            "variables": {"target": "100"},
            "steps": [
                {
                    "id": "s1",
                    "type": "action",
                    "action": {"type": "click", "x": "{{target}}"},
                    "next_step": None,
                },
            ],
        }
        wf = tmp_path / "action_var.json"
        wf.write_text(json.dumps(wf_data), encoding="utf-8")
        engine = WorkflowEngine(action_executor=executor)
        result = engine.run_workflow(str(wf))
        assert result.success is True
        # Verify variable was resolved in the action
        call_args = executor.execute_sync.call_args[0][0]
        assert call_args["x"] == "100"
