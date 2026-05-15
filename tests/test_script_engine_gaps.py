"""Tests for script_engine.py — covering retry_once, progress callback errors, non-dict results."""

from unittest.mock import MagicMock, patch

from core.script_engine import ScriptEngine


def _make_executor(return_value: dict | None = None, side_effect=None) -> MagicMock:
    ex = MagicMock()
    if return_value is not None:
        ex.execute_sync.return_value = return_value
    if side_effect is not None:
        ex.execute_sync.side_effect = side_effect
    ex._dispatch_table = {"click": True, "type": True}
    return ex


class TestRetryOncePolicy:
    """retry_once retries once then continues."""

    def test_retry_once_retries_and_continues(self) -> None:
        ex = _make_executor()
        # First call fails, retry succeeds
        ex.execute_sync.side_effect = [
            {"success": False, "error": "fail"},
            {"success": True},
        ]
        engine = ScriptEngine(ex)
        engine.set_on_error_policy("retry_once")
        script = {
            "steps": [
                {"action": "click", "params": {"x": 10}},
                {"action": "type", "params": {"text": "hi"}},
            ]
        }
        result = engine.run_script_from_dict(script)
        assert result.success is False  # first step failed overall
        assert result.steps_completed == 2

    def test_retry_once_both_attempts_fail(self) -> None:
        ex = _make_executor()
        ex.execute_sync.side_effect = [
            {"success": False, "error": "fail1"},
            {"success": False, "error": "fail2"},
            {"success": True},
        ]
        engine = ScriptEngine(ex)
        engine.set_on_error_policy("retry_once")
        script = {
            "steps": [
                {"action": "click", "params": {"x": 10}},
                {"action": "type", "params": {"text": "hi"}},
            ]
        }
        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert result.steps_completed == 2


class TestProgressCallbackException:
    """Progress callback that raises is swallowed."""

    def test_callback_exception_ignored(self) -> None:
        ex = _make_executor(return_value={"success": True})
        engine = ScriptEngine(ex)
        engine.set_progress_callback(MagicMock(side_effect=RuntimeError("cb boom")))
        script = {"steps": [{"action": "click", "params": {"x": 1}}]}
        result = engine.run_script_from_dict(script)
        assert result.success is True
        assert result.steps_completed == 1


class TestNonDictResult:
    """Executor returning non-dict triggers error path."""

    def test_non_dict_result_treated_as_failure(self) -> None:
        ex = _make_executor(return_value="not a dict")
        engine = ScriptEngine(ex)
        script = {"steps": [{"action": "click", "params": {"x": 1}}]}
        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert "non-dict" in result.error.lower() or "expected dict" in result.error.lower()


class TestExecutorException:
    """Executor raising exception returns failure result."""

    def test_executor_raises_exception(self) -> None:
        ex = _make_executor()
        ex.execute_sync.side_effect = RuntimeError("executor broke")
        engine = ScriptEngine(ex)
        script = {"steps": [{"action": "click", "params": {"x": 1}}]}
        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert "executor broke" in result.error


class TestRetryOnceExecutorException:
    """retry_once when executor raises on both attempts."""

    def test_retry_once_with_executor_exception(self) -> None:
        ex = _make_executor()
        ex.execute_sync.side_effect = RuntimeError("boom")
        engine = ScriptEngine(ex)
        engine.set_on_error_policy("retry_once")
        script = {"steps": [{"action": "click", "params": {"x": 1}}]}
        result = engine.run_script_from_dict(script)
        assert result.success is False


class TestWaitAfterMs:
    """wait_after_ms causes sleep between steps."""

    @patch("core.script_engine.time.sleep")
    def test_wait_after_ms_honored(self, mock_sleep: MagicMock) -> None:
        ex = _make_executor(return_value={"success": True})
        engine = ScriptEngine(ex)
        script = {
            "steps": [
                {"action": "click", "params": {"x": 1}, "wait_after_ms": 500},
                {"action": "type", "params": {"text": "a"}},
            ]
        }
        result = engine.run_script_from_dict(script)
        assert result.success is True
        mock_sleep.assert_called_once_with(0.5)
