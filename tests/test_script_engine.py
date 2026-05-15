"""Tests for core/script_engine.py — parameter substitution, validation, replay."""

import json

import pytest

from core.script_engine import (
    ScriptEngine,
    ScriptResult,
    _extract_required_params,
    _substitute_params,
    _substitute_step,
    _validate_script,
)


class TestSubstituteParams:
    def test_simple_replacement(self):
        assert _substitute_params("Hello {{name}}", {"name": "World"}) == "Hello World"

    def test_multiple_params(self):
        assert _substitute_params("{{a}}-{{b}}", {"a": "x", "b": "y"}) == "x-y"

    def test_missing_param_left_intact(self):
        assert _substitute_params("{{missing}}", {}) == "{{missing}}"

    def test_non_string_returned_unchanged(self):
        assert _substitute_params(42, {"x": "y"}) == 42
        assert _substitute_params(None, {}) is None
        assert _substitute_params([1, 2], {}) == [1, 2]

    def test_whitespace_in_placeholder(self):
        assert _substitute_params("{{  name  }}", {"name": "ok"}) == "ok"

    def test_numeric_param_cast_to_str(self):
        assert _substitute_params("val={{n}}", {"n": 42}) == "val=42"


class TestSubstituteStep:
    def test_substitutes_all_values(self):
        step = {"x": "{{a}}", "y": "{{b}}", "z": 99}
        result = _substitute_step(step, {"a": "10", "b": "20"})
        assert result == {"x": "10", "y": "20", "z": 99}

    def test_does_not_mutate_original(self):
        step = {"x": "{{a}}"}
        _substitute_step(step, {"a": "val"})
        assert step["x"] == "{{a}}"


class TestExtractRequiredParams:
    def test_extracts_from_steps(self):
        script = {
            "steps": [
                {"action": "click", "params": {"x": "{{pos_x}}", "y": "{{pos_y}}"}},
                {"action": "type_text", "params": {"text": "{{msg}}"}},
            ]
        }
        assert _extract_required_params(script) == {"pos_x", "pos_y", "msg"}

    def test_empty_script(self):
        assert _extract_required_params({}) == set()
        assert _extract_required_params({"steps": []}) == set()

    def test_no_placeholders(self):
        script = {"steps": [{"action": "click", "params": {"x": 100, "y": 200}}]}
        assert _extract_required_params(script) == set()


class TestValidateScript:
    def test_valid_script(self):
        script = {"steps": [{"action": "click", "params": {"x": 100}}]}
        assert _validate_script(script, {}, None) == []

    def test_missing_steps_key(self):
        assert _validate_script({}, {}, None) != []

    def test_empty_steps(self):
        assert _validate_script({"steps": []}, {}, None) != []

    def test_missing_action_field(self):
        errors = _validate_script({"steps": [{"params": {}}]}, {}, None)
        assert any("missing 'action'" in e for e in errors)

    def test_missing_params_field(self):
        errors = _validate_script({"steps": [{"action": "click"}]}, {}, None)
        assert any("missing 'params'" in e for e in errors)

    def test_missing_required_params(self):
        script = {"steps": [{"action": "click", "params": {"x": "{{pos}}"}}]}
        errors = _validate_script(script, {}, None)
        assert any("Missing required" in e for e in errors)

    def test_unknown_action_with_executor(self):
        executor = type("E", (), {"_dispatch_table": {"click": True}})()
        script = {"steps": [{"action": "fly", "params": {}}]}
        errors = _validate_script(script, {}, executor)
        assert any("unknown action" in e for e in errors)

    def test_known_action_passes(self):
        executor = type("E", (), {"_dispatch_table": {"click": True}})()
        script = {"steps": [{"action": "click", "params": {}}]}
        assert _validate_script(script, {}, executor) == []


class TestScriptResult:
    def test_defaults(self):
        r = ScriptResult(success=True, steps_completed=1, steps_total=1)
        assert r.results == []
        assert r.error is None
        assert r.duration_ms == 0


class TestScriptEngine:
    def _make_executor(self, results=None):
        """Create a mock executor with configurable results."""
        results = results or [{"success": True, "output": "ok"}]

        class MockExecutor:
            def __init__(self, res):
                self._results = list(res)
                self._idx = 0
                self._dispatch_table = {"click": True, "type_text": True}

            def execute_sync(self, action_dict):
                if self._idx < len(self._results):
                    r = self._results[self._idx]
                    self._idx += 1
                    return r
                return {"success": False, "output": "no more results"}

        return MockExecutor(results)

    def test_run_from_dict_success(self):
        executor = self._make_executor()
        engine = ScriptEngine(executor)
        script = {"steps": [{"action": "click", "params": {"x": 100, "y": 200}}]}
        result = engine.run_script_from_dict(script)
        assert result.success is True
        assert result.steps_completed == 1
        assert result.steps_total == 1

    def test_run_from_dict_with_params(self):
        executor = self._make_executor()
        engine = ScriptEngine(executor)
        script = {"steps": [{"action": "click", "params": {"x": "{{cx}}"}}]}
        result = engine.run_script_from_dict(script, {"cx": "500"})
        assert result.success is True

    def test_run_from_dict_validation_failure(self):
        engine = ScriptEngine(self._make_executor())
        result = engine.run_script_from_dict({"steps": []})
        assert result.success is False
        assert "Validation failed" in result.error

    def test_run_script_missing_file(self):
        engine = ScriptEngine(self._make_executor())
        result = engine.run_script("/nonexistent/path.json")
        assert result.success is False
        assert "not found" in result.error

    def test_run_script_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{{", encoding="utf-8")
        engine = ScriptEngine(self._make_executor())
        result = engine.run_script(str(bad))
        assert result.success is False

    def test_run_script_valid_json(self, tmp_path):
        wf = tmp_path / "script.json"
        wf.write_text(
            json.dumps({"steps": [{"action": "click", "params": {"x": 1, "y": 2}}]}),
            encoding="utf-8",
        )
        engine = ScriptEngine(self._make_executor())
        result = engine.run_script(str(wf))
        assert result.success is True

    def test_error_policy_stop(self):
        executor = self._make_executor(
            [{"success": False, "output": "err"}, {"success": True, "output": "ok"}]
        )
        engine = ScriptEngine(executor)
        engine.set_on_error_policy("stop")
        script = {
            "steps": [
                {"action": "click", "params": {}},
                {"action": "click", "params": {}},
            ]
        }
        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert result.steps_completed == 1

    def test_error_policy_skip(self):
        executor = self._make_executor(
            [{"success": False, "output": "err"}, {"success": True, "output": "ok"}]
        )
        engine = ScriptEngine(executor)
        engine.set_on_error_policy("skip")
        script = {
            "steps": [
                {"action": "click", "params": {}},
                {"action": "click", "params": {}},
            ]
        }
        result = engine.run_script_from_dict(script)
        assert result.steps_completed == 2

    def test_invalid_error_policy_raises(self):
        engine = ScriptEngine(self._make_executor())
        with pytest.raises(ValueError):
            engine.set_on_error_policy("explode")

    def test_dry_run_returns_previews(self):
        engine = ScriptEngine(self._make_executor())
        script = {
            "steps": [
                {"action": "click", "params": {"x": "{{cx}}"}, "wait_after_ms": 100},
                {"action": "type_text", "params": {"text": "hi"}},
            ]
        }
        previews = engine.dry_run(script, {"cx": "500"})
        assert len(previews) == 2
        assert previews[0]["action"] == "click"
        assert previews[0]["params"]["x"] == "500"
        assert previews[0]["wait_after_ms"] == 100
        assert previews[1]["action"] == "type_text"

    def test_dry_run_invalid_raises(self):
        engine = ScriptEngine(self._make_executor())
        with pytest.raises(ValueError):
            engine.dry_run({"steps": []})

    def test_progress_callback(self):
        executor = self._make_executor([{"success": True, "output": "ok"}] * 2)
        engine = ScriptEngine(executor)
        events = []
        engine.set_progress_callback(lambda sn, total, action, result: events.append((sn, action)))
        script = {
            "steps": [
                {"action": "click", "params": {}},
                {"action": "type_text", "params": {"text": "x"}},
            ]
        }
        engine.run_script_from_dict(script)
        assert len(events) == 2
        assert events[0] == (1, "click")
        assert events[1] == (2, "type_text")
