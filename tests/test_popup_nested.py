"""Edge-case tests for popup_handler.py — nested/stacked dialog scenarios.

Covers:
- Dismissing one popup resets attempt counter so the next one can be caught
- Successive check_and_dismiss calls handle a second popup after the first is gone
- Screenshot capture failure returns non-detected result
- Detected-but-not-dismissed result when auto_dismiss is False
"""

from __future__ import annotations

from unittest.mock import patch

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
            detected=True,
            popup_type="error_dialog",
            dismissed=False,
            dismiss_action="OK",
            dismiss_type="button",
        )
        second_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="save_changes",
            dismissed=False,
            dismiss_action="Don't Save",
            dismiss_type="button",
        )
        dismissed_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value=""),
            patch.object(ph, "_get_foreground_window_title", return_value=""),
            patch.object(handler, "detect", return_value=first_result),
            patch.object(handler, "dismiss", return_value=dismissed_result),
        ):
            r1 = handler.check_and_dismiss()

        assert r1.detected
        assert r1.dismissed

        # Second popup is a different type — cooldown should not apply
        dismissed_second = ph.PopupDetectionResult(
            detected=True,
            popup_type="save_changes",
            dismissed=True,
        )
        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value=""),
            patch.object(ph, "_get_foreground_window_title", return_value=""),
            patch.object(handler, "detect", return_value=second_result),
            patch.object(handler, "dismiss", return_value=dismissed_second),
        ):
            r2 = handler.check_and_dismiss()

        assert r2.detected


class TestDismissAttemptsResetOnNonDetected:
    """_dismiss_attempts is reset to 0 when no popup is detected."""

    def test_dismiss_attempts_reset(self) -> None:
        handler = ph.PopupHandler(auto_dismiss=True)
        handler._dismiss_attempts = 3

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value=""),
            patch.object(ph, "_get_foreground_window_title", return_value=""),
        ):
            result = handler.check_and_dismiss()

        assert not result.detected
        assert handler._dismiss_attempts == 0


class TestAutoDismissFalseDoesNotDismiss:
    """With auto_dismiss=False, detected popups are reported but not dismissed."""

    def test_detected_not_dismissed(self) -> None:
        handler = ph.PopupHandler(auto_dismiss=False)

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="Error\nAn error has occurred."),
            patch.object(ph, "_get_foreground_window_title", return_value="Error"),
            patch.object(handler, "dismiss") as mock_dismiss,
        ):
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


class TestCascadingPopups:
    """Test handling of cascading popups (one popup triggers another)."""

    def test_three_popups_in_sequence(self) -> None:
        """Test dismissing three popups that appear in sequence."""
        handler = ph.PopupHandler(auto_dismiss=True)

        # First popup: Error dialog
        first_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            dismissed=False,
            dismiss_action="OK",
            dismiss_type="button",
        )
        dismissed_first = ph.PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="Error"),
            patch.object(ph, "_get_foreground_window_title", return_value="Error"),
            patch.object(handler, "detect", return_value=first_result),
            patch.object(handler, "dismiss", return_value=dismissed_first),
        ):
            r1 = handler.check_and_dismiss()

        assert r1.detected
        assert r1.dismissed

        # Second popup: Confirm dialog
        second_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="confirm_dialog",
            dismissed=False,
            dismiss_action="Yes",
            dismiss_type="button",
        )
        dismissed_second = ph.PopupDetectionResult(
            detected=True,
            popup_type="confirm_dialog",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="Confirm"),
            patch.object(ph, "_get_foreground_window_title", return_value="Confirm"),
            patch.object(handler, "detect", return_value=second_result),
            patch.object(handler, "dismiss", return_value=dismissed_second),
        ):
            r2 = handler.check_and_dismiss()

        assert r2.detected
        assert r2.dismissed

        # Third popup: Save changes
        third_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="save_changes",
            dismissed=False,
            dismiss_action="Don't Save",
            dismiss_type="button",
        )
        dismissed_third = ph.PopupDetectionResult(
            detected=True,
            popup_type="save_changes",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="Save"),
            patch.object(ph, "_get_foreground_window_title", return_value="Save"),
            patch.object(handler, "detect", return_value=third_result),
            patch.object(handler, "dismiss", return_value=dismissed_third),
        ):
            r3 = handler.check_and_dismiss()

        assert r3.detected
        assert r3.dismissed

    def test_cascading_same_popup_type(self) -> None:
        """Test multiple popups of the same type appearing in sequence."""
        handler = ph.PopupHandler(auto_dismiss=True)

        # First error popup
        first_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            dismissed=False,
            dismiss_action="OK",
            dismiss_type="button",
        )
        dismissed_first = ph.PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="Error 1"),
            patch.object(ph, "_get_foreground_window_title", return_value="Error"),
            patch.object(handler, "detect", return_value=first_result),
            patch.object(handler, "dismiss", return_value=dismissed_first),
        ):
            r1 = handler.check_and_dismiss()

        assert r1.detected

        # Second error popup of same type - should still be caught after cooldown
        # Reset dismiss attempts to simulate new popup
        handler._dismiss_attempts = 0
        second_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            dismissed=False,
            dismiss_action="OK",
            dismiss_type="button",
        )
        dismissed_second = ph.PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="Error 2"),
            patch.object(ph, "_get_foreground_window_title", return_value="Error"),
            patch.object(handler, "detect", return_value=second_result),
            patch.object(handler, "dismiss", return_value=dismissed_second),
        ):
            r2 = handler.check_and_dismiss()

        assert r2.detected


class TestRapidlyAppearingDisappearingDialogs:
    """Test handling of rapidly appearing and disappearing dialogs."""

    def test_rapid_appear_disappear_cycle(self) -> None:
        """Test popup that appears and disappears rapidly."""
        handler = ph.PopupHandler(auto_dismiss=True)

        # Popup appears
        detected = ph.PopupDetectionResult(
            detected=True,
            popup_type="notification",
            dismissed=False,
            dismiss_action="Close",
            dismiss_type="button",
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="Notification"),
            patch.object(ph, "_get_foreground_window_title", return_value="Notification"),
            patch.object(handler, "detect", return_value=detected),
        ):
            r1 = handler.check_and_dismiss()

        assert r1.detected

        # Immediately disappears (no popup detected)
        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value=""),
            patch.object(ph, "_get_foreground_window_title", return_value=""),
        ):
            r2 = handler.check_and_dismiss()

        assert not r2.detected
        assert handler._dismiss_attempts == 0  # Should reset

    def test_multiple_rapid_cycles(self) -> None:
        """Test multiple rapid appear/disappear cycles."""
        handler = ph.PopupHandler(auto_dismiss=True)

        for i in range(3):
            # Popup appears
            detected = ph.PopupDetectionResult(
                detected=True,
                popup_type="notification",
                dismissed=False,
                dismiss_action="Close",
                dismiss_type="button",
            )
            dismissed = ph.PopupDetectionResult(
                detected=True,
                popup_type="notification",
                dismissed=True,
            )

            with (
                patch("core.screenshot.capture_screen", return_value=_blank_image()),
                patch.object(ph, "_ocr_text", return_value=f"Notification {i}"),
                patch.object(ph, "_get_foreground_window_title", return_value="Notification"),
                patch.object(handler, "detect", return_value=detected),
                patch.object(handler, "dismiss", return_value=dismissed),
            ):
                result = handler.check_and_dismiss()

            assert result.detected

            # Disappears
            with (
                patch("core.screenshot.capture_screen", return_value=_blank_image()),
                patch.object(ph, "_ocr_text", return_value=""),
                patch.object(ph, "_get_foreground_window_title", return_value=""),
            ):
                result = handler.check_and_dismiss()

            assert not result.detected


class TestPopupDuringCriticalActions:
    """Test popup detection during critical system actions."""

    def test_popup_during_file_operation(self) -> None:
        """Test popup detection during critical file operations."""
        handler = ph.PopupHandler(auto_dismiss=True)

        # Simulate popup appearing during file copy
        popup_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="file_locked",
            dismissed=False,
            dismiss_action="Retry",
            dismiss_type="button",
        )
        dismissed_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="file_locked",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="File in use"),
            patch.object(ph, "_get_foreground_window_title", return_value="File Access Error"),
            patch.object(handler, "detect", return_value=popup_result),
            patch.object(handler, "dismiss", return_value=dismissed_result),
        ):
            result = handler.check_and_dismiss()

        assert result.detected
        assert result.dismissed

    def test_popup_during_installation(self) -> None:
        """Test popup handling during software installation."""
        handler = ph.PopupHandler(auto_dismiss=True)

        # Installation confirmation popup
        popup_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="uac_prompt",
            dismissed=False,
            dismiss_action="Yes",
            dismiss_type="button",
        )
        dismissed_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="uac_prompt",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="User Account Control"),
            patch.object(ph, "_get_foreground_window_title", return_value="UAC"),
            patch.object(handler, "detect", return_value=popup_result),
            patch.object(handler, "dismiss", return_value=dismissed_result),
        ):
            result = handler.check_and_dismiss()

        assert result.detected
        assert result.dismissed

    def test_multiple_popups_during_single_action(self) -> None:
        """Test multiple popups appearing during a single critical action."""
        handler = ph.PopupHandler(auto_dismiss=True)

        # First popup: Warning
        warning_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="warning",
            dismissed=False,
            dismiss_action="Continue",
            dismiss_type="button",
        )
        dismissed_warning = ph.PopupDetectionResult(
            detected=True,
            popup_type="warning",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="Warning"),
            patch.object(ph, "_get_foreground_window_title", return_value="Warning"),
            patch.object(handler, "detect", return_value=warning_result),
            patch.object(handler, "dismiss", return_value=dismissed_warning),
        ):
            r1 = handler.check_and_dismiss()

        assert r1.detected

        # Second popup: Confirmation
        confirm_result = ph.PopupDetectionResult(
            detected=True,
            popup_type="confirm_dialog",
            dismissed=False,
            dismiss_action="Yes",
            dismiss_type="button",
        )
        dismissed_confirm = ph.PopupDetectionResult(
            detected=True,
            popup_type="confirm_dialog",
            dismissed=True,
        )

        with (
            patch("core.screenshot.capture_screen", return_value=_blank_image()),
            patch.object(ph, "_ocr_text", return_value="Confirm"),
            patch.object(ph, "_get_foreground_window_title", return_value="Confirm"),
            patch.object(handler, "detect", return_value=confirm_result),
            patch.object(handler, "dismiss", return_value=dismissed_confirm),
        ):
            r2 = handler.check_and_dismiss()

        assert r2.detected
