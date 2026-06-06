"""Full coverage tests for core/script_engine.py — missing lines and edge cases."""

import time
from unittest.mock import MagicMock

import pytest

from core.script_engine import (
    ScriptEngine,
    _extract_required_params,
    _substitute_step,
)


class TestProgressCallbackExceptionHandling:
    """Tests for lines 270-271: Exception handling in progress callback."""

    def test_progress_callback_exception_is_caught(self):
        """Test that exceptions in progress callback are caught and logged."""
        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}
        executor._dispatch_table = {"test": lambda x: x, "test2": lambda x: x}
        engine = ScriptEngine(executor)

        # Callback that raises an exception
        def failing_callback(step_num, total, action, result):
            raise ValueError("Callback error!")

        engine.set_progress_callback(failing_callback)

        script = {
            "steps": [
                {"action": "test", "params": {"x": "1"}},
                {"action": "test2", "params": {"y": "2"}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is True
        assert result.steps_completed == 2


class TestWaitAfterMs:
    """Tests for line 292: time.sleep() for wait_after_ms."""

    def test_wait_after_ms_executes_sleep(self):
        """Test that wait_after_ms triggers time.sleep()."""
        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}
        executor._dispatch_table = {"test": lambda x: x, "test2": lambda x: x}
        engine = ScriptEngine(executor)

        # Mock time.sleep to verify it's called
        original_sleep = time.sleep
        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        time.sleep = mock_sleep

        try:
            script = {
                "steps": [
                    {"action": "test", "params": {"x": "1"}, "wait_after_ms": 100},
                    {"action": "test2", "params": {"y": "2"}, "wait_after_ms": 200},
                ]
            }

            result = engine.run_script_from_dict(script)
            assert result.success is True
            assert len(sleep_calls) == 2
            assert sleep_calls[0] == 0.1  # 100ms
            assert sleep_calls[1] == 0.2  # 200ms
        finally:
            time.sleep = original_sleep


class TestExecuteStepExceptionHandling:
    """Tests for lines 337-339: Exception handling in execute_step."""

    def test_execute_step_exception_handling(self):
        """Test that executor exceptions are caught and returned as error."""
        executor = MagicMock()
        executor.execute_sync.side_effect = RuntimeError("Executor crashed!")
        executor._dispatch_table = {"failing_action": lambda x: x}
        engine = ScriptEngine(executor)

        script = {
            "steps": [
                {"action": "failing_action", "params": {"x": "1"}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert "Executor crashed!" in result.error
        assert result.steps_completed == 1


class TestExecuteStepNonDictResult:
    """Tests for lines 342-343: Non-dict result handling."""

    def test_execute_step_non_dict_result(self):
        """Test that non-dict results are handled correctly."""
        executor = MagicMock()
        executor.execute_sync.return_value = "not a dict"  # Return a string instead of dict
        executor._dispatch_table = {"bad_action": lambda x: x}
        engine = ScriptEngine(executor)

        script = {
            "steps": [
                {"action": "bad_action", "params": {"x": "1"}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert "expected dict" in result.error
        assert "str" in result.error


class TestRetryLogic:
    """Tests for lines 353-358: Retry logic with exception handling."""

    def test_retry_once_on_failure(self):
        """Test that retry_once policy retries failed steps."""
        executor = MagicMock()
        # First call fails, second call succeeds
        executor.execute_sync.side_effect = [
            {"success": False, "error": "First attempt failed"},
            {"success": True, "output": "Success on retry"},
        ]
        executor._dispatch_table = {"flaky_action": lambda x: x}
        engine = ScriptEngine(executor)
        engine.set_on_error_policy("retry_once")

        script = {
            "steps": [
                {"action": "flaky_action", "params": {"x": "1"}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is True
        assert executor.execute_sync.call_count == 2

    def test_retry_once_exception_on_retry(self):
        """Test that exceptions during retry are handled."""
        executor = MagicMock()
        # First call succeeds, retry raises exception
        executor.execute_sync.side_effect = [
            {"success": False, "error": "First attempt failed"},
            RuntimeError("Retry crashed!"),
        ]
        executor._dispatch_table = {"flaky_action": lambda x: x}
        engine = ScriptEngine(executor)
        engine.set_on_error_policy("retry_once")

        script = {
            "steps": [
                {"action": "flaky_action", "params": {"x": "1"}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert "Retry crashed!" in result.error
        assert executor.execute_sync.call_count == 2


class TestOnErrorPolicies:
    """Tests for different error handling policies."""

    def test_stop_policy_on_first_failure(self):
        """Test that 'stop' policy stops execution on first failure."""
        executor = MagicMock()
        executor.execute_sync.side_effect = [
            {"success": True, "output": "Step 1 success"},
            {"success": False, "error": "Step 2 failed"},
            {"success": True, "output": "Step 3 success"},  # Should not execute
        ]
        executor._dispatch_table = {
            "step1": lambda x: x,
            "step2": lambda x: x,
            "step3": lambda x: x,
        }
        engine = ScriptEngine(executor)
        engine.set_on_error_policy("stop")

        script = {
            "steps": [
                {"action": "step1", "params": {}},
                {"action": "step2", "params": {}},
                {"action": "step3", "params": {}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert result.steps_completed == 2
        assert executor.execute_sync.call_count == 2

    def test_skip_policy_continues_on_failure(self):
        """Test that 'skip' policy continues execution on failure."""
        executor = MagicMock()
        executor.execute_sync.side_effect = [
            {"success": True, "output": "Step 1 success"},
            {"success": False, "error": "Step 2 failed"},
            {"success": True, "output": "Step 3 success"},
        ]
        executor._dispatch_table = {
            "step1": lambda x: x,
            "step2": lambda x: x,
            "step3": lambda x: x,
        }
        engine = ScriptEngine(executor)
        engine.set_on_error_policy("skip")

        script = {
            "steps": [
                {"action": "step1", "params": {}},
                {"action": "step2", "params": {}},
                {"action": "step3", "params": {}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is False  # Overall success is False due to step 2 failure
        assert result.steps_completed == 3
        assert executor.execute_sync.call_count == 3


class TestValidationWithExecutor:
    """Tests for validation with executor context."""

    def test_validation_with_unknown_action(self):
        """Test that validation catches unknown actions when executor has dispatch table."""
        executor = MagicMock()
        executor._dispatch_table = {"valid_action": lambda x: x}
        engine = ScriptEngine(executor)

        script = {
            "steps": [
                {"action": "unknown_action", "params": {}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert "unknown action" in result.error


class TestComplexScenarios:
    """Complex integration scenarios."""

    def test_mixed_success_and_failure_with_retry(self):
        """Test a complex scenario with mixed results and retries."""
        executor = MagicMock()
        executor.execute_sync.side_effect = [
            {"success": True, "output": "Step 1"},
            {"success": False, "error": "Step 2 first try"},
            {"success": True, "output": "Step 2 retry success"},
            {"success": True, "output": "Step 3"},
        ]
        executor._dispatch_table = {
            "step1": lambda x: x,
            "step2": lambda x: x,
            "step3": lambda x: x,
        }
        engine = ScriptEngine(executor)
        engine.set_on_error_policy("retry_once")

        script = {
            "steps": [
                {"action": "step1", "params": {}},
                {"action": "step2", "params": {}},
                {"action": "step3", "params": {}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is True
        assert result.steps_completed == 3
        assert len(result.results) == 3

    def test_progress_callback_called_correctly(self):
        """Test that progress callback is called with correct parameters."""
        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True, "output": "test"}
        executor._dispatch_table = {
            "action1": lambda x: x,
            "action2": lambda x: x,
            "action3": lambda x: x,
        }
        engine = ScriptEngine(executor)

        callback_calls = []

        def tracking_callback(step_num, total, action, result):
            callback_calls.append((step_num, total, action, result))

        engine.set_progress_callback(tracking_callback)

        script = {
            "steps": [
                {"action": "action1", "params": {}},
                {"action": "action2", "params": {}},
                {"action": "action3", "params": {}},
            ]
        }

        result = engine.run_script_from_dict(script)
        assert result.success is True
        assert len(callback_calls) == 3

        # Check first callback
        assert callback_calls[0][0] == 1  # step_num
        assert callback_calls[0][1] == 3  # total
        assert callback_calls[0][2] == "action1"  # action
        assert callback_calls[0][3]["success"] is True  # result


class TestEdgeCases:
    """Edge case scenarios."""

    def test_empty_params_dict(self):
        """Test that empty params dict is handled correctly."""
        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}
        executor._dispatch_table = {"test": lambda x: x}
        engine = ScriptEngine(executor)

        script = {
            "steps": [
                {"action": "test", "params": {}},
            ]
        }

        result = engine.run_script_from_dict(script, {})
        assert result.success is True

    def test_none_params(self):
        """Test that None params are handled correctly."""
        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}
        executor._dispatch_table = {"test": lambda x: x}
        engine = ScriptEngine(executor)

        script = {
            "steps": [
                {"action": "test", "params": {}},
            ]
        }

        result = engine.run_script_from_dict(script, None)
        assert result.success is True

    def test_zero_wait_after_ms(self):
        """Test that zero wait_after_ms doesn't trigger sleep."""
        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}
        executor._dispatch_table = {"test": lambda x: x}
        engine = ScriptEngine(executor)

        original_sleep = time.sleep
        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        time.sleep = mock_sleep

        try:
            script = {
                "steps": [
                    {"action": "test", "params": {"x": "1"}, "wait_after_ms": 0},
                ]
            }

            result = engine.run_script_from_dict(script)
            assert result.success is True
            assert len(sleep_calls) == 0  # No sleep should occur
        finally:
            time.sleep = original_sleep

    def test_invalid_on_error_policy(self):
        """Test that invalid on_error policy raises ValueError."""
        executor = MagicMock()
        engine = ScriptEngine(executor)

        with pytest.raises(ValueError, match="Invalid on_error policy"):
            engine.set_on_error_policy("invalid_policy")


class TestSubstitutionEdgeCases:
    """Additional edge cases for parameter substitution."""

    def test_substitute_with_nested_structures(self):
        """Test substitution with nested dict/list structures."""
        step = {
            "x": "{{value}}",
            "y": [1, 2, 3],
            "z": {"nested": "{{another}}"},
        }
        result = _substitute_step(step, {"value": "replaced", "another": "done"})
        assert result["x"] == "replaced"
        assert result["y"] == [1, 2, 3]
        # Note: _substitute_step doesn't recursively process nested structures
        assert result["z"]["nested"] == "{{another}}"  # Not substituted in nested structures

    def test_extract_required_params_from_complex_steps(self):
        """Test parameter extraction from complex step structures."""
        script = {
            "steps": [
                {
                    "action": "test",
                    "params": {
                        "simple": "{{param1}}",
                        "nested": {"key": "{{param2}}"},
                        "list": ["{{param3}}", "fixed"],
                    },
                }
            ]
        }
        required = _extract_required_params(script)
        # Note: _extract_required_params only processes string values, not nested structures
        assert required == {"param1"}  # Only param1 is extracted from the simple string value


class TestDryRun:
    """Tests for dry_run method."""

    def test_dry_run_returns_step_previews(self):
        """Test that dry_run returns correct step previews."""
        executor = MagicMock()
        executor._dispatch_table = {"action1": lambda x: x, "action2": lambda x: x}
        engine = ScriptEngine(executor)

        script = {
            "steps": [
                {"action": "action1", "params": {"x": "{{param}}"}, "wait_after_ms": 100},
                {"action": "action2", "params": {"y": "fixed"}, "wait_after_ms": 200},
            ]
        }

        previews = engine.dry_run(script, {"param": "value"})
        assert len(previews) == 2
        assert previews[0]["step_number"] == 1
        assert previews[0]["action"] == "action1"
        assert previews[0]["params"]["x"] == "value"  # Substituted
        assert previews[0]["wait_after_ms"] == 100

        assert previews[1]["step_number"] == 2
        assert previews[1]["action"] == "action2"
        assert previews[1]["params"]["y"] == "fixed"  # No substitution needed
        assert previews[1]["wait_after_ms"] == 200

    def test_dry_run_raises_on_validation_error(self):
        """Test that dry_run raises ValueError on validation failure."""
        executor = MagicMock()
        executor._dispatch_table = {"valid_action": lambda x: x}  # This action is not in the script
        engine = ScriptEngine(executor)

        script = {
            "steps": [
                {"action": "unknown_action", "params": {}},
            ]
        }

        with pytest.raises(ValueError, match="Script validation failed"):
            engine.dry_run(script, {})
