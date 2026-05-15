"""Gap tests for script_engine.py — retry_once executor exception on retry."""

from unittest.mock import MagicMock

from core.script_engine import ScriptEngine


def _make_executor() -> MagicMock:
    ex = MagicMock()
    ex._dispatch_table = {"click": True, "type": True}
    return ex


class TestRetryOnceExecutorExceptionOnRetry:
    """retry_once: executor succeeds first call but raises on retry."""

    def test_retry_raises_returns_failure(self) -> None:
        ex = _make_executor()
        # First call returns failure (triggers retry), second raises
        ex.execute_sync.side_effect = [
            {"success": False, "error": "fail"},
            RuntimeError("retry boom"),
        ]
        engine = ScriptEngine(ex)
        engine.set_on_error_policy("retry_once")
        script = {"steps": [{"action": "click", "params": {"x": 1}}]}
        result = engine.run_script_from_dict(script)
        assert result.success is False
        assert "retry boom" in result.error
