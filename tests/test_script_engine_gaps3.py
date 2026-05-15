"""Tests for script_engine.py — _StepPreview.to_dict, result without success key,
substitute_params with nested-dict values, and dry_run wait_after_ms preservation."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.script_engine import (
    ScriptEngine,
    ScriptResult,
    _StepPreview,
    _substitute_params,
    _substitute_step,
)


class TestStepPreviewToDict:
    def test_round_trip(self):
        p = _StepPreview(step_number=3, action="click", params={"x": 5, "y": 10}, wait_after_ms=200)
        d = p.to_dict()
        assert d == {
            "step_number": 3,
            "action": "click",
            "params": {"x": 5, "y": 10},
            "wait_after_ms": 200,
        }

    def test_default_wait(self):
        p = _StepPreview(step_number=1, action="note", params={"text": "hi"})
        d = p.to_dict()
        assert d["wait_after_ms"] == 0


class TestSubstituteStepNested:
    def test_does_not_recurse_into_nested_dicts(self):
        step = {"url": "http://{{host}}/api", "meta": {"key": "{{token}}"}}
        result = _substitute_step(step, {"host": "example.com", "token": "abc"})
        assert result["url"] == "http://example.com/api"
        # _substitute_params only handles top-level string values, not nested dicts
        assert result["meta"] == {"key": "{{token}}"}


class TestSubstituteParamsEdge:
    def test_empty_string(self):
        assert _substitute_params("", {"x": "y"}) == ""

    def test_non_dict_params(self):
        assert _substitute_params(42, None) == 42


class TestExecuteStepNoSuccessKey:
    def test_result_without_success_key_treated_as_failure(self):
        ex = MagicMock()
        ex.execute_sync.return_value = {"output": "something"}
        ex._dispatch_table = {"click": True}
        engine = ScriptEngine(ex)
        script = {"steps": [{"action": "click", "params": {"x": 1}}]}
        result = engine.run_script_from_dict(script)
        assert result.success is False


class TestDryRunWaitAfterMs:
    def test_preserves_wait_after_ms(self):
        ex = MagicMock()
        ex._dispatch_table = {"click": True}
        engine = ScriptEngine(ex)
        script = {"steps": [{"action": "click", "params": {"x": 1}, "wait_after_ms": 500}]}
        previews = engine.dry_run(script)
        assert previews[0]["wait_after_ms"] == 500


class TestRunScriptFromDictDuration:
    def test_duration_ms_positive(self):
        ex = MagicMock()
        ex.execute_sync.return_value = {"success": True}
        ex._dispatch_table = {"click": True}
        engine = ScriptEngine(ex)
        script = {"steps": [{"action": "click", "params": {"x": 1}}]}
        result = engine.run_script_from_dict(script)
        assert result.duration_ms >= 0
        assert isinstance(result.results, list)
        assert len(result.results) == 1


class TestScriptResultDefaults:
    def test_error_defaults_none(self):
        r = ScriptResult(success=True, steps_completed=1, steps_total=1)
        assert r.error is None
        assert r.results == []
        assert r.duration_ms == 0
