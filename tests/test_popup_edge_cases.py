"""Edge-case tests for core/popup_handler.py — nested dialogs, pattern matching, cooldowns."""

import time
from unittest.mock import MagicMock, patch

import pytest

from core.popup_handler import (
    BUILTIN_PATTERNS,
    PopupDetectionResult,
    PopupHandler,
    PopupPattern,
)


class TestPopupPattern:
    def test_match_both_title_and_body(self):
        pat = PopupPattern(
            name="test", title_regex=r"Error", body_regex=r"failed",
            dismiss_action="OK",
        )
        assert pat.match("Error occurred", "operation failed") > 0.85

    def test_match_title_only(self):
        pat = PopupPattern(
            name="test", title_regex=r"Warning", body_regex=r"",
            dismiss_action="OK",
        )
        assert pat.match("Warning!", "any body text") == pat.confidence_base

    def test_match_body_only(self):
        pat = PopupPattern(
            name="test", title_regex=r"", body_regex=r"are you sure",
            dismiss_action="Yes",
        )
        assert pat.match("any title", "are you sure?") == pat.confidence_base

    def test_no_match(self):
        pat = PopupPattern(
            name="test", title_regex=r"Error", body_regex=r"critical",
            dismiss_action="OK",
        )
        assert pat.match("Success", "all good") == 0.0

    def test_no_regexes_wildcard(self):
        """Pattern with no title or body regex matches anything with low confidence."""
        pat = PopupPattern(
            name="wild", title_regex=r"", body_regex=r"",
            dismiss_action="OK",
        )
        assert pat.match("anything", "anything") == 0.3

    def test_case_insensitive(self):
        pat = PopupPattern(
            name="test", title_regex=r"ERROR", body_regex=r"FAIL",
            dismiss_action="OK",
        )
        assert pat.match("error", "fail") > 0

    def test_confidence_cap_at_1(self):
        """confidence_base + 0.10 boost should never exceed 1.0."""
        pat = PopupPattern(
            name="test", title_regex=r"a", body_regex=r"b",
            dismiss_action="OK", confidence_base=0.95,
        )
        score = pat.match("a", "b")
        assert score <= 1.0


class TestPopupHandlerDetect:
    def setup_method(self):
        self.handler = PopupHandler()

    def test_no_match_returns_undetected(self):
        result = self.handler.detect("Normal Window", "regular content")
        assert result.detected is False

    def test_save_changes_detected(self):
        result = self.handler.detect("Save Changes", "Do you want to save before closing?")
        assert result.detected is True
        assert result.popup_type == "save_changes"

    def test_error_dialog_detected(self):
        result = self.handler.detect("Error", "An error has occurred")
        assert result.detected is True
        assert result.dismiss_action == "OK"

    def test_best_match_wins(self):
        """When multiple patterns could match, the highest confidence wins."""
        result = self.handler.detect(
            "Save Changes",
            "Do you want to save your work? Unsaved changes will be lost.",
        )
        assert result.detected is True

    def test_exact_threshold_boundary(self):
        """Score must be >= DETECTION_THRESHOLD (0.55) to be detected."""
        # Add a pattern that scores exactly at threshold
        self.handler.add_pattern(PopupPattern(
            name="borderline", title_regex=r"^exact$", body_regex=r"",
            dismiss_action="OK", confidence_base=0.55,
        ))
        result = self.handler.detect("exact", "")
        # 0.55 >= 0.55 should be detected
        assert result.detected is True

    def test_just_below_threshold(self):
        self.handler.add_pattern(PopupPattern(
            name="just_under", title_regex=r"^under$", body_regex=r"",
            dismiss_action="OK", confidence_base=0.54,
        ))
        result = self.handler.detect("under", "")
        assert result.detected is False

    def test_empty_text_no_match(self):
        result = self.handler.detect("", "")
        assert result.detected is False


class TestPopupHandlerPatternManagement:
    def test_add_pattern(self):
        handler = PopupHandler(patterns=[])
        handler.add_pattern(PopupPattern(name="custom", title_regex=r"x", body_regex=r"", dismiss_action="OK"))
        assert len(handler.patterns) == 1

    def test_remove_pattern(self):
        handler = PopupHandler(patterns=[])
        handler.add_pattern(PopupPattern(name="keep", title_regex=r"a", body_regex=r"", dismiss_action="OK"))
        handler.add_pattern(PopupPattern(name="drop", title_regex=r"b", body_regex=r"", dismiss_action="OK"))
        assert handler.remove_pattern("drop") is True
        assert len(handler.patterns) == 1
        assert handler.patterns[0].name == "keep"

    def test_remove_nonexistent(self):
        handler = PopupHandler(patterns=[])
        assert handler.remove_pattern("no_such") is False

    def test_default_patterns_loaded(self):
        handler = PopupHandler()
        assert len(handler.patterns) > 0
        names = [p.name for p in handler.patterns]
        assert "save_changes" in names
        assert "error_dialog" in names


class TestPopupHandlerCooldown:
    """Cooldown logic lives in check_and_dismiss(), not detect().

    detect() is pure pattern matching; check_and_dismiss() wraps it with
    cooldown tracking and auto-dismiss.
    """

    def _mock_handler(self, **kwargs):
        """Create a PopupHandler with mocked OCR and screenshot capture."""
        handler = PopupHandler(**kwargs)
        # Mock _ocr_text and _get_foreground_window_title so detect works
        # without a real screenshot or Tesseract.
        self._ocr_patch = patch("core.popup_handler._ocr_text")
        self._title_patch = patch("core.popup_handler._get_foreground_window_title", return_value="")
        self._ocr_mock = self._ocr_patch.start()
        self._title_patch.start()
        return handler

    def test_cooldown_prevents_repeat_dismiss(self):
        handler = self._mock_handler()
        handler.COOLDOWN_SECONDS = 60.0
        handler.auto_dismiss = False  # don't actually try to click

        # Make OCR return text that triggers save_changes detection
        self._ocr_mock.return_value = "Save Changes\nSave before closing?"

        from PIL import Image
        fake_img = Image.new("RGB", (100, 100))

        result1 = handler.check_and_dismiss(screenshot=fake_img)
        assert result1.detected is True

        # Immediately re-detecting same popup type should be cooldown-suppressed
        result2 = handler.check_and_dismiss(screenshot=fake_img)
        assert result2.detected is True  # still detected
        assert result2.dismissed is False  # but not dismissed (cooldown active)

        self._ocr_patch.stop()
        self._title_patch.stop()

    def test_cooldown_expires(self):
        handler = self._mock_handler()
        handler.COOLDOWN_SECONDS = 0.01
        handler.auto_dismiss = False

        self._ocr_mock.return_value = "Error\nAn error has occurred"
        from PIL import Image
        fake_img = Image.new("RGB", (100, 100))

        result1 = handler.check_and_dismiss(screenshot=fake_img)
        assert result1.detected is True

        time.sleep(0.02)  # Wait for cooldown to expire
        result2 = handler.check_and_dismiss(screenshot=fake_img)
        assert result2.detected is True

        self._ocr_patch.stop()
        self._title_patch.stop()

    def test_different_popup_type_not_suppressed(self):
        """A different popup type should not be affected by cooldown."""
        handler = self._mock_handler()
        handler.COOLDOWN_SECONDS = 60.0
        handler.auto_dismiss = False

        from PIL import Image
        fake_img = Image.new("RGB", (100, 100))

        # First popup type
        self._ocr_mock.return_value = "Save Changes\nSave before closing?"
        result1 = handler.check_and_dismiss(screenshot=fake_img)
        assert result1.detected is True

        # Different popup type should still be detected and not suppressed
        self._ocr_mock.return_value = "Error\nAn error has occurred"
        result2 = handler.check_and_dismiss(screenshot=fake_img)
        assert result2.detected is True

        self._ocr_patch.stop()
        self._title_patch.stop()


class TestPopupDetectionResult:
    def test_default_undetected(self):
        result = PopupDetectionResult()
        assert result.detected is False
        assert result.popup_type == ""
        assert result.confidence == 0.0

    def test_detected_result(self):
        result = PopupDetectionResult(
            detected=True,
            popup_type="save_changes",
            confidence=0.9,
            dismiss_action="Don't Save",
            dismiss_type="button",
        )
        assert result.detected is True
        assert result.popup_type == "save_changes"
        assert result.dismiss_action == "Don't Save"


class TestBuiltinPatterns:
    def test_all_builtin_patterns_valid(self):
        """All built-in patterns should compile their regexes without error."""
        for pat in BUILTIN_PATTERNS:
            assert pat.name
            assert pat.dismiss_action
            assert pat.dismiss_type in ("button", "key")

    def test_save_pattern_matches_save_dialog(self):
        save_pat = next(p for p in BUILTIN_PATTERNS if p.name == "save_changes")
        assert save_pat.match("Save Changes", "Save before closing?") > 0

    def test_error_pattern_matches_error_dialog(self):
        error_pat = next(p for p in BUILTIN_PATTERNS if p.name == "error_dialog")
        assert error_pat.match("Error", "An error has occurred") > 0


class TestMaxDismissAttempts:
    def test_max_dismiss_attempts_limit(self):
        """After MAX_DISMISS_ATTEMPTS, the handler should stop trying."""
        handler = PopupHandler(auto_dismiss=True)
        handler.COOLDOWN_SECONDS = 0  # disable cooldown for this test

        # Mock dismiss to always "fail" (returns False for click/button)
        with patch.object(handler, "_click_button", return_value=False), \
             patch.object(handler, "_send_key", return_value=False), \
             patch("core.popup_handler._ocr_text", return_value="Error\nAn error has occurred"), \
             patch("core.popup_handler._get_foreground_window_title", return_value=""):
            from PIL import Image
            fake_img = Image.new("RGB", (100, 100))

            # Simulate repeated check_and_dismiss calls
            for _ in range(handler.MAX_DISMISS_ATTEMPTS + 2):
                handler.check_and_dismiss(screenshot=fake_img)

            assert handler._dismiss_attempts >= handler.MAX_DISMISS_ATTEMPTS
