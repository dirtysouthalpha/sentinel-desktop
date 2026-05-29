"""Edge-case tests for popup_handler.py — nested/stacked dialog scenarios.

Covers:
- Dismissing one popup resets attempt counter so the next one can be caught
- Successive check_and_dismiss calls handle a second popup after the first is gone
- Screenshot capture failure returns non-detected result
- Detected-but-not-dismissed result when auto_dismiss is False
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import core.popup_handler as ph


def _blank_image() -> Image.Image:
    return Image.new("RGB", (200, 100), color=(240, 240, 240))


# ---------------------------------------------------------------------------
# Nested / stacked dialog scenario
# ---------------------------------------------------------------------------


class TestNestedDialogSequence:
    """Simulates dismissing one dialog which then reveals a second one."""

    def test_second_popup_detected_after_first_dismissed(self) -> None:
        handler = ph.PopupHandler(auto_dismiss=True)

        first_result = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", dismissed=False,
            dismiss_action="OK", dismiss_type="button",
        )
        second_result = ph.PopupDetectionResult(
            detected=True, popup_type="save_changes", dismissed=False,
            dismiss_action="Don't Save", dismiss_type="button",
        )
        dismissed_result = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value=""), \
             patch.object(ph, "_get_foreground_window_title", return_value=""), \
             patch.object(handler, "detect", return_value=first_result), \
             patch.object(handler, "dismiss", return_value=dismissed_result):
            r1 = handler.check_and_dismiss()

        assert r1.detected
        assert r1.dismissed

        # Second popup is a different type — cooldown should not apply
        dismissed_second = ph.PopupDetectionResult(
            detected=True, popup_type="save_changes", dismissed=True,
        )
        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value=""), \
             patch.object(ph, "_get_foreground_window_title", return_value=""), \
             patch.object(handler, "detect", return_value=second_result), \
             patch.object(handler, "dismiss", return_value=dismissed_second):
            r2 = handler.check_and_dismiss()

        assert r2.detected


class TestDismissAttemptsResetOnNonDetected:
    """_dismiss_attempts is reset to 0 when no popup is detected."""

    def test_dismiss_attempts_reset(self) -> None:
        handler = ph.PopupHandler(auto_dismiss=True)
        handler._dismiss_attempts = 3

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value=""), \
             patch.object(ph, "_get_foreground_window_title", return_value=""):
            result = handler.check_and_dismiss()

        assert not result.detected
        assert handler._dismiss_attempts == 0


class TestAutoDismissFalseDoesNotDismiss:
    """With auto_dismiss=False, detected popups are reported but not dismissed."""

    def test_detected_not_dismissed(self) -> None:
        handler = ph.PopupHandler(auto_dismiss=False)

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Error\nAn error has occurred."), \
             patch.object(ph, "_get_foreground_window_title", return_value="Error"), \
             patch.object(handler, "dismiss") as mock_dismiss:
            result = handler.check_and_dismiss()

        mock_dismiss.assert_not_called()


class TestScreenshotCaptureFailureReturnsEmpty:
    """If screenshot capture raises, check_and_dismiss returns a non-detected result."""

    def test_screenshot_failure_returns_empty_result(self) -> None:
        handler = ph.PopupHandler(auto_dismiss=True)

        with patch("core.screenshot.capture_screen", side_effect=OSError("screen grab failed")):
            result = handler.check_and_dismiss(screenshot=None)

        assert not result.detected
        assert not result.dismissed
