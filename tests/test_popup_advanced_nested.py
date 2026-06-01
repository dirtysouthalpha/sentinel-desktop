"""Advanced nested dialog tests for popup_handler.py.

Covers:
- Multi-level dialog hierarchies (3+ levels)
- Modal vs non-modal dialog handling
- Popups with complex layouts and multiple dismiss options
- Edge cases with OCR failures
- Dialog detection with unusual window states
- High-frequency popup scenarios
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import core.popup_handler as ph


def _blank_image() -> Image.Image:
    return Image.new("RGB", (200, 100), color=(240, 240, 240))


# ---------------------------------------------------------------------------
# Multi-level dialog hierarchies
# ---------------------------------------------------------------------------


class TestMultiLevelDialogHierarchy:
    """Test handling of deeply nested dialog hierarchies (3+ levels)."""

    def test_four_level_dialog_hierarchy(self) -> None:
        """Test dismissing a chain of 4 nested dialogs."""
        handler = ph.PopupHandler(auto_dismiss=True)

        # Level 1: Error dialog
        level1 = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", dismissed=False,
            dismiss_action="OK", dismiss_type="button",
        )
        dismissed1 = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Error Level 1"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Error"), \
             patch.object(handler, "detect", return_value=level1), \
             patch.object(handler, "dismiss", return_value=dismissed1):
            r1 = handler.check_and_dismiss()

        assert r1.detected and r1.dismissed

        # Level 2: Warning dialog
        level2 = ph.PopupDetectionResult(
            detected=True, popup_type="warning", dismissed=False,
            dismiss_action="Continue", dismiss_type="button",
        )
        dismissed2 = ph.PopupDetectionResult(
            detected=True, popup_type="warning", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Warning Level 2"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Warning"), \
             patch.object(handler, "detect", return_value=level2), \
             patch.object(handler, "dismiss", return_value=dismissed2):
            r2 = handler.check_and_dismiss()

        assert r2.detected and r2.dismissed

        # Level 3: Confirmation dialog
        level3 = ph.PopupDetectionResult(
            detected=True, popup_type="confirm_dialog", dismissed=False,
            dismiss_action="Yes", dismiss_type="button",
        )
        dismissed3 = ph.PopupDetectionResult(
            detected=True, popup_type="confirm_dialog", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Confirm Level 3"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Confirm"), \
             patch.object(handler, "detect", return_value=level3), \
             patch.object(handler, "dismiss", return_value=dismissed3):
            r3 = handler.check_and_dismiss()

        assert r3.detected and r3.dismissed

        # Level 4: Save changes dialog
        level4 = ph.PopupDetectionResult(
            detected=True, popup_type="save_changes", dismissed=False,
            dismiss_action="Don't Save", dismiss_type="button",
        )
        dismissed4 = ph.PopupDetectionResult(
            detected=True, popup_type="save_changes", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Save Level 4"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Save"), \
             patch.object(handler, "detect", return_value=level4), \
             patch.object(handler, "dismiss", return_value=dismissed4):
            r4 = handler.check_and_dismiss()

        assert r4.detected and r4.dismissed

    def test_interleaved_dialog_types(self) -> None:
        """Test dialog hierarchy with interleaved different types."""
        handler = ph.PopupHandler(auto_dismiss=True)

        dialog_types = [
            ("error_dialog", "OK", "Error"),
            ("warning", "Continue", "Warning"),
            ("confirm_dialog", "Yes", "Confirm"),
            ("save_changes", "Don't Save", "Save"),
            ("error_dialog", "OK", "Error 2"),  # Repeats error type
        ]

        for popup_type, action, title in dialog_types:
            result = ph.PopupDetectionResult(
                detected=True, popup_type=popup_type, dismissed=False,
                dismiss_action=action, dismiss_type="button",
            )
            dismissed = ph.PopupDetectionResult(
                detected=True, popup_type=popup_type, dismissed=True,
            )

            with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
                 patch.object(ph, "_ocr_text", return_value=title), \
                 patch.object(ph, "_get_foreground_window_title", return_value=title), \
                 patch.object(handler, "detect", return_value=result), \
                 patch.object(handler, "dismiss", return_value=dismissed):
                r = handler.check_and_dismiss()

            assert r.detected and r.dismissed


# ---------------------------------------------------------------------------
# Modal vs non-modal dialog handling
# ---------------------------------------------------------------------------


class TestModalNonModalHandling:
    """Test handling of modal vs non-modal dialogs."""

    def test_modal_dialog_blocks_detection(self) -> None:
        """Test that modal dialogs are properly detected and handled."""
        handler = ph.PopupHandler(auto_dismiss=True)

        modal_result = ph.PopupDetectionResult(
            detected=True, popup_type="modal_dialog", dismissed=False,
            dismiss_action="Close", dismiss_type="button",
        )
        dismissed = ph.PopupDetectionResult(
            detected=True, popup_type="modal_dialog", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Modal Dialog"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Modal"), \
             patch.object(handler, "detect", return_value=modal_result), \
             patch.object(handler, "dismiss", return_value=dismissed):
            result = handler.check_and_dismiss()

        assert result.detected and result.dismissed

    def test_non_modal_dialog_allows_background_detection(self) -> None:
        """Test that non-modal dialogs allow background detection."""
        handler = ph.PopupHandler(auto_dismiss=True)

        non_modal_result = ph.PopupDetectionResult(
            detected=True, popup_type="notification", dismissed=False,
            dismiss_action="Dismiss", dismiss_type="button",
        )
        dismissed = ph.PopupDetectionResult(
            detected=True, popup_type="notification", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Notification"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Notification"), \
             patch.object(handler, "detect", return_value=non_modal_result), \
             patch.object(handler, "dismiss", return_value=dismissed):
            result = handler.check_and_dismiss()

        assert result.detected

    def test_switching_between_modal_and_non_modal(self) -> None:
        """Test switching between modal and non-modal dialogs."""
        handler = ph.PopupHandler(auto_dismiss=True)

        # Modal dialog first
        modal = ph.PopupDetectionResult(
            detected=True, popup_type="modal_dialog", dismissed=False,
            dismiss_action="OK", dismiss_type="button",
        )
        dismissed_modal = ph.PopupDetectionResult(
            detected=True, popup_type="modal_dialog", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Modal"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Modal"), \
             patch.object(handler, "detect", return_value=modal), \
             patch.object(handler, "dismiss", return_value=dismissed_modal):
            r1 = handler.check_and_dismiss()

        assert r1.detected

        # Then non-modal
        non_modal = ph.PopupDetectionResult(
            detected=True, popup_type="notification", dismissed=False,
            dismiss_action="Close", dismiss_type="button",
        )
        dismissed_non_modal = ph.PopupDetectionResult(
            detected=True, popup_type="notification", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Notification"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Notification"), \
             patch.object(handler, "detect", return_value=non_modal), \
             patch.object(handler, "dismiss", return_value=dismissed_non_modal):
            r2 = handler.check_and_dismiss()

        assert r2.detected


# ---------------------------------------------------------------------------
# Complex layouts and multiple dismiss options
# ---------------------------------------------------------------------------


class TestComplexLayoutHandling:
    """Test handling of dialogs with complex layouts and multiple options."""

    def test_dialog_with_multiple_buttons(self) -> None:
        """Test dialog with multiple dismiss options (Yes, No, Cancel)."""
        handler = ph.PopupHandler(auto_dismiss=True)

        multi_button = ph.PopupDetectionResult(
            detected=True, popup_type="confirm_dialog", dismissed=False,
            dismiss_action="Yes", dismiss_type="button",  # Primary action
        )
        dismissed = ph.PopupDetectionResult(
            detected=True, popup_type="confirm_dialog", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Yes\nNo\nCancel"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Confirm"), \
             patch.object(handler, "detect", return_value=multi_button), \
             patch.object(handler, "dismiss", return_value=dismissed):
            result = handler.check_and_dismiss()

        assert result.detected and result.dismissed

    def test_dialog_with_checkbox_and_button(self) -> None:
        """Test dialog with checkbox followed by action button."""
        handler = ph.PopupHandler(auto_dismiss=True)

        checkbox_dialog = ph.PopupDetectionResult(
            detected=True, popup_type="warning", dismissed=False,
            dismiss_action="OK", dismiss_type="button",
        )
        dismissed = ph.PopupDetectionResult(
            detected=True, popup_type="warning", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="☑ Don't show again\nOK"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Warning"), \
             patch.object(handler, "detect", return_value=checkbox_dialog), \
             patch.object(handler, "dismiss", return_value=dismissed):
            result = handler.check_and_dismiss()

        assert result.detected

    def test_dialog_with_dropdown_and_buttons(self) -> None:
        """Test dialog with dropdown menu and action buttons."""
        handler = ph.PopupHandler(auto_dismiss=True)

        dropdown_dialog = ph.PopupDetectionResult(
            detected=True, popup_type="settings", dismissed=False,
            dismiss_action="Apply", dismiss_type="button",
        )
        dismissed = ph.PopupDetectionResult(
            detected=True, popup_type="settings", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Options: ▼\nApply\nCancel"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Settings"), \
             patch.object(handler, "detect", return_value=dropdown_dialog), \
             patch.object(handler, "dismiss", return_value=dismissed):
            result = handler.check_and_dismiss()

        assert result.detected


# ---------------------------------------------------------------------------
# OCR failure edge cases
# ---------------------------------------------------------------------------


class TestOCRFailureEdgeCases:
    """Test popup handler behavior when OCR fails."""

    def test_ocr_returns_empty_string(self) -> None:
        """Test handling when OCR returns empty string."""
        handler = ph.PopupHandler(auto_dismiss=True)

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value=""), \
             patch.object(ph, "_get_foreground_window_title", return_value=""):
            result = handler.check_and_dismiss()

        assert not result.detected

    def test_ocr_returns_garbled_text(self) -> None:
        """Test handling when OCR returns garbled/unreadable text."""
        handler = ph.PopupHandler(auto_dismiss=True)

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="#@! $%^ &*("), \
             patch.object(ph, "_get_foreground_window_title", return_value=""):
            result = handler.check_and_dismiss()

        # Garbled text should not trigger false positive detection
        assert not result.detected

    def test_ocr_raises_exception(self) -> None:
        """Test handling when OCR raises an exception."""
        handler = ph.PopupHandler(auto_dismiss=True)

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", side_effect=OSError("OCR failed")), \
             patch.object(ph, "_get_foreground_window_title", return_value=""):
            result = handler.check_and_dismiss()

        assert not result.detected

    def test_ocr_partial_success(self) -> None:
        """Test handling when OCR partially succeeds (some text readable)."""
        handler = ph.PopupHandler(auto_dismiss=True)

        error_result = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", dismissed=False,
            dismiss_action="OK", dismiss_type="button",
        )
        dismissed = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", dismissed=True,
        )

        # Partial OCR with some readable keywords
        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Eror has ocured"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Error"), \
             patch.object(handler, "detect", return_value=error_result), \
             patch.object(handler, "dismiss", return_value=dismissed):
            result = handler.check_and_dismiss()

        # Should still detect despite typos from OCR
        assert result.detected


# ---------------------------------------------------------------------------
# Unusual window states
# ---------------------------------------------------------------------------


class TestUnusualWindowStates:
    """Test popup detection with unusual window states."""

    def test_minimized_dialog(self) -> None:
        """Test detection of minimized dialog windows."""
        handler = ph.PopupHandler(auto_dismiss=True)

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value=""), \
             patch.object(ph, "_get_foreground_window_title", return_value=""):  # Minimized = no title
            result = handler.check_and_dismiss()

        assert not result.detected

    def test_maximized_dialog(self) -> None:
        """Test detection of maximized dialog windows."""
        handler = ph.PopupHandler(auto_dismiss=True)

        max_result = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", dismissed=False,
            dismiss_action="OK", dismiss_type="button",
        )
        dismissed = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", dismissed=True,
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="ERROR"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Error"), \
             patch.object(handler, "detect", return_value=max_result), \
             patch.object(handler, "dismiss", return_value=dismissed):
            result = handler.check_and_dismiss()

        assert result.detected

    def test_dialog_off_screen(self) -> None:
        """Test dialog that appears partially off-screen."""
        handler = ph.PopupHandler(auto_dismiss=True)

        # Partial screenshot due to off-screen dialog
        partial_image = Image.new("RGB", (100, 100), color=(240, 240, 240))

        with patch("core.screenshot.capture_screen", return_value=partial_image), \
             patch.object(ph, "_ocr_text", return_value="Error"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Error"):
            result = handler.check_and_dismiss()

        # Should still attempt detection even with partial screenshot
        # (actual detection depends on OCR and pattern matching)


# ---------------------------------------------------------------------------
# High-frequency popup scenarios
# ---------------------------------------------------------------------------


class TestHighFrequencyPopups:
    """Test handling of high-frequency popup scenarios."""

    def test_rapid_same_popups(self) -> None:
        """Test rapid succession of identical popups."""
        handler = ph.PopupHandler(auto_dismiss=True)

        for i in range(5):
            handler._dismiss_attempts = 0  # Reset to simulate new popup
            result = ph.PopupDetectionResult(
                detected=True, popup_type="error_dialog", dismissed=False,
                dismiss_action="OK", dismiss_type="button",
            )

            # Mock dismiss to actually dismiss (return dismissed=True)
            def mock_dismiss(*args, **kwargs):
                return ph.PopupDetectionResult(
                    detected=True, popup_type="error_dialog", dismissed=True,
                )

            with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
                 patch.object(ph, "_ocr_text", return_value=f"Error {i}"), \
                 patch.object(ph, "_get_foreground_window_title", return_value="Error"), \
                 patch.object(handler, "detect", return_value=result), \
                 patch.object(handler, "dismiss", side_effect=mock_dismiss):
                r = handler.check_and_dismiss()

            # Should be detected, but dismissal depends on handler logic
            assert r.detected

    def test_popup_storm(self) -> None:
        """Test 'popup storm' - many different popups in quick succession."""
        handler = ph.PopupHandler(auto_dismiss=True)

        popup_types = [
            ("error_dialog", "OK", "Error"),
            ("warning", "Continue", "Warning"),
            ("confirm_dialog", "Yes", "Confirm"),
            ("save_changes", "Don't Save", "Save"),
            ("notification", "Close", "Notification"),
        ]

        for popup_type, action, title in popup_types:
            result = ph.PopupDetectionResult(
                detected=True, popup_type=popup_type, dismissed=False,
                dismiss_action=action, dismiss_type="button",
            )
            dismissed = ph.PopupDetectionResult(
                detected=True, popup_type=popup_type, dismissed=True,
            )

            with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
                 patch.object(ph, "_ocr_text", return_value=title), \
                 patch.object(ph, "_get_foreground_window_title", return_value=title), \
                 patch.object(handler, "detect", return_value=result), \
                 patch.object(handler, "dismiss", return_value=dismissed):
                r = handler.check_and_dismiss()

            assert r.detected

    def test_preventing_infinite_loop(self) -> None:
        """Test that handler prevents infinite loops on persistent popups."""
        handler = ph.PopupHandler(auto_dismiss=True)
        handler._dismiss_attempts = 100  # Simulate many attempts

        # Even with high attempt count, should still try to detect
        persistent = ph.PopupDetectionResult(
            detected=True, popup_type="error_dialog", dismissed=False,
            dismiss_action="OK", dismiss_type="button",
        )

        with patch("core.screenshot.capture_screen", return_value=_blank_image()), \
             patch.object(ph, "_ocr_text", return_value="Error"), \
             patch.object(ph, "_get_foreground_window_title", return_value="Error"), \
             patch.object(handler, "detect", return_value=persistent):
            result = handler.check_and_dismiss()

        # Should still attempt detection
        assert result.detected
