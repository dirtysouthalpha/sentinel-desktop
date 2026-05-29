"""Tests for core/engine.py — _check_popup_dismiss and _check_mfa_pause."""

from unittest.mock import MagicMock, patch

from core.engine import AgentEngine


def _make_engine(**overrides):
    """Create a minimal engine for MFA/popup testing."""
    eng = AgentEngine.__new__(AgentEngine)
    eng.step = overrides.get("step", 1)
    eng.running = True
    eng.config = overrides.get("config", {})
    eng.notes = []
    eng._mfa_paused = False
    eng.on_step_callback = overrides.get("on_step_callback", None)

    # Subsystems
    eng.logger = MagicMock()
    eng.mfa_detector = MagicMock()
    eng._popup_handler = MagicMock()
    eng.MFA_POLL_INTERVAL_SECONDS = 0  # instant for tests
    eng.MFA_POLL_ITERATIONS = 3
    eng.POPUP_DISMISS_DELAY = 0  # instant for tests

    return eng


# ---------------------------------------------------------------------------
# _check_popup_dismiss
# ---------------------------------------------------------------------------


class TestCheckPopupDismiss:
    """Tests for AgentEngine._check_popup_dismiss (lines 770-801)."""

    def test_no_popup_detected(self):
        eng = _make_engine()
        eng._popup_handler.check_and_dismiss.return_value = MagicMock(
            detected=False
        )
        with patch("core.screenshot.capture_screen", return_value="screen"):
            eng._check_popup_dismiss()

        eng._popup_handler.check_and_dismiss.assert_called_once()
        eng.logger.log_event.assert_not_called()

    def test_popup_detected_not_dismissed(self):
        eng = _make_engine()
        eng._popup_handler.check_and_dismiss.return_value = MagicMock(
            detected=True,
            popup_type="save_prompt",
            confidence=0.9,
            dismissed=False,
            dismiss_action=None,
        )
        with patch("core.screenshot.capture_screen", return_value="screen"):
            with patch("core.engine.time"):
                eng._check_popup_dismiss()

        eng.logger.log_event.assert_called_once()
        call_args = eng.logger.log_event.call_args
        assert call_args[0][0] == "popup_detected"
        assert call_args[0][1]["type"] == "save_prompt"
        assert call_args[0][1]["dismissed"] is False

    def test_popup_detected_and_dismissed(self):
        eng = _make_engine()
        eng._popup_handler.check_and_dismiss.return_value = MagicMock(
            detected=True,
            popup_type="error_dialog",
            confidence=0.95,
            dismissed=True,
            dismiss_action="clicked_ok",
        )
        with patch("core.screenshot.capture_screen", return_value="screen"):
            with patch("core.engine.time") as mock_time:
                eng._check_popup_dismiss()

        # Should sleep for dismiss delay
        mock_time.sleep.assert_called_once_with(eng.POPUP_DISMISS_DELAY)
        eng.logger.log_event.assert_called_once()
        event_data = eng.logger.log_event.call_args[0][1]
        assert event_data["dismissed"] is True
        # Key in the actual code is "action" not "dismiss_action"
        assert event_data["action"] == "clicked_ok"

    def test_screenshot_failure_is_handled(self):
        eng = _make_engine()
        with patch("core.screenshot.capture_screen", side_effect=OSError("no screen")):
            # Should not raise
            eng._check_popup_dismiss()

        eng._popup_handler.check_and_dismiss.assert_not_called()

    def test_popup_handler_exception_is_handled(self):
        eng = _make_engine()
        eng._popup_handler.check_and_dismiss.side_effect = RuntimeError("crash")
        with patch("core.screenshot.capture_screen", return_value="screen"):
            # Should not raise — caught by broad except
            eng._check_popup_dismiss()

    def test_passes_screenshot_to_handler(self):
        eng = _make_engine()
        eng._popup_handler.check_and_dismiss.return_value = MagicMock(detected=False)
        with patch("core.screenshot.capture_screen", return_value="fake_image"):
            eng._check_popup_dismiss()

        call_kwargs = eng._popup_handler.check_and_dismiss.call_args
        assert call_kwargs[1]["screenshot"] == "fake_image"


# ---------------------------------------------------------------------------
# _check_mfa_pause
# ---------------------------------------------------------------------------


class TestCheckMfaPause:
    """Tests for AgentEngine._check_mfa_pause (lines 718-768)."""

    def test_no_mfa_detected(self):
        eng = _make_engine()
        eng.mfa_detector.check_window_titles.return_value = MagicMock(detected=False)
        with patch("core.screenshot.capture_screen") as mock_cs:
            mock_cs.return_value = None
            eng.mfa_detector.check_screen.return_value = MagicMock(detected=False)
            eng._check_mfa_pause()

        assert eng._mfa_paused is False
        eng.logger.log_event.assert_not_called()

    def test_mfa_detected_from_window_titles(self):
        eng = _make_engine()
        mfa_result = MagicMock(
            detected=True,
            type="uac",
            prompt_text="Do you want to allow this app?",
            window_title="User Account Control",
        )
        # Side effect: initial call returns mfa_result, recheck returns not detected
        eng.mfa_detector.check_window_titles.side_effect = [
            mfa_result,                   # initial check
            MagicMock(detected=False),     # recheck — clears
        ]

        with patch("core.engine.time") as mock_time:
            mock_time.sleep = MagicMock()
            eng._check_mfa_pause()

        assert eng._mfa_paused is False  # cleared after recheck
        # Actual code uses "prompt" and "window" keys
        eng.logger.log_event.assert_any_call("mfa_pause", {
            "type": "uac",
            "prompt": "Do you want to allow this app?",
            "window": "User Account Control",
        })
        eng.logger.log_event.assert_any_call("mfa_resume", {"msg": "Auth prompt dismissed"})

    def test_mfa_detected_from_screenshot_fallback(self):
        eng = _make_engine()
        mfa_screen_result = MagicMock(
            detected=True,
            type="mfa",
            prompt_text="Enter your authenticator code",
            window_title=None,
        )
        # Window titles: initial returns not detected, recheck clears
        eng.mfa_detector.check_window_titles.side_effect = [
            MagicMock(detected=False),  # initial check — no MFA in titles
            MagicMock(detected=False),  # recheck — clears
        ]
        eng.mfa_detector.check_screen.return_value = mfa_screen_result

        with patch("core.engine.time") as mock_time:
            mock_time.sleep = MagicMock()
            with patch("core.screenshot.capture_screen", return_value="screen"):
                eng._check_mfa_pause()

        eng.logger.log_event.assert_any_call("mfa_pause", {
            "type": "mfa",
            "prompt": "Enter your authenticator code",
            "window": None,
        })

    def test_mfa_screenshot_failure_falls_through(self):
        eng = _make_engine()
        eng.mfa_detector.check_window_titles.side_effect = [
            MagicMock(detected=False),  # initial check
        ]
        with patch("core.screenshot.capture_screen", side_effect=OSError("no capture")):
            eng._check_mfa_pause()

        # Should not detect MFA, no pause
        assert eng._mfa_paused is False

    def test_mfa_sets_paused_flag(self):
        eng = _make_engine()
        mfa_result = MagicMock(
            detected=True, type="mfa", prompt_text="code", window_title="Auth",
        )
        # Initial detected, then all rechecks stay detected (user hasn't dismissed)
        eng.mfa_detector.check_window_titles.side_effect = [
            mfa_result,       # initial check
            mfa_result,       # recheck 1
            mfa_result,       # recheck 2
            mfa_result,       # recheck 3
        ]

        with patch("core.engine.time") as mock_time:
            mock_time.sleep = MagicMock()
            eng._check_mfa_pause()

        # After exhausting all 3 retries, _mfa_paused stays True
        assert eng._mfa_paused is True

    def test_mfa_stops_polling_if_not_running(self):
        eng = _make_engine()
        mfa_result = MagicMock(
            detected=True, type="uac", prompt_text="allow?", window_title="UAC",
        )
        call_count = 0

        def fake_sleep(_):
            nonlocal call_count
            call_count += 1
            eng.running = False  # simulate stop

        eng.mfa_detector.check_window_titles.side_effect = [
            mfa_result,                   # initial check
            MagicMock(detected=True),     # recheck (won't get here due to running=False)
        ]

        with patch("core.engine.time") as mock_time:
            mock_time.sleep = fake_sleep
            eng._check_mfa_pause()

        # Should have broken out after first sleep sets running=False
        assert call_count == 1

    def test_mfa_step_callback_called(self):
        callback = MagicMock()
        eng = _make_engine(on_step_callback=callback)
        mfa_result = MagicMock(
            detected=True, type="mfa", prompt_text="Enter code", window_title="Auth",
        )
        eng.mfa_detector.check_window_titles.side_effect = [
            mfa_result,                   # initial check
            MagicMock(detected=False),     # recheck — clears
        ]

        with patch("core.engine.time") as mock_time:
            mock_time.sleep = MagicMock()
            eng._check_mfa_pause()

        callback.assert_called_once()
        call_kwargs = callback.call_args[1]
        assert call_kwargs["action"]["action"] == "mfa_pause"
        assert "MFA" in call_kwargs["result"]["msg"]

    def test_mfa_step_callback_failure_handled(self):
        callback = MagicMock(side_effect=RuntimeError("GUI gone"))
        eng = _make_engine(on_step_callback=callback)
        mfa_result = MagicMock(
            detected=True, type="mfa", prompt_text="code", window_title="Auth",
        )
        eng.mfa_detector.check_window_titles.side_effect = [
            mfa_result,                   # initial check
            MagicMock(detected=False),     # recheck
        ]

        with patch("core.engine.time") as mock_time:
            mock_time.sleep = MagicMock()
            # Should not raise
            eng._check_mfa_pause()

    def test_mfa_no_step_callback_when_none(self):
        eng = _make_engine(on_step_callback=None)
        mfa_result = MagicMock(
            detected=True, type="mfa", prompt_text="code", window_title="Auth",
        )
        eng.mfa_detector.check_window_titles.side_effect = [
            mfa_result,                   # initial check
            MagicMock(detected=False),     # recheck
        ]

        with patch("core.engine.time") as mock_time:
            mock_time.sleep = MagicMock()
            # Should not raise (no callback to call)
            eng._check_mfa_pause()

        assert eng._mfa_paused is False
