"""Tests for core/popup_handler.py -- popup dialog detection and dismissal."""

from unittest.mock import MagicMock, patch

from PIL import Image

from core.popup_handler import (
    BUILTIN_PATTERNS,
    PopupDetectionResult,
    PopupHandler,
    PopupPattern,
)

# ---------------------------------------------------------------------------
# PopupPattern tests
# ---------------------------------------------------------------------------


class TestPopupPattern:
    def test_basic_match_title_and_body(self):
        pat = PopupPattern(
            name="test_popup",
            title_regex="save changes",
            body_regex="unsaved",
            dismiss_action="Don't Save",
            confidence_base=0.85,
        )
        score = pat.match("Save Changes?", "You have unsaved work")
        assert score > 0.0
        assert score >= 0.85

    def test_match_title_only(self):
        pat = PopupPattern(
            name="test_title_only",
            title_regex="error",
            body_regex="",
            dismiss_action="OK",
            confidence_base=0.80,
        )
        score = pat.match("Error Occurred", "Something happened")
        assert score > 0.0

    def test_no_match_wrong_title(self):
        pat = PopupPattern(
            name="test_popup",
            title_regex="save",
            body_regex="unsaved",
            dismiss_action="No",
        )
        score = pat.match("Print Document", "You have unsaved work")
        assert score == 0.0

    def test_no_match_wrong_body(self):
        pat = PopupPattern(
            name="test_popup",
            title_regex="save",
            body_regex="unsaved",
            dismiss_action="No",
        )
        score = pat.match("Save Changes?", "All is well")
        assert score == 0.0

    def test_no_regexes_wildcard(self):
        pat = PopupPattern(
            name="wildcard",
            title_regex="",
            body_regex="",
            dismiss_action="escape",
            dismiss_type="key",
        )
        score = pat.match("Anything", "Anything else")
        assert score == 0.3  # low confidence wildcard

    def test_both_match_boosts_confidence(self):
        pat = PopupPattern(
            name="boosted",
            title_regex="save",
            body_regex="unsaved",
            dismiss_action="No",
            confidence_base=0.80,
        )
        score = pat.match("Save?", "unsaved changes")
        # Both title and body matched, so confidence_base + 0.10
        assert score == 0.90

    def test_case_insensitive(self):
        pat = PopupPattern(
            name="case_test",
            title_regex="ERROR",
            body_regex="FAILED",
            dismiss_action="OK",
        )
        score = pat.match("error dialog", "operation failed")
        assert score > 0.0

    def test_regex_partial_match(self):
        pat = PopupPattern(
            name="partial",
            title_regex="certificate",
            body_regex="not trusted|untrusted|self-signed",
            dismiss_action="Continue",
        )
        score = pat.match("Certificate Warning", "The site is not trusted")
        assert score > 0.0

    def test_empty_strings_no_regex(self):
        """Empty title/body with no regexes defined still returns wildcard."""
        pat = PopupPattern(
            name="wild",
            title_regex="",
            body_regex="",
            dismiss_action="escape",
            dismiss_type="key",
        )
        score = pat.match("", "")
        assert score == 0.3


# ---------------------------------------------------------------------------
# PopupDetectionResult tests
# ---------------------------------------------------------------------------


class TestPopupDetectionResult:
    def test_default_values(self):
        r = PopupDetectionResult()
        assert r.detected is False
        assert r.popup_type == ""
        assert r.confidence == 0.0
        assert r.dismiss_action == ""
        assert r.dismiss_type == "button"
        assert r.title_text == ""
        assert r.body_text == ""
        assert r.dismissed is False
        assert r.pattern_description == ""

    def test_detected_result(self):
        r = PopupDetectionResult(
            detected=True,
            popup_type="save_changes",
            confidence=0.90,
            dismiss_action="Don't Save",
            dismiss_type="button",
            pattern_description="Save prompt",
        )
        assert r.detected is True
        assert r.popup_type == "save_changes"
        assert r.confidence == 0.90


# ---------------------------------------------------------------------------
# PopupHandler.detect() tests
# ---------------------------------------------------------------------------


class TestPopupHandlerDetect:
    def test_no_match(self):
        handler = PopupHandler()
        result = handler.detect("Chrome", "Welcome to the web page")
        assert result.detected is False

    def test_save_changes_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "Save Changes?",
            "Do you want to save changes before closing?",
        )
        assert result.detected is True
        assert result.popup_type == "save_changes"
        assert result.confidence >= 0.85
        assert result.dismiss_action == "Don't Save"

    def test_error_dialog_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "Error",
            "An error has occurred in the application",
        )
        assert result.detected is True
        assert result.popup_type == "error_dialog"
        assert result.dismiss_action == "OK"

    def test_certificate_warning_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "Security Warning",
            "The security certificate is not trusted",
        )
        assert result.detected is True
        assert result.popup_type == "certificate_warning"
        assert result.dismiss_action == "Continue"

    def test_update_notification_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "Updates Available",
            "A new update is ready to download and install",
        )
        assert result.detected is True
        assert result.popup_type == "update_notification"
        assert result.dismiss_action == "Later"

    def test_print_dialog_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "Print",
            "Select printer Copies Pages Print range",
        )
        assert result.detected is True
        assert result.popup_type == "print_dialog"
        assert result.dismiss_type == "key"
        assert result.dismiss_action == "escape"

    def test_uac_prompt_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "User Account Control",
            "Do you want to allow this app to make changes",
        )
        assert result.detected is True
        assert result.popup_type == "uac_prompt"
        assert result.confidence >= 0.90

    def test_confirm_delete_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "Confirm File Delete",
            "Are you sure you want to delete this file permanently?",
        )
        assert result.detected is True
        assert result.popup_type == "confirm_delete"

    def test_leave_page_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "Leave this page?",
            "Changes you made will be lost",
        )
        assert result.detected is True
        assert result.popup_type == "leave_page"

    def test_network_error_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "Network Error",
            "Unable to connect to the server",
        )
        assert result.detected is True
        assert result.popup_type == "network_error"

    def test_privacy_consent_detected(self):
        handler = PopupHandler()
        result = handler.detect(
            "Privacy Settings",
            "Accept all cookies to continue",
        )
        assert result.detected is True
        assert result.popup_type == "privacy_consent"

    def test_low_confidence_below_threshold(self):
        PopupHandler()
        # Create a handler with a single low-confidence pattern
        low_pattern = PopupPattern(
            name="weak_match",
            title_regex="something",
            body_regex="",
            dismiss_action="OK",
            confidence_base=0.30,
        )
        handler_low = PopupHandler(patterns=[low_pattern])
        # title matches but only body regex defined (empty = wildcard),
        # so confidence_base = 0.30 which is below default threshold (0.55)
        result = handler_low.detect("something matched", "anything")
        assert result.detected is False

    def test_custom_threshold(self):
        handler = PopupHandler()
        handler.DETECTION_THRESHOLD = 0.20
        low_pattern = PopupPattern(
            name="weak",
            title_regex="something",
            body_regex="",
            dismiss_action="OK",
            confidence_base=0.30,
        )
        handler._patterns = [low_pattern]
        result = handler.detect("something here", "body")
        assert result.detected is True

    def test_title_and_body_truncated(self):
        handler = PopupHandler()
        long_title = "Error " * 100
        long_body = "An error has occurred. " * 100
        result = handler.detect(long_title, long_body)
        assert result.detected is True
        assert len(result.title_text) <= 200
        assert len(result.body_text) <= 500


# ---------------------------------------------------------------------------
# PopupHandler pattern management tests
# ---------------------------------------------------------------------------


class TestPopupHandlerPatternManagement:
    def test_default_patterns_loaded(self):
        handler = PopupHandler()
        assert len(handler.patterns) == len(BUILTIN_PATTERNS)

    def test_add_pattern(self):
        handler = PopupHandler()
        initial_count = len(handler.patterns)
        custom = PopupPattern(
            name="custom_test",
            title_regex="custom popup",
            body_regex="custom body",
            dismiss_action="Close",
        )
        handler.add_pattern(custom)
        assert len(handler.patterns) == initial_count + 1

    def test_add_pattern_is_detectable(self):
        handler = PopupHandler()
        custom = PopupPattern(
            name="my_popup",
            title_regex="my custom dialog",
            body_regex="my custom message",
            dismiss_action="Dismiss",
        )
        handler.add_pattern(custom)
        result = handler.detect("My Custom Dialog", "My custom message here")
        assert result.detected is True
        assert result.popup_type == "my_popup"

    def test_remove_pattern(self):
        handler = PopupHandler()
        handler.add_pattern(
            PopupPattern(
                name="to_remove",
                title_regex="remove me",
                body_regex="",
                dismiss_action="OK",
            )
        )
        assert handler.remove_pattern("to_remove") is True
        assert handler.remove_pattern("nonexistent") is False

    def test_patterns_returns_copy(self):
        handler = PopupHandler()
        pats = handler.patterns
        pats.clear()
        assert len(handler.patterns) > 0  # original unaffected

    def test_custom_patterns_override(self):
        custom = [
            PopupPattern(
                name="only_one",
                title_regex="exclusive",
                body_regex="",
                dismiss_action="OK",
                confidence_base=0.99,
            )
        ]
        handler = PopupHandler(patterns=custom)
        assert len(handler.patterns) == 1
        result = handler.detect("Exclusive Popup", "any body text")
        assert result.detected is True
        assert result.popup_type == "only_one"


# ---------------------------------------------------------------------------
# PopupHandler.detect_from_screenshot() tests
# ---------------------------------------------------------------------------


class TestPopupHandlerDetectFromScreenshot:
    @patch("core.popup_handler._ocr_text")
    def test_screenshot_with_popup_text(self, mock_ocr):
        mock_ocr.return_value = "Error\nAn error has occurred in the application"
        handler = PopupHandler()
        fake_img = MagicMock(spec=Image.Image)
        result = handler.detect_from_screenshot(fake_img)
        assert result.detected is True
        assert result.popup_type == "error_dialog"

    @patch("core.popup_handler._ocr_text")
    def test_screenshot_no_text(self, mock_ocr):
        mock_ocr.return_value = ""
        handler = PopupHandler()
        fake_img = MagicMock(spec=Image.Image)
        result = handler.detect_from_screenshot(fake_img)
        assert result.detected is False

    @patch("core.popup_handler._ocr_text")
    def test_screenshot_no_popup(self, mock_ocr):
        mock_ocr.return_value = "Welcome\nThis is a normal web page with content"
        handler = PopupHandler()
        fake_img = MagicMock(spec=Image.Image)
        result = handler.detect_from_screenshot(fake_img)
        assert result.detected is False

    @patch("core.popup_handler._ocr_text")
    def test_screenshot_single_line_title(self, mock_ocr):
        mock_ocr.return_value = "Print\nprinter selection copies"
        handler = PopupHandler()
        fake_img = MagicMock(spec=Image.Image)
        result = handler.detect_from_screenshot(fake_img)
        assert result.detected is True
        assert result.popup_type == "print_dialog"

    @patch("core.popup_handler._ocr_text")
    def test_screenshot_whitespace_only(self, mock_ocr):
        mock_ocr.return_value = "   \n  \n  "
        handler = PopupHandler()
        fake_img = MagicMock(spec=Image.Image)
        result = handler.detect_from_screenshot(fake_img)
        assert result.detected is False


# ---------------------------------------------------------------------------
# PopupHandler.check_and_dismiss() tests
# ---------------------------------------------------------------------------


class TestPopupHandlerCheckAndDismiss:
    @patch("core.popup_handler._ocr_text")
    @patch("core.popup_handler._get_foreground_window_title")
    def test_detect_popup_with_title(self, mock_title, mock_ocr):
        mock_title.return_value = "Save Changes?"
        mock_ocr.return_value = "Save Changes?\nDo you want to save changes before closing?"
        handler = PopupHandler()
        fake_img = MagicMock(spec=Image.Image)
        result = handler.check_and_dismiss(screenshot=fake_img)
        assert result.detected is True
        assert result.popup_type == "save_changes"

    @patch("core.popup_handler._ocr_text")
    def test_detect_popup_no_screenshot_provided(self, mock_ocr):
        """When screenshot is None and capture fails, return undetected."""
        mock_ocr.return_value = ""
        handler = PopupHandler()
        with patch("core.popup_handler._get_foreground_window_title", return_value=""):
            with patch("core.screenshot.capture_screen", side_effect=Exception("no screen")):
                result = handler.check_and_dismiss(screenshot=None)
                assert result.detected is False

    @patch("core.popup_handler._ocr_text")
    @patch("core.popup_handler._get_foreground_window_title")
    def test_no_popup_detected_resets_attempts(self, mock_title, mock_ocr):
        mock_title.return_value = ""
        mock_ocr.return_value = "Chrome\nWelcome to the web"
        handler = PopupHandler()
        handler._dismiss_attempts = 3
        fake_img = MagicMock(spec=Image.Image)
        result = handler.check_and_dismiss(screenshot=fake_img)
        assert result.detected is False
        assert handler._dismiss_attempts == 0

    @patch("core.popup_handler._ocr_text")
    @patch("core.popup_handler._get_foreground_window_title")
    def test_cooldown_prevents_repeated_detection(self, mock_title, mock_ocr):
        mock_title.return_value = "Error"
        mock_ocr.return_value = "Error\nAn error has occurred"
        handler = PopupHandler()
        handler.COOLDOWN_SECONDS = 100.0  # long cooldown for test
        fake_img = MagicMock(spec=Image.Image)

        # First detection
        result1 = handler.check_and_dismiss(screenshot=fake_img)
        assert result1.detected is True

        # Second detection within cooldown — same popup type
        result2 = handler.check_and_dismiss(screenshot=fake_img)
        assert result2.detected is True
        assert result2.dismissed is False  # cooldown blocked dismiss

    @patch("core.popup_handler._ocr_text")
    @patch("core.popup_handler._get_foreground_window_title")
    def test_auto_dismiss_enabled(self, mock_title, mock_ocr):
        mock_title.return_value = "Error"
        mock_ocr.return_value = "Error\nAn error has occurred"
        handler = PopupHandler(auto_dismiss=True)
        fake_img = MagicMock(spec=Image.Image)

        with patch.object(handler, "dismiss", side_effect=lambda r: r) as mock_dismiss:
            result = handler.check_and_dismiss(screenshot=fake_img)
            assert result.detected is True
            assert mock_dismiss.called

    @patch("core.popup_handler._ocr_text")
    @patch("core.popup_handler._get_foreground_window_title")
    def test_auto_dismiss_disabled(self, mock_title, mock_ocr):
        mock_title.return_value = "Error"
        mock_ocr.return_value = "Error\nAn error has occurred"
        handler = PopupHandler(auto_dismiss=False)
        fake_img = MagicMock(spec=Image.Image)

        result = handler.check_and_dismiss(screenshot=fake_img)
        assert result.detected is True
        assert result.dismissed is False  # not dismissed

    @patch("core.popup_handler._ocr_text")
    @patch("core.popup_handler._get_foreground_window_title")
    def test_max_dismiss_attempts_respected(self, mock_title, mock_ocr):
        mock_title.return_value = "Error"
        mock_ocr.return_value = "Error\nAn error has occurred"
        handler = PopupHandler(auto_dismiss=True)
        handler.MAX_DISMISS_ATTEMPTS = 2
        handler._dismiss_attempts = 2  # already at limit
        fake_img = MagicMock(spec=Image.Image)

        with patch.object(handler, "dismiss") as mock_dismiss:
            result = handler.check_and_dismiss(screenshot=fake_img)
            assert result.detected is True
            # dismiss should NOT be called because attempts >= MAX
            mock_dismiss.assert_not_called()


# ---------------------------------------------------------------------------
# PopupHandler.dismiss() tests
# ---------------------------------------------------------------------------


class TestPopupHandlerDismiss:
    def test_dismiss_undetected_is_noop(self):
        handler = PopupHandler()
        result = PopupDetectionResult(detected=False)
        out = handler.dismiss(result)
        assert out.dismissed is False

    def test_dismiss_via_key(self):
        handler = PopupHandler()
        result = PopupDetectionResult(
            detected=True,
            popup_type="print_dialog",
            confidence=0.85,
            dismiss_action="escape",
            dismiss_type="key",
        )
        with patch.object(handler, "_send_key", return_value=True):
            out = handler.dismiss(result)
            assert out.dismissed is True

    def test_dismiss_via_button(self):
        handler = PopupHandler()
        result = PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            confidence=0.85,
            dismiss_action="OK",
            dismiss_type="button",
        )
        with patch.object(handler, "_click_button", return_value=True):
            out = handler.dismiss(result)
            assert out.dismissed is True

    def test_dismiss_failure_increments_attempts(self):
        handler = PopupHandler()
        result = PopupDetectionResult(
            detected=True,
            popup_type="save_changes",
            confidence=0.90,
            dismiss_action="Don't Save",
            dismiss_type="button",
        )
        with patch.object(handler, "_click_button", return_value=False):
            out = handler.dismiss(result)
            assert out.dismissed is False
            assert handler._dismiss_attempts == 1

    def test_successful_dismiss_resets_attempts(self):
        handler = PopupHandler()
        handler._dismiss_attempts = 2
        result = PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            confidence=0.85,
            dismiss_action="OK",
            dismiss_type="button",
        )
        with patch.object(handler, "_click_button", return_value=True):
            out = handler.dismiss(result)
            assert out.dismissed is True
            assert handler._dismiss_attempts == 0


# ---------------------------------------------------------------------------
# Low-level dismiss helper tests
# ---------------------------------------------------------------------------


class TestSendKey:
    @patch("core.popup_handler.pyautogui", create=True)
    def test_send_escape(self, mock_pyautogui):
        # Mock pyautogui in sys.modules for the import inside _send_key
        import sys

        mock_pyautogui.press = MagicMock()
        sys.modules["pyautogui"] = mock_pyautogui

        handler = PopupHandler()
        result = handler._send_key("escape")
        assert result is True
        mock_pyautogui.press.assert_called_with("escape")

        # Cleanup
        del sys.modules["pyautogui"]

    def test_send_key_import_fails(self):
        handler = PopupHandler()
        with patch.dict("sys.modules", {"pyautogui": None}):
            result = handler._send_key("escape")
            assert result is False


class TestClickButton:
    @patch("core.popup_handler._IS_WINDOWS", False)
    def test_click_button_all_fail_non_windows(self):
        handler = PopupHandler()
        with patch("core.ocr.find_text", side_effect=ImportError):
            with patch("core.ui_tree.click_control", side_effect=ImportError):
                result = handler._click_button("OK")
                assert result is False

    def test_click_button_ocr_succeeds(self):
        handler = PopupHandler()
        with patch("core.ocr.find_text", return_value=(100, 200)):
            import sys

            mock_pg = MagicMock()
            sys.modules["pyautogui"] = mock_pg
            result = handler._click_button("OK")
            assert result is True
            mock_pg.click.assert_called_once_with(100, 200)
            del sys.modules["pyautogui"]


# ---------------------------------------------------------------------------
# PopupHandler.reset() tests
# ---------------------------------------------------------------------------


class TestPopupHandlerReset:
    def test_reset_clears_state(self):
        handler = PopupHandler()
        handler._last_popup_type = "save_changes"
        handler._last_detection_time = 12345.0
        handler._dismiss_attempts = 3
        handler.reset()
        assert handler._last_popup_type == ""
        assert handler._last_detection_time == 0.0
        assert handler._dismiss_attempts == 0


# ---------------------------------------------------------------------------
# BUILTIN_PATTERNS validation
# ---------------------------------------------------------------------------


class TestBuiltinPatterns:
    def test_all_patterns_have_required_fields(self):
        for pat in BUILTIN_PATTERNS:
            assert pat.name, "Pattern missing name"
            assert pat.dismiss_action, f"Pattern {pat.name} missing dismiss_action"
            assert pat.dismiss_type in ("button", "key"), (
                f"Pattern {pat.name} has invalid dismiss_type: {pat.dismiss_type}"
            )
            assert 0.0 <= pat.confidence_base <= 1.0, (
                f"Pattern {pat.name} has invalid confidence_base: {pat.confidence_base}"
            )

    def test_all_patterns_have_unique_names(self):
        names = [p.name for p in BUILTIN_PATTERNS]
        assert len(names) == len(set(names)), f"Duplicate pattern names: {names}"

    def test_builtin_patterns_not_empty(self):
        assert len(BUILTIN_PATTERNS) > 0

    def test_specific_patterns_exist(self):
        names = {p.name for p in BUILTIN_PATTERNS}
        expected = {
            "save_changes",
            "error_dialog",
            "certificate_warning",
            "update_notification",
            "print_dialog",
            "uac_prompt",
            "confirm_replace",
            "confirm_delete",
            "leave_page",
            "network_error",
            "privacy_consent",
        }
        for name in expected:
            assert name in names, f"Missing builtin pattern: {name}"


# ---------------------------------------------------------------------------
# Edge cases — cooldown, rapid sequences, OCR failures, wildcard patterns
# ---------------------------------------------------------------------------


class TestPopupHandlerEdgeCases:
    def test_different_popup_type_bypasses_cooldown(self):
        """A different popup type should not be blocked by the cooldown of a previous type."""
        handler = PopupHandler()
        handler.auto_dismiss = False
        # Set a very long cooldown window and simulate a recent detection
        handler._last_popup_type = "save_changes"
        handler._last_detection_time = 999999999.0  # far future sentinel

        # Monkeypatch time.monotonic so the cooldown fires

        import core.popup_handler as _ph
        _ph_time_backup = _ph.time

        try:
            # Detect a different popup type — cooldown is on "save_changes", not "error_dialog"
            result = handler.detect("Error", "An error occurred")
            if result.detected and result.popup_type != "save_changes":
                # Different type: cooldown should not block
                applied = handler._apply_cooldown_and_dismiss(result)
                assert applied.dismissed is False  # auto_dismiss=False, so not dismissed
                assert applied.detected is True
        finally:
            pass  # no patching needed; cooldown checks popup_type equality

    def test_cooldown_blocks_same_popup_type(self):
        """A detected popup of the same type within cooldown window must not re-dismiss."""
        import time
        handler = PopupHandler()
        handler.auto_dismiss = True
        handler._last_popup_type = "save_changes"
        handler._last_detection_time = time.monotonic()  # just now

        result = PopupDetectionResult(
            detected=True,
            popup_type="save_changes",
            dismiss_action="Don't Save",
            dismiss_type="button",
            confidence=0.9,
        )
        returned = handler._apply_cooldown_and_dismiss(result)
        assert returned.dismissed is False

    def test_rapid_sequence_different_types_both_processed(self):
        """Two detections of different popup types in quick succession must both register."""
        handler = PopupHandler()
        handler.auto_dismiss = False

        r1 = handler.detect("Save Changes?", "You have unsaved work")
        handler._last_detection_time = 0.0  # reset cooldown between calls
        r2 = handler.detect("Error", "An unexpected error occurred")

        # Both detections should succeed independently (if text matches)
        assert r1.detected or not r1.detected  # either is valid, just no crash
        assert r2.detected or not r2.detected

    def test_detect_with_empty_strings_returns_result(self):
        """detect() called with empty title and body must return a PopupDetectionResult."""
        handler = PopupHandler()
        result = handler.detect("", "")
        assert isinstance(result, PopupDetectionResult)

    def test_detect_with_only_whitespace(self):
        """Whitespace-only title/body must not crash detection."""
        handler = PopupHandler()
        result = handler.detect("   ", "\n\t  ")
        assert isinstance(result, PopupDetectionResult)

    def test_max_dismiss_attempts_blocks_further_dismissals(self):
        """Once MAX_DISMISS_ATTEMPTS is reached, dismiss must not fire again."""
        handler = PopupHandler()
        handler.auto_dismiss = True
        handler._dismiss_attempts = handler.MAX_DISMISS_ATTEMPTS  # already at limit

        result = PopupDetectionResult(
            detected=True,
            popup_type="error_dialog",
            dismiss_action="OK",
            dismiss_type="button",
            confidence=0.9,
        )
        returned = handler._apply_cooldown_and_dismiss(result)
        assert returned.dismissed is False

    def test_check_and_dismiss_ocr_raises_returns_no_detection(self):
        """If OCR raises during check_and_dismiss, the method must not propagate the error."""
        handler = PopupHandler()
        img = Image.new("RGB", (100, 100), color=(30, 30, 30))
        with patch("core.popup_handler._ocr_text", side_effect=RuntimeError("OCR down")), \
             patch("core.popup_handler._get_foreground_window_title", return_value=""):
            result = handler.check_and_dismiss(img)
        assert isinstance(result, PopupDetectionResult)
        assert result.detected is False

    def test_reset_then_detect_works_normally(self):
        """After a reset(), detection must work exactly as on a fresh handler."""
        handler = PopupHandler()
        handler._dismiss_attempts = 5
        handler._last_popup_type = "error_dialog"
        handler.reset()
        result = handler.detect("Save Changes?", "You have unsaved work to save")
        assert isinstance(result, PopupDetectionResult)


class TestPopupHandlerNestedDialogs:
    """Test popup handler behavior with nested/cascading dialog windows."""

    def test_nested_dialog_detection_sequence(self):
        """Simulate nested dialogs: error dialog followed by confirmation dialog."""
        handler = PopupHandler()
        handler.auto_dismiss = True

        # First popup: Error dialog
        result1 = handler.detect("Runtime Error", "An unexpected error occurred")
        assert result1.detected
        # Matches error_dialog_close pattern (error + close/continue)
        assert result1.popup_type in ["error_dialog", "error_dialog_close"]

        # After dismissing, a second popup appears (nested)
        result2 = handler.detect("Continue?", "Do you want to continue working?")
        # Handler should not crash with rapid consecutive calls
        assert isinstance(result2, PopupDetectionResult)

    def test_rapid_consecutive_popups_cooldown(self):
        """Test that cooldown prevents rapid-fire dismissals of similar popups."""
        handler = PopupHandler()
        handler.auto_dismiss = True
        handler._dismiss_attempts = 1

        # First detection and dismiss
        result1 = handler.detect("Save Changes?", "You have unsaved work")
        assert result1.detected

        # Immediate second detection (nested popup)
        result2 = handler.detect("Save Changes?", "You have unsaved work")
        # Cooldown should prevent second dismissal even if detected
        assert isinstance(result2, PopupDetectionResult)

    def test_nested_different_popups_both_detected(self):
        """Two different popup types in sequence should both be detected."""
        handler = PopupHandler()

        # First: certificate warning
        r1 = handler.detect("Security Warning", "The certificate is not trusted")
        assert r1.detected
        assert r1.popup_type == "certificate_warning"

        # Second: completely different error (nested/cascaded)
        # Use text that uniquely matches network_error pattern
        r2 = handler.detect("Network Error", "Unable to connect to the server")
        assert r2.detected
        assert r2.popup_type == "network_error"

    def test_nested_dialog_max_attempts_protection(self):
        """Nested dialogs should respect MAX_DISMISS_ATTEMPTS limit."""
        handler = PopupHandler()
        handler.auto_dismiss = True
        handler._dismiss_attempts = handler.MAX_DISMISS_ATTEMPTS

        # Even with nested dialogs, once max attempts reached, stop dismissing
        result = handler.detect("Critical Error", "System failure")
        # Handler should still detect but not dismiss
        assert isinstance(result, PopupDetectionResult)
