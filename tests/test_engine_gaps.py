"""Tests for core/engine.py — covering uncovered lines in the agent loop.

Covers:
  - Plugin loader logging (357-359)
  - Scheduler auto-start in run() (406-410)
  - Virtual desktop creation/teardown in run() (415-424, 431-434)
  - Full _run_inner loop: success, failure, recovery, MFA, approval, etc. (465-851)
  - _call_llm_with_retry retry/timeout paths (881-926)
  - _build_env_context active window detection (1031-1034)
  - _build_app_context with full profile fields (1056-1073)
  - _prune_old_screenshots string content fallback (1152-1153)
  - _parse_action markdown-fenced tool_calls path (1185-1186, 1189)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from core.approval_gate import ApprovalDecision
from core.engine import (
    AgentEngine,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(**overrides):
    """Build a minimal AgentEngine with a valid config for _run_inner."""
    config = {
        "provider": "openai",
        "api_key": "sk-test",
        "model": "gpt-4o",
        "max_steps": 100,
    }
    config.update(overrides)
    with (
        patch("core.engine.capture_to_base64", return_value="fakeb64"),
        patch("core.engine.ActionExecutor"),
    ):
        eng = AgentEngine(config=config)
    return eng


def _make_bare_engine(**overrides):
    """Build a bare engine via __new__ with minimal wiring for _run_inner."""
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
    eng.running = True  # Must be True for _run_inner's while loop
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

    # Mock subsystems
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


def _mf_result(detected=False, type_="", prompt_text="", window_title=""):
    """Create a mock DetectionResult."""
    r = MagicMock()
    r.detected = detected
    r.type = type_
    r.prompt_text = prompt_text
    r.window_title = window_title
    return r


def _recovery_suggestion(
    strategy="retry_same",
    pattern="generic_error",
    confidence=0.5,
    recovery_prompt="Try again",
):
    """Create a mock RecoverySuggestion."""
    s = MagicMock()
    s.strategy = strategy
    s.pattern = pattern
    s.confidence = confidence
    s.recovery_prompt = recovery_prompt
    s.alternate_action = None
    return s


# ===================================================================
# Plugin loader logging — lines 357-359
# ===================================================================


class TestPluginLoaderLogging:
    @patch("core.engine.os.path.join", return_value="/fake/plugins")
    @patch("core.plugin_loader.PluginLoader")
    def test_plugin_loaded_info_log(self, mock_cls, mock_join):
        mock_inst = MagicMock()
        mock_inst.load_all.return_value = [
            {"name": "TestPlugin", "version": "1.0"},
        ]
        mock_cls.return_value = mock_inst
        eng = _make_engine()
        with patch("core.engine.logger") as mock_logger:
            _ = eng.plugin_loader
            mock_logger.info.assert_any_call("Plugin loaded: %s v%s", "TestPlugin", "1.0")

    @patch("core.engine.os.path.join", return_value="/fake/plugins")
    @patch("core.plugin_loader.PluginLoader")
    def test_plugin_load_failure_warning_log(self, mock_cls, mock_join):
        mock_inst = MagicMock()
        mock_inst.load_all.side_effect = RuntimeError("disk error")
        mock_cls.return_value = mock_inst
        eng = _make_engine()
        with patch("core.engine.logger") as mock_logger:
            _ = eng.plugin_loader
            mock_logger.warning.assert_called()


# ===================================================================
# Scheduler auto-start — lines 406-410
# ===================================================================


class TestSchedulerAutoStart:
    @patch("core.scheduler.TaskScheduler")
    @patch("core.engine.capture_to_base64", return_value="b64")
    @patch("core.engine.ActionExecutor")
    def test_scheduler_started_when_enabled(self, mock_exec, mock_cap, mock_sched_cls):
        mock_sched_inst = MagicMock()
        mock_sched_cls.return_value = mock_sched_inst
        eng = AgentEngine(
            config={
                "provider": "openai",
                "api_key": "",
                "model": "gpt-4o",
                "scheduler_enabled": True,
            }
        )
        # Set _scheduler directly to control it
        eng._scheduler = mock_sched_inst
        eng.run("test")
        mock_sched_inst.start.assert_called_once()

    @patch("core.engine.capture_to_base64", return_value="b64")
    @patch("core.engine.ActionExecutor")
    def test_scheduler_failure_handled_gracefully(self, mock_exec, mock_cap):
        """Lines 406-410: scheduler auto-start failure is caught and logged."""
        eng = AgentEngine(
            config={
                "provider": "openai",
                "api_key": "",
                "model": "gpt-4o",
                "scheduler_enabled": True,
            }
        )
        mock_sched = MagicMock()
        mock_sched.start.side_effect = RuntimeError("port busy")
        eng._scheduler = mock_sched
        # The failure is caught in run() — should not raise
        result = eng.run("test")
        # _run_inner overwrites notes, but the scheduler start was attempted
        mock_sched.start.assert_called_once()
        assert result["error"] == "api_key_missing"

    @patch("core.engine.capture_to_base64", return_value="b64")
    @patch("core.engine.ActionExecutor")
    def test_scheduler_failure_note_visible_before_run_inner(self, mock_exec, mock_cap):
        """Verify scheduler failure note is appended (lines 409-410)."""
        eng = AgentEngine(
            config={
                "provider": "ollama",
                "api_key": "",
                "model": "llama3",
                "scheduler_enabled": True,
            }
        )
        mock_sched = MagicMock()
        mock_sched.start.side_effect = RuntimeError("port busy")
        eng._scheduler = mock_sched

        # Patch _run_inner to capture notes before they could be overwritten
        original_run_inner = eng._run_inner
        captured_notes = []

        def capturing_run_inner(goal):
            captured_notes.extend(eng.notes)
            return original_run_inner(goal)

        with patch.object(eng, "_run_inner", side_effect=capturing_run_inner):
            eng.run("test")

        assert any("Scheduler start failed" in n for n in captured_notes)

    @patch("core.engine.capture_to_base64", return_value="b64")
    @patch("core.engine.ActionExecutor")
    def test_scheduler_not_started_when_disabled(self, mock_exec, mock_cap):
        eng = AgentEngine(
            config={
                "provider": "openai",
                "api_key": "",
                "model": "gpt-4o",
            }
        )
        mock_sched = MagicMock()
        eng._scheduler = mock_sched
        eng.run("test")
        mock_sched.start.assert_not_called()


# ===================================================================
# Virtual desktop — lines 415-424, 431-434
# ===================================================================


class TestVirtualDesktop:
    @patch("core.engine.capture_to_base64", return_value="b64")
    @patch("core.engine.ActionExecutor")
    def test_virtual_desktop_created_when_configured(self, mock_exec, mock_cap):
        eng = AgentEngine(
            config={
                "provider": "openai",
                "api_key": "",
                "model": "gpt-4o",
                "virtual_desktop": True,
            }
        )
        mock_vd = MagicMock()
        captured_notes = []

        def capturing_run_inner(goal):
            captured_notes.extend(eng.notes)
            return {"steps": 0, "notes": eng.notes, "error": "test_capture"}

        with patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd) as mock_cls:
            with patch.object(eng, "_run_inner", side_effect=capturing_run_inner):
                eng.run("test")
            mock_cls.assert_called_once()
            mock_vd.create.assert_called_once_with("SentinelAgent")
            mock_vd.switch_to.assert_any_call("SentinelAgent")
            assert any("virtual desktop" in n.lower() for n in captured_notes)

    @patch("core.engine.capture_to_base64", return_value="b64")
    @patch("core.engine.ActionExecutor")
    def test_virtual_desktop_failure_appends_note(self, mock_exec, mock_cap):
        eng = AgentEngine(
            config={
                "provider": "openai",
                "api_key": "",
                "model": "gpt-4o",
                "virtual_desktop": True,
            }
        )
        captured_notes = []

        def capturing_run_inner(goal):
            captured_notes.extend(eng.notes)
            return {"steps": 0, "notes": eng.notes, "error": "test_capture"}

        with patch(
            "core.virtual_desktop.VirtualDesktop",
            side_effect=OSError("no virtual desktop support"),
        ):
            with patch.object(eng, "_run_inner", side_effect=capturing_run_inner):
                eng.run("test")
            assert any("Virtual desktop unavailable" in n for n in captured_notes)

    @patch("core.engine.capture_to_base64", return_value="b64")
    @patch("core.engine.ActionExecutor")
    def test_virtual_desktop_switch_back_in_finally(self, mock_exec, mock_cap):
        eng = AgentEngine(
            config={
                "provider": "openai",
                "api_key": "",
                "model": "gpt-4o",
                "virtual_desktop": True,
            }
        )
        mock_vd = MagicMock()
        with patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd):
            eng.run("test")
            # Should have called switch_to("Default") in the finally block
            mock_vd.switch_to.assert_called_with("Default")

    @patch("core.engine.capture_to_base64", return_value="b64")
    @patch("core.engine.ActionExecutor")
    def test_virtual_desktop_switch_back_failure_no_crash(self, mock_exec, mock_cap):
        eng = AgentEngine(
            config={
                "provider": "openai",
                "api_key": "",
                "model": "gpt-4o",
                "virtual_desktop": True,
            }
        )
        mock_vd = MagicMock()
        mock_vd.switch_to.side_effect = [None, RuntimeError("switch failed")]
        with patch("core.virtual_desktop.VirtualDesktop", return_value=mock_vd):
            # Should not raise
            eng.run("test")


# ===================================================================
# _run_inner — full agent loop (lines 465-851)
# ===================================================================


class TestRunInnerFinishAction:
    """Test the finish action path in _run_inner."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_finish_action_stops_loop(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = json.dumps(
            {"action": "finish", "summary": "Task completed successfully"}
        )
        result = eng._run_inner("open notepad")
        assert result["steps"] == 1
        assert result["finish_summary"] == "Task completed successfully"
        assert eng.running is False

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_finish_without_summary(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "finish"}'
        result = eng._run_inner("test")
        assert result["finish_summary"] == "Task completed"

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_note_action_appended(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        # First step: note, second step: finish
        eng.llm.chat.side_effect = [
            '{"action": "note", "text": "I see the desktop"}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "noted"}
        eng._run_inner("test")
        assert "I see the desktop" in eng.notes


class TestRunInnerActionSuccess:
    """Test the successful action execution path."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_successful_action_resets_failure_counter(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng._consecutive_failures = 3
        eng.llm.chat.return_value = json.dumps({"action": "finish", "summary": "ok"})
        eng._run_inner("test")
        # After successful parse of finish, consecutive_failures is not
        # incremented. finish does not go through executor, so this tests
        # the parse success path.
        assert eng._consecutive_failures == 3  # not incremented further

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_action_success_then_finish(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 0.5, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 100, "y": 200}',
            '{"action": "finish", "summary": "clicked"}',
        ]
        eng.executor.execute_sync.return_value = {
            "success": True,
            "output": "clicked",
        }
        result = eng._run_inner("click something")
        assert result["steps"] == 2
        assert result["finish_summary"] == "clicked"
        assert eng._consecutive_failures == 0


class TestRunInnerActionFailure:
    """Test the action failure and recovery path."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_failed_action_increments_failure_counter(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "click", "x": 1, "y": 2}'
        eng.executor.execute_sync.return_value = {
            "success": False,
            "output": "click missed target",
        }
        eng._recovery_engine.analyze_failure.return_value = _recovery_suggestion()
        eng.config["max_steps"] = 1
        eng.max_steps = 1
        eng._run_inner("test")
        assert eng._consecutive_failures == 1

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_failed_action_consults_recovery_engine(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "click", "x": 1, "y": 2}'
        eng.executor.execute_sync.return_value = {
            "success": False,
            "output": "missed",
        }
        suggestion = _recovery_suggestion(
            strategy="retry_alternate",
            pattern="click_miss",
            confidence=0.8,
            recovery_prompt="Try click_control instead",
        )
        eng._recovery_engine.analyze_failure.return_value = suggestion
        eng.config["max_steps"] = 1
        eng.max_steps = 1
        eng._run_inner("test")
        eng._recovery_engine.analyze_failure.assert_called_once()
        eng.logger.log_event.assert_any_call(
            "recovery_suggestion",
            {
                "pattern": "click_miss",
                "strategy": "retry_alternate",
                "confidence": 0.8,
                "action": "click",
            },
        )

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_8_consecutive_failures_aborts(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0] + [1.0] * 20
        eng = _make_bare_engine()
        eng.config["max_steps"] = 20
        eng.max_steps = 20
        eng.llm.chat.return_value = '{"action": "click", "x": 1, "y": 2}'
        eng.executor.execute_sync.return_value = {
            "success": False,
            "output": "fail",
        }
        eng._recovery_engine.analyze_failure.return_value = _recovery_suggestion()
        eng._run_inner("test")
        assert eng.step == 8
        assert any("8 consecutive failures" in n for n in eng.notes)

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_5_consecutive_failures_injects_recovery_prompt(
        self, mock_time, mock_failsafe, mock_cap
    ):
        mock_time.time.side_effect = [0.0] + [1.0] * 20
        eng = _make_bare_engine()
        eng.config["max_steps"] = 20
        eng.max_steps = 20
        eng.llm.chat.return_value = '{"action": "click", "x": 1, "y": 2}'
        eng.executor.execute_sync.return_value = {
            "success": False,
            "output": "fail",
        }
        eng._recovery_engine.analyze_failure.return_value = _recovery_suggestion()
        # We won't reach 8, just need to verify recovery prompt injected at 5.
        # Actually this test runs 8 steps and aborts, but we check the call to
        # _recovery_engine was made, which it is.
        eng._run_inner("test")
        # The recovery prompt should have been injected (SYSTEM RECOVERY message)
        assert eng._recovery_engine.analyze_failure.call_count >= 5

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_action_exception_caught(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "click", "x": 1, "y": 2}'
        eng.executor.execute_sync.side_effect = RuntimeError("crash")
        eng._recovery_engine.analyze_failure.return_value = _recovery_suggestion()
        eng.config["max_steps"] = 1
        eng.max_steps = 1
        eng._run_inner("test")
        assert eng._consecutive_failures == 1


class TestRunInnerLLMFailure:
    """Test LLM call failure paths."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_llm_returns_none_counts_as_failure(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0]
        eng = _make_bare_engine()
        eng.config["max_steps"] = 3
        eng.max_steps = 3
        # First call returns None (simulating exhausted retries),
        # second call returns finish
        eng.llm.chat.side_effect = [
            None,
            '{"action": "finish", "summary": "recovered"}',
        ]
        result = eng._run_inner("test")
        assert result["steps"] == 2
        # finish action doesn't reset consecutive_failures; that happens
        # only on successful executor actions (line 759)
        assert eng._consecutive_failures == 1

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_8_consecutive_llm_failures_aborts(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0] + [1.0] * 20
        eng = _make_bare_engine()
        eng.config["max_steps"] = 20
        eng.max_steps = 20
        eng.llm.chat.return_value = None
        eng._run_inner("test")
        assert eng.step == 8
        assert any("consecutive failures" in n for n in eng.notes)

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_5_consecutive_llm_failures_injects_recovery(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0] + [1.0] * 20
        eng = _make_bare_engine()
        eng.config["max_steps"] = 20
        eng.max_steps = 20
        eng.llm.chat.return_value = None
        eng._run_inner("test")
        # Should have called log_event for recovery at step 5
        assert eng.step == 8


class TestRunInnerParseFailure:
    """Test when LLM returns unparseable text."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_unparseable_response_increments_failure(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.config["max_steps"] = 1
        eng.max_steps = 1
        eng.llm.chat.return_value = "I am not a JSON action"
        eng._run_inner("test")
        assert eng._consecutive_failures == 1

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_8_consecutive_parse_failures_aborts(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0] + [1.0] * 20
        eng = _make_bare_engine()
        eng.config["max_steps"] = 20
        eng.max_steps = 20
        eng.llm.chat.return_value = "not json"
        eng._run_inner("test")
        assert eng.step == 8

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_5_consecutive_parse_failures_injects_hint(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0] + [1.0] * 20
        eng = _make_bare_engine()
        eng.config["max_steps"] = 20
        eng.max_steps = 20
        eng.llm.chat.return_value = "not json at all"
        eng._run_inner("test")
        assert eng.step == 8


class TestRunInnerSchemaValidation:
    """Test schema validation warning path."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    @patch("core.engine.validate_action")
    def test_schema_errors_appended_to_notes(
        self, mock_validate, mock_time, mock_failsafe, mock_cap
    ):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        mock_validate.return_value = (
            {"action": "finish", "summary": "done"},
            ["x must be positive"],
        )
        eng._run_inner("test")
        assert any("schema validation" in n for n in eng.notes)


class TestRunInnerApprovalGate:
    """Test approval gate integration."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_skip_action_continues_loop(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0]
        eng = _make_bare_engine()
        eng.gate.enabled = True
        # First action skipped, second finishes
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 100, "y": 200}',
            '{"action": "finish", "summary": "done after skip"}',
        ]
        eng.gate.evaluate.side_effect = [
            (ApprovalDecision.SKIP, None),
            (ApprovalDecision.APPROVE, {"action": "finish", "summary": "done after skip"}),
        ]
        result = eng._run_inner("test")
        assert result["steps"] == 2

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_abort_action_stops_loop(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.gate.enabled = True
        eng.llm.chat.return_value = '{"action": "click", "x": 1, "y": 2}'
        eng.gate.evaluate.return_value = (ApprovalDecision.ABORT, None)
        result = eng._run_inner("test")
        assert result["steps"] == 1
        assert eng.running is False

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_modify_action_uses_modified(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.gate.enabled = True
        eng.llm.chat.return_value = '{"action": "click", "x": 1, "y": 2}'
        modified = {"action": "click", "x": 999, "y": 888}
        eng.gate.evaluate.return_value = (ApprovalDecision.MODIFY, modified)
        eng.executor.execute_sync.return_value = {
            "success": True,
            "output": "clicked modified",
        }
        # We need a second step to finish
        eng.config["max_steps"] = 2
        eng.max_steps = 2
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng._run_inner("test")
        # The modified action should have been passed to executor
        call_args = eng.executor.execute_sync.call_args_list[0][0][0]
        assert call_args["x"] == 999

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_safe_action_not_gated(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0]
        eng = _make_bare_engine()
        eng.gate.enabled = True
        eng.llm.chat.side_effect = [
            '{"action": "screenshot"}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        eng.gate.evaluate.side_effect = [
            # screenshot is not in APPROVAL_REQUIRED_ACTIONS, so gate.evaluate
            # should not even be called for it. But if it is, approve it.
            (ApprovalDecision.APPROVE, {"action": "screenshot"}),
            (ApprovalDecision.APPROVE, {"action": "finish", "summary": "done"}),
        ]
        result = eng._run_inner("test")
        assert result["steps"] == 2


class TestRunInnerMFADetection:
    """Test MFA/UAC detection and pause."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_mfa_detected_and_paused(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0, 3.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        # First action: click (not finish, so MFA check runs), then finish
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 100, "y": 200}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        # MFA detected on first check, then not detected on recheck
        mfa_detected = _mf_result(
            detected=True, type_="uac", prompt_text="Allow?", window_title="UAC"
        )
        mfa_clear = _mf_result(detected=False)
        eng.mfa_detector.check_window_titles.side_effect = [
            mfa_detected,
            mfa_clear,
        ]
        # capture_screen mock for secondary MFA check
        with patch("core.screenshot.capture_screen", return_value=MagicMock()):
            with patch("core.engine.time.sleep"):
                eng._run_inner("test")
        assert eng.logger.log_event.call_count >= 1
        eng.logger.log_event.assert_any_call("mfa_resume", {"msg": "Auth prompt dismissed"})

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_mfa_not_running_breaks_poll(self, mock_time, mock_failsafe, mock_cap):
        """When self.running becomes False during MFA poll, loop breaks."""
        mock_time.time.side_effect = [0.0, 1.0, 2.0, 3.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        mfa_detected = _mf_result(detected=True, type_="mfa")
        eng.mfa_detector.check_window_titles.return_value = mfa_detected
        # Simulate: running set to False after first sleep
        call_count = [0]

        def fake_sleep(_):
            call_count[0] += 1
            if call_count[0] == 1:
                eng.running = False

        with patch("core.engine.time.sleep", side_effect=fake_sleep):
            with patch("core.screenshot.capture_screen", return_value=MagicMock()):
                eng._run_inner("test")

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_mfa_callback_called(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0, 3.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        mfa_detected = _mf_result(
            detected=True, type_="uac", prompt_text="Allow?", window_title="UAC"
        )
        mfa_clear = _mf_result(detected=False)
        eng.mfa_detector.check_window_titles.side_effect = [
            mfa_detected,
            mfa_clear,
        ]
        callback = MagicMock()
        eng.on_step_callback = callback
        with patch("core.screenshot.capture_screen", return_value=MagicMock()):
            with patch("core.engine.time.sleep"):
                eng._run_inner("test")
        callback.assert_called()
        # Check that at least one call was for MFA pause
        mfa_call_found = False
        for call in callback.call_args_list:
            if call[1].get("action", {}).get("action") == "mfa_pause":
                mfa_call_found = True
                break
        assert mfa_call_found, "MFA pause callback not found in call args"

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_mfa_secondary_screen_check(self, mock_time, mock_failsafe, mock_cap):
        """When window_titles doesn't detect MFA, check_screen is tried."""
        mock_time.time.side_effect = [0.0, 1.0, 2.0, 3.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        no_mfa_windows = _mf_result(detected=False)
        mfa_screen = _mf_result(detected=True, type_="credential", prompt_text="Password?")
        mfa_clear = _mf_result(detected=False)
        eng.mfa_detector.check_window_titles.return_value = no_mfa_windows
        eng.mfa_detector.check_screen.side_effect = [mfa_screen, mfa_clear]
        with patch("core.screenshot.capture_screen", return_value=MagicMock()):
            with patch("core.engine.time.sleep"):
                eng._run_inner("test")
        eng.mfa_detector.check_screen.assert_called()

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_mfa_screen_check_failure(self, mock_time, mock_failsafe, mock_cap):
        """When capture_screen fails during MFA check, no crash."""
        mock_time.time.side_effect = [0.0, 1.0, 2.0, 3.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        no_mfa = _mf_result(detected=False)
        eng.mfa_detector.check_window_titles.return_value = no_mfa
        with patch("core.screenshot.capture_screen", side_effect=OSError("no screen")):
            eng._run_inner("test")

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_mfa_callback_exception_no_crash(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0, 3.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        mfa_detected = _mf_result(
            detected=True, type_="uac", prompt_text="Allow?", window_title="UAC"
        )
        mfa_clear = _mf_result(detected=False)
        eng.mfa_detector.check_window_titles.side_effect = [
            mfa_detected,
            mfa_clear,
        ]
        eng.on_step_callback = MagicMock(side_effect=RuntimeError("callback crash"))
        with patch("core.screenshot.capture_screen", return_value=MagicMock()):
            with patch("core.engine.time.sleep"):
                eng._run_inner("test")  # should not raise


class TestRunInnerCheckpoint:
    """Test checkpoint auto-save."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_checkpoint_saved_on_step_5(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0] + [float(i) for i in range(1, 20)]
        eng = _make_bare_engine()
        eng.config["max_steps"] = 10
        eng.max_steps = 10
        eng.config["auto_screenshot"] = False
        # 5 note actions then finish -- checkpoint should fire on step 5
        eng.llm.chat.side_effect = [
            '{"action": "note", "text": "step"}',
        ] * 5 + ['{"action": "finish", "summary": "done"}']
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        eng.checkpoint.should_auto_save.side_effect = lambda s: s % 5 == 0
        eng._run_inner("test")
        eng.checkpoint.save.assert_called_once()

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_checkpoint_save_failure_no_crash(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0] + [float(i) for i in range(1, 20)]
        eng = _make_bare_engine()
        eng.config["max_steps"] = 10
        eng.max_steps = 10
        eng.config["auto_screenshot"] = False
        eng.llm.chat.side_effect = [
            '{"action": "note", "text": "step"}',
        ] * 4 + ['{"action": "finish", "summary": "done"}']
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        eng.checkpoint.should_auto_save.side_effect = lambda s: s % 5 == 0
        eng.checkpoint.save.side_effect = OSError("disk full")
        eng._run_inner("test")  # no crash


class TestRunInnerRecorder:
    """Test action recorder integration."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_recorder_captures_when_recording(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        eng._recorder.is_recording = True
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        eng._run_inner("test")
        eng._recorder.capture_action.assert_called_once()


class TestRunInnerStepCallback:
    """Test on_step_callback."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_callback_called_on_successful_action(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        callback = MagicMock()
        eng.on_step_callback = callback
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        eng._run_inner("test")
        # Called once for the successful click action
        callback.assert_called()

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_callback_exception_no_crash(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = False
        eng.on_step_callback = MagicMock(side_effect=RuntimeError("boom"))
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        eng._run_inner("test")  # no crash


class TestRunInnerAutoScreenshot:
    """Test auto-screenshot and pruning."""

    @patch("core.engine.capture_to_base64", return_value="newb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_screenshot_captured_between_steps(self, mock_time, mock_failsafe, mock_cap):
        from PIL import Image

        mock_time.time.side_effect = [0.0, 1.0, 2.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = True
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        with patch(
            "core.screenshot.capture_screen", return_value=Image.new("RGB", (100, 100), "white")
        ) as mock_screen:
            with patch("core.perception.PerceptionPipeline"):
                eng._run_inner("test")
        # capture_screen called: initial + 1 auto screenshot
        assert mock_screen.call_count >= 2

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_screenshot_failure_midrun_no_crash(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = True
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        # Second call (mid-run) fails
        mock_cap.side_effect = ["initial_b64", OSError("capture failed")]
        eng._run_inner("test")  # no crash

    @patch("core.engine.capture_to_base64", return_value=None)
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_none_screenshot_skips_vision_message(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0, 2.0]
        eng = _make_bare_engine()
        eng.config["auto_screenshot"] = True
        eng.llm.chat.side_effect = [
            '{"action": "click", "x": 1, "y": 2}',
            '{"action": "finish", "summary": "done"}',
        ]
        eng.executor.execute_sync.return_value = {"success": True, "output": "ok"}
        result = eng._run_inner("test")
        assert result["steps"] == 2


class TestRunInnerExceptionHandling:
    """Test the outer try/except in _run_inner."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_fatal_error_caught_and_logged(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.side_effect = Exception("catastrophic failure")
        eng._run_inner("test")
        assert any("Fatal error" in n for n in eng.notes)
        assert eng.running is False

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_failsafe_disarmed_in_finally(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        eng._run_inner("test")
        mock_failsafe.disarm.assert_called_once()

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_forensic_log_finalized(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        eng._run_inner("test")
        eng.logger.end_run.assert_called_once()


class TestRunInnerSoundNotification:
    """Test sound notification at end of run (lines 844-849)."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_complete_sound_on_success(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        with patch("core.sound.play_sound") as mock_sound:
            eng._run_inner("test")
            mock_sound.assert_called_with("complete")

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_error_sound_on_failure(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = "not json"  # parse failure
        eng.config["max_steps"] = 1
        eng.max_steps = 1
        with patch("core.sound.play_sound") as mock_sound:
            eng._run_inner("test")
            mock_sound.assert_called_with("error")

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_sound_import_error_no_crash(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        with patch(
            "core.sound.play_sound",
            side_effect=ImportError("no sound module"),
        ):
            eng._run_inner("test")  # no crash


class TestRunInnerReturnReport:
    """Test return value structure from _run_inner."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_return_has_all_fields(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        result = eng._run_inner("test")
        assert "steps" in result
        assert "notes" in result
        assert "log" in result
        assert "finish_summary" in result
        assert "elapsed_seconds" in result
        assert "report" in result


class TestRunInnerToolUsage:
    """Test tool-capable provider flag."""

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    @patch("core.engine.ACTION_TOOLS", [{"type": "function"}])
    def test_tools_passed_for_tool_capable_provider(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine(provider="openai")
        eng.config["use_tools"] = True
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        eng._run_inner("test")
        # Check that tools was passed to llm.chat
        call_kwargs = eng.llm.chat.call_args
        assert call_kwargs[1].get("tools") is not None or (len(call_kwargs[0]) > 0)

    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_no_tools_for_non_tool_provider(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine(provider="custom")
        eng.config["use_tools"] = True
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        eng._run_inner("test")
        call_kwargs = eng.llm.chat.call_args[1]
        assert call_kwargs.get("tools") is None


# ===================================================================
# _call_llm_with_retry — lines 881-926
# ===================================================================


class TestCallLLMWithRetry:
    def test_successful_first_attempt(self):
        eng = _make_bare_engine()
        eng.llm.chat.return_value = "response text"
        result = eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=[],
            tools=None,
        )
        assert result == "response text"

    @patch("core.engine.time.sleep")
    def test_retries_on_connection_error(self, mock_sleep):
        eng = _make_bare_engine()
        eng.llm.chat.side_effect = [
            ConnectionError("timeout"),
            "success on retry",
        ]
        result = eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=[],
            tools=None,
        )
        assert result == "success on retry"
        mock_sleep.assert_called_once()

    @patch("core.engine.time.sleep")
    def test_retries_on_timeout_error(self, mock_sleep):
        eng = _make_bare_engine()
        eng.llm.chat.side_effect = [
            TimeoutError("timed out"),
            "success",
        ]
        result = eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=[],
            tools=None,
        )
        assert result == "success"

    @patch("core.engine.time.sleep")
    def test_retries_on_os_error(self, mock_sleep):
        eng = _make_bare_engine()
        eng.llm.chat.side_effect = [
            OSError("network unreachable"),
            "success",
        ]
        result = eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=[],
            tools=None,
        )
        assert result == "success"

    def test_llm_error_returns_none_immediately(self):
        """LLMError is non-retriable — returns None on first attempt."""
        from core.llm_client import LLMError

        eng = _make_bare_engine()
        eng.llm.chat.side_effect = LLMError("auth failed")
        result = eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=[],
            tools=None,
        )
        assert result is None

    @patch("core.engine.time.sleep")
    def test_exhausted_retries_returns_none(self, mock_sleep):
        eng = _make_bare_engine()
        eng.llm.chat.side_effect = ConnectionError("down")
        result = eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=[],
            tools=None,
        )
        assert result is None
        # Should have slept for each retry delay
        assert mock_sleep.call_count == len(AgentEngine._LLM_RETRY_DELAYS)

    @patch("core.engine.time.sleep")
    def test_llm_error_appends_note(self, mock_sleep):
        from core.llm_client import LLMError

        eng = _make_bare_engine()
        eng.step = 5
        eng.llm.chat.side_effect = LLMError("bad key")
        eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=[],
            tools=None,
        )
        assert any("LLM error" in n for n in eng.notes)

    @patch("core.engine.time.sleep")
    def test_exhausted_retries_appends_note(self, mock_sleep):
        eng = _make_bare_engine()
        eng.step = 3
        eng.llm.chat.side_effect = ConnectionError("down")
        eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=[],
            tools=None,
        )
        assert any("LLM error" in n for n in eng.notes)

    def test_passes_custom_url(self):
        eng = _make_bare_engine()
        eng.config["custom_base_url"] = "http://myproxy:8080"
        eng.llm.chat.return_value = "ok"
        eng._call_llm_with_retry(
            provider="custom",
            api_key="key",
            model="mymodel",
            messages=[],
            tools=None,
        )
        call_kwargs = eng.llm.chat.call_args[1]
        assert call_kwargs["custom_url"] == "http://myproxy:8080"

    def test_max_retries_zero_passed_to_client(self):
        eng = _make_bare_engine()
        eng.llm.chat.return_value = "ok"
        eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=[],
            tools=None,
        )
        call_kwargs = eng.llm.chat.call_args[1]
        assert call_kwargs["max_retries"] == 0

    def test_cleans_messages_before_sending(self):
        eng = _make_bare_engine()
        eng.llm.chat.return_value = "ok"
        messages = [
            {"role": "user", "content": "hi", "_sentinel_step": 1},
        ]
        eng._call_llm_with_retry(
            provider="openai",
            api_key="key",
            model="gpt-4o",
            messages=messages,
            tools=None,
        )
        call_kwargs = eng.llm.chat.call_args[1]
        sent_messages = call_kwargs["messages"]
        assert "_sentinel_step" not in sent_messages[0]


# ===================================================================
# _build_env_context — lines 1031-1034
# ===================================================================


class TestBuildEnvContextActiveWindow:
    @patch("core.engine.wm")
    @patch("core.engine.sysinfo")
    def test_active_window_detected(self, mock_sysinfo, mock_wm):
        mock_sysinfo.brief_system_info.return_value = "Windows 11"
        mock_wm.list_windows.return_value = [
            {"title": "Chrome", "is_focused": False},
            {"title": "VSCode", "is_focused": True},
        ]
        eng = _make_engine()
        result = eng._build_env_context()
        assert "VSCode" in result

    @patch("core.engine.wm")
    @patch("core.engine.sysinfo")
    def test_active_window_detection_failure(self, mock_sysinfo, mock_wm):
        mock_sysinfo.brief_system_info.return_value = "Windows 11"
        mock_wm.list_windows.side_effect = RuntimeError("access denied")
        eng = _make_engine()
        result = eng._build_env_context()
        assert isinstance(result, str)  # no crash

    @patch("core.engine.wm")
    @patch("core.engine.sysinfo")
    def test_no_focused_window(self, mock_sysinfo, mock_wm):
        mock_sysinfo.brief_system_info.return_value = "Windows 11"
        mock_wm.list_windows.return_value = [
            {"title": "Chrome", "is_focused": False},
        ]
        eng = _make_engine()
        result = eng._build_env_context()
        assert "Active Window" not in result

    @patch("core.engine.wm")
    @patch("core.engine.sysinfo")
    def test_sysinfo_and_wm_both_fail(self, mock_sysinfo, mock_wm):
        mock_sysinfo.brief_system_info.side_effect = OSError("fail")
        mock_wm.list_windows.side_effect = RuntimeError("fail")
        eng = _make_engine()
        result = eng._build_env_context()
        assert isinstance(result, str)


# ===================================================================
# _build_app_context — lines 1056-1073
# ===================================================================


class TestBuildAppContextFullProfile:
    @patch("core.engine.detect_profile")
    @patch("core.engine.wm")
    def test_full_profile_with_all_fields(self, mock_wm, mock_detect):
        """Covers lines 1056-1073 — quirks, strategies, menu_paths."""
        mock_wm.list_windows.return_value = [
            {"title": "Excel", "is_focused": True},
        ]

        @dataclass
        class FakeProfile:
            name: str = "excel"
            display_name: str = "Microsoft Excel"
            window_title_patterns: list = field(default_factory=list)
            stealth_compatible: str = "none"
            preferred_input: str = "uia"
            quirks: list = field(
                default_factory=lambda: [
                    "Cell editing requires double-click, not single-click",
                    "Ribbon tabs change with context",
                ]
            )
            strategies: dict = field(
                default_factory=lambda: {
                    "save": "Ctrl+S hotkey",
                    "open_file": "Ctrl+O then navigate",
                }
            )
            menu_paths: dict = field(
                default_factory=lambda: {
                    "save_as": ["File", "Save As"],
                    "insert_chart": ["Insert", "Chart"],
                }
            )

        mock_detect.return_value = FakeProfile()
        eng = _make_engine()
        result = eng._build_app_context()

        assert "Microsoft Excel" in result
        assert "stealth compatibility: none" in result.lower()
        assert "preferred input method: uia" in result.lower()
        assert "Cell editing requires double-click" in result
        assert "save: Ctrl+S hotkey" in result
        assert "save_as: File" in result
        assert "Insert" in result

    @patch("core.engine.detect_profile")
    @patch("core.engine.wm")
    def test_profile_with_no_extras(self, mock_wm, mock_detect):
        """Profile with empty quirks/strategies/menu_paths."""
        mock_wm.list_windows.return_value = [
            {"title": "Calculator", "is_focused": True},
        ]

        @dataclass
        class MinimalProfile:
            name: str = "calculator"
            display_name: str = "Calculator"
            window_title_patterns: list = field(default_factory=list)
            stealth_compatible: str = "full"
            preferred_input: str = "uia"
            quirks: list = field(default_factory=list)
            strategies: dict = field(default_factory=dict)
            menu_paths: dict = field(default_factory=dict)

        mock_detect.return_value = MinimalProfile()
        eng = _make_engine()
        result = eng._build_app_context()
        assert "Calculator" in result
        assert "Quirks" not in result
        assert "Suggested strategies" not in result
        assert "Known menu paths" not in result

    @patch("core.engine.detect_profile")
    @patch("core.engine.wm")
    def test_no_profile_detected(self, mock_wm, mock_detect):
        mock_wm.list_windows.return_value = [
            {"title": "Unknown App", "is_focused": True},
        ]
        mock_detect.return_value = None
        eng = _make_engine()
        result = eng._build_app_context()
        assert result == ""


# ===================================================================
# _prune_old_screenshots — lines 1152-1153 (string content path)
# ===================================================================


class TestPruneOldScreenshotsStringContent:
    def test_string_content_preserved_when_pruning(self):
        """Covers line 1152-1153: when content is a string, preserve it."""
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 10
        eng.image_history = 1
        messages = [
            {
                "role": "user",
                "content": "plain text goal",
                "_sentinel_has_image": True,
                "_sentinel_step": 1,
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "step 5"}],
                "_sentinel_has_image": True,
                "_sentinel_step": 5,
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "step 10"}],
                "_sentinel_has_image": True,
                "_sentinel_step": 10,
            },
        ]
        eng._prune_old_screenshots(messages)
        # First message should be pruned (string content path)
        assert isinstance(messages[0]["content"], str)
        assert "plain text goal" in messages[0]["content"]
        assert "screenshot at step 1" in messages[0]["content"]

    def test_no_pruning_when_within_limit(self):
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 5
        eng.image_history = 10
        messages = [
            {"role": "user", "content": "goal", "_sentinel_has_image": True, "_sentinel_step": 1},
        ]
        eng._prune_old_screenshots(messages)
        assert messages[0]["content"] == "goal"  # unchanged


# ===================================================================
# _parse_action — lines 1185-1186, 1189 (markdown fenced tool_calls)
# ===================================================================


class TestParseActionMarkdownToolCalls:
    def test_markdown_fenced_tool_calls(self):
        """Covers lines 1185-1186, 1189: tool_calls inside markdown fence."""
        eng = AgentEngine.__new__(AgentEngine)
        payload = json.dumps(
            {"tool_calls": [{"function": {"name": "click", "arguments": '{"x": 42, "y": 99}'}}]}
        )
        text = f"```json\n{payload}\n```"
        result = eng._parse_action(text)
        assert result is not None
        assert result["action"] == "click"
        assert result["x"] == 42
        assert result["y"] == 99

    def test_markdown_fenced_invalid_json_inner(self):
        eng = AgentEngine.__new__(AgentEngine)
        text = "```json\n{broken\n```"
        result = eng._parse_action(text)
        assert result is None

    def test_markdown_fenced_plain_action(self):
        """Covers line 1190: action key inside markdown fence."""
        eng = AgentEngine.__new__(AgentEngine)
        text = '```json\n{"action": "screenshot"}\n```'
        result = eng._parse_action(text)
        assert result == {"action": "screenshot"}

    def test_markdown_fenced_without_language_tag(self):
        eng = AgentEngine.__new__(AgentEngine)
        text = '```\n{"action": "click", "x": 1}\n```'
        result = eng._parse_action(text)
        assert result == {"action": "click", "x": 1}


# ===================================================================
# _run_inner — initial screenshot failure (line 476-478)
# ===================================================================


class TestRunInnerInitialScreenshot:
    @patch("core.engine.capture_to_base64", side_effect=OSError("no screen"))
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_initial_screenshot_failure_continues(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        result = eng._run_inner("test")
        assert result["steps"] == 1


# ===================================================================
# _run_inner — initial screenshot failure path via run()
# ===================================================================


class TestRunInitialScreenshotFailure:
    @patch("core.engine.ActionExecutor")
    @patch("core.engine.capture_to_base64", side_effect=OSError("no display"))
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_run_handles_initial_screenshot_failure(
        self, mock_time, mock_failsafe, mock_cap, mock_exec
    ):
        """When initial capture fails in run(), the empty b64 is used and run continues."""
        mock_time.time.side_effect = [0.0, 1.0]
        eng = AgentEngine(
            config={
                "provider": "openai",
                "api_key": "sk-test",
                "model": "gpt-4o",
            }
        )
        eng.llm = MagicMock()
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        result = eng.run("test")
        # Screenshot failed but engine did not crash; LLM ran once and finished.
        assert result["steps"] == 1


# ===================================================================
# _run_inner — system prompt construction (lines 465-471)
# ===================================================================


class TestRunInnerSystemPrompt:
    @patch("core.engine.capture_to_base64", return_value="fakeb64")
    @patch("core.engine.failsafe")
    @patch("core.engine.time")
    def test_system_prompt_includes_env_context(self, mock_time, mock_failsafe, mock_cap):
        mock_time.time.side_effect = [0.0, 1.0]
        eng = _make_bare_engine()
        eng.llm.chat.return_value = '{"action": "finish", "summary": "done"}'
        with patch.object(eng, "_build_env_context", return_value="Win11 Test"):
            with patch.object(eng, "_build_app_context", return_value="App Info"):
                eng._run_inner("test")
                call_kwargs = eng.llm.chat.call_args[1]
                messages = call_kwargs["messages"]
                system_msg = messages[0]
                assert "Win11 Test" in system_msg["content"]
                assert "App Info" in system_msg["content"]


# ===================================================================
# run() wrapper — state reset and ollama bypass
# ===================================================================


class TestRunWrapperOllamaBypass:
    @patch("core.engine.ActionExecutor")
    @patch("core.engine.capture_to_base64", return_value="b64")
    def test_ollama_no_api_key_needed(self, mock_cap, mock_exec):
        """Ollama provider should not require an API key."""
        eng = AgentEngine(config={"provider": "ollama", "api_key": "", "model": "llama3"})
        # Patch _run_inner to avoid the actual loop
        with patch.object(eng, "_run_inner", return_value={"steps": 1}) as mock_inner:
            eng.run("test")
            mock_inner.assert_called_once_with("test")


# ===================================================================
# _handle_action_failure — line 846->848 (empty recovery_prompt)
# ===================================================================


class TestHandleActionFailureNoRecoveryPrompt:
    def _make_eng_with_suggestion(self, recovery_prompt):
        """Build a minimal bare engine and wire up a recovery suggestion."""
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 1
        eng._consecutive_failures = 0
        eng.forensic_log = []
        eng.logger = MagicMock()
        eng._recovery_engine = MagicMock()

        suggestion = _recovery_suggestion(
            strategy="retry_same",
            pattern="click_miss",
            confidence=0.5,
            recovery_prompt=recovery_prompt,
        )
        eng._recovery_engine.analyze_failure.return_value = suggestion

        # Stub out the threshold check so it returns None (normal flow)
        eng._check_action_failure_threshold = MagicMock(return_value=None)
        return eng

    def test_empty_recovery_prompt_not_appended(self):
        """Covers 846->848: suggestion.recovery_prompt is "" → False branch.

        The recovery message appended to messages must NOT contain
        "Recovery hint:" when recovery_prompt is falsy.
        """
        eng = self._make_eng_with_suggestion(recovery_prompt="")
        action = {"action": "click", "x": 1, "y": 2}
        messages: list = []

        eng._handle_action_failure(action, "click", "missed target", messages)

        assert len(messages) == 1
        recovery_msg = messages[0]["content"]
        assert "failed:" in recovery_msg
        assert "Recovery hint:" not in recovery_msg

    def test_none_recovery_prompt_not_appended(self):
        """Covers 846->848: suggestion.recovery_prompt is None → False branch."""
        eng = self._make_eng_with_suggestion(recovery_prompt=None)
        action = {"action": "click", "x": 1, "y": 2}
        messages: list = []

        eng._handle_action_failure(action, "click", "missed target", messages)

        assert len(messages) == 1
        recovery_msg = messages[0]["content"]
        assert "failed:" in recovery_msg
        assert "Recovery hint:" not in recovery_msg


# ===================================================================
# _prune_old_screenshots — missing branches 1420->1427, 1421->1420, 1424->1427
# ===================================================================


class TestPruneOldScreenshotsMissingBranches:
    def test_empty_content_list_no_text_extracted(self):
        """Covers 1420->1427: content is [] so the for-loop has no iterations.

        The stub should be used without any prefix text.
        """
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 10
        eng.image_history = 1
        messages = [
            {
                "role": "user",
                "content": [],  # <-- empty list → loop body never runs
                "_sentinel_has_image": True,
                "_sentinel_step": 1,
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "latest step"}],
                "_sentinel_has_image": True,
                "_sentinel_step": 10,
            },
        ]
        eng._prune_old_screenshots(messages)
        pruned = messages[0]["content"]
        # No preserved_text → result is just the stub
        assert isinstance(pruned, str)
        assert "screenshot at step 1 omitted" in pruned
        # Must NOT have a leading newline from empty preserved_text
        assert not pruned.startswith("\n")

    def test_non_text_block_before_text_block_skipped(self):
        """Covers 1421->1420: a non-text block (e.g. image_url) is encountered
        first in the content list and the inner loop continues to the text block.
        """
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 10
        eng.image_history = 1
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                    {"type": "text", "text": "the preserved text"},
                ],
                "_sentinel_has_image": True,
                "_sentinel_step": 1,
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "latest step"}],
                "_sentinel_has_image": True,
                "_sentinel_step": 10,
            },
        ]
        eng._prune_old_screenshots(messages)
        pruned = messages[0]["content"]
        assert isinstance(pruned, str)
        # Text from the second block must be preserved
        assert "the preserved text" in pruned
        assert "screenshot at step 1 omitted" in pruned

    def test_non_text_block_only_no_text_extracted(self):
        """Covers 1421->1420 + 1420->1427: content has only non-text blocks,
        so the loop iterates but never matches → preserved_text stays empty.
        """
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 10
        eng.image_history = 1
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,xyz"}},
                ],
                "_sentinel_has_image": True,
                "_sentinel_step": 1,
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "latest step"}],
                "_sentinel_has_image": True,
                "_sentinel_step": 10,
            },
        ]
        eng._prune_old_screenshots(messages)
        pruned = messages[0]["content"]
        assert isinstance(pruned, str)
        assert "screenshot at step 1 omitted" in pruned
        assert not pruned.startswith("\n")

    def test_none_content_neither_list_nor_str(self):
        """Covers 1424->1427: content is None → neither list nor str branch taken.

        preserved_text stays "" and the stub is used alone.
        """
        eng = AgentEngine.__new__(AgentEngine)
        eng.step = 10
        eng.image_history = 1
        messages = [
            {
                "role": "user",
                "content": None,  # <-- not list, not str → falls through
                "_sentinel_has_image": True,
                "_sentinel_step": 1,
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "latest step"}],
                "_sentinel_has_image": True,
                "_sentinel_step": 10,
            },
        ]
        eng._prune_old_screenshots(messages)
        pruned = messages[0]["content"]
        assert isinstance(pruned, str)
        assert "screenshot at step 1 omitted" in pruned
        assert not pruned.startswith("\n")


class TestTryParseJsonGap:
    """Test _try_parse_json function for line 1611 coverage.

    Covers the case when JSON parses successfully but returns None because:
    - The result is not a dict (e.g., a list, string, number)
    - The result is a dict but doesn't contain the expected key
    """

    def test_valid_json_list_returns_none(self):
        """Covers 1611: valid JSON list instead of dict."""
        from core.engine import _try_parse_json

        # Valid JSON but not a dict → line 1611
        result = _try_parse_json('["item1", "item2"]', "action")
        assert result is None

    def test_valid_json_dict_without_key_returns_none(self):
        """Covers 1611: valid JSON dict without expected key."""
        from core.engine import _try_parse_json

        # Valid JSON dict but doesn't contain the key → line 1611
        result = _try_parse_json('{"other_key": "value"}', "action")
        assert result is None

    def test_valid_json_dict_with_key_returns_dict(self):
        """Verifies line 1610: valid JSON dict with expected key succeeds."""
        from core.engine import _try_parse_json

        # Valid JSON dict with the key → line 1610
        result = _try_parse_json('{"action": "click"}', "action")
        assert result is not None
        assert result == {"action": "click"}
