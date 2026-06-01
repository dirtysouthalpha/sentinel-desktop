"""Gap tests for engine.py remaining uncovered lines.

Lines 792-793: checkpoint save OSError/ValueError
Line 926: _call_llm_with_retry unreachable return (pragma: no cover applied)
Lines 1185-1186: _parse_action markdown JSONDecodeError
Lines 608, 638: KeyboardInterrupt/SystemExit re-raise guards in _run_inner
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.engine import AgentEngine


def _make_bare_engine(**overrides):
    eng = AgentEngine.__new__(AgentEngine)
    eng.config = {
        "provider": "openai",
        "api_key": "sk-test",
        "model": "gpt-4o",
        "max_steps": 5,
        "use_tools": False,
        "auto_screenshot": False,
    }
    eng.config.update(overrides)
    eng.running = True
    eng.step = 0
    eng.notes = []
    eng.forensic_log = []
    eng.finish_summary = ""
    eng.max_steps = eng.config.get("max_steps", 5)
    eng.image_history = 3
    eng.on_step_callback = None
    eng.pre_action_callback = None
    eng.approval_callback = None
    eng._consecutive_failures = 0
    eng._mfa_paused = False
    eng.llm = MagicMock()
    eng.executor = MagicMock()
    eng.logger = MagicMock()
    eng.checkpoint = MagicMock()
    eng.checkpoint.should_auto_save.return_value = False
    eng.gate = MagicMock()
    eng.gate.enabled = False
    eng.mfa_detector = MagicMock()
    eng.mfa_detector.check_window_titles.return_value = MagicMock(detected=False)
    eng.mfa_detector.check_screen.return_value = MagicMock(detected=False)
    eng.smart_waiter = MagicMock()
    eng._recovery_engine = MagicMock()
    eng._recorder = MagicMock()
    eng._recorder.is_recording = False
    return eng


class TestCheckpointSaveError:
    """Lines 792-793: checkpoint.save raises OSError or ValueError."""

    @patch("core.engine.capture_to_base64", return_value="b64")
    def test_checkpoint_save_oserror_caught(self, _mock_cap):
        eng = _make_bare_engine()
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        eng.checkpoint.should_auto_save.side_effect = [True, False]
        eng.checkpoint.save.side_effect = OSError("disk full")
        eng._run_inner("test")
        # Should not raise, and should continue to step 2
        assert eng.step == 2

    @patch("core.engine.capture_to_base64", return_value="b64")
    def test_checkpoint_save_valueerror_caught(self, _mock_cap):
        eng = _make_bare_engine()
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        eng.checkpoint.should_auto_save.side_effect = [True, False]
        eng.checkpoint.save.side_effect = ValueError("bad data")
        eng._run_inner("test")
        assert eng.step == 2


class TestParseActionMarkdownJsonDecodeError:
    """Lines 1185-1186: markdown-fenced JSON that fails json.loads."""

    def test_invalid_json_in_markdown_returns_none(self):
        eng = _make_bare_engine()
        text = "```json\n{not valid json}\n```"
        result = eng._parse_action(text)
        # json.loads fails → inner = None → not isinstance(dict → falls through
        assert result is None

    def test_valid_json_in_markdown_without_action_key(self):
        eng = _make_bare_engine()
        text = '```json\n{"foo": "bar"}\n```'
        result = eng._parse_action(text)
        # inner is a dict but no "action" key and no "tool_calls" → falls through
        assert result is None


class TestSignalReRaise:
    """Lines 608 and 638: KeyboardInterrupt/SystemExit re-raise guards in _run_inner."""

    @patch("core.engine.failsafe")
    @patch("core.engine.capture_to_base64", return_value="b64")
    def test_keyboard_interrupt_from_executor_propagates(self, _mock_cap, _mock_failsafe):
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "click", "x": 1, "y": 2}'
        # Make the executor raise KeyboardInterrupt — hits line 608 then 638
        eng.executor.execute_sync.side_effect = KeyboardInterrupt()
        import pytest
        with pytest.raises(KeyboardInterrupt):
            eng._run_inner("test goal")

    @patch("core.engine.failsafe")
    @patch("core.engine.capture_to_base64", return_value="b64")
    def test_system_exit_from_executor_propagates(self, _mock_cap, _mock_failsafe):
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "click", "x": 1, "y": 2}'
        eng.executor.execute_sync.side_effect = SystemExit(1)
        import pytest
        with pytest.raises(SystemExit):
            eng._run_inner("test goal")
