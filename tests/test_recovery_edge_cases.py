"""Edge-case tests for core/recovery.py — failure pattern matching and recovery strategies."""

import pytest

from core.recovery import (
    RecoveryEngine,
    RecoverySuggestion,
    _match_pattern,
    _recover_click_failed,
    _recover_element_not_found,
    _recover_input_failed,
    _recover_timeout,
    _recover_window_not_found,
)


class TestMatchPattern:
    def test_element_not_found_patterns(self):
        for msg in [
            "element not found on screen",
            "text not found",
            "could not find the button",
            "window not located at coords",
        ]:
            assert _match_pattern(msg) == "element_not_found"

    def test_permission_denied_patterns(self):
        for msg in [
            "permission denied",
            "access denied",
            "Access is Denied",
            "unauthorized request",
        ]:
            assert _match_pattern(msg) == "permission_denied"

    def test_timeout_patterns(self):
        for msg in [
            "operation timed out",
            "connection timeout",
            "deadline exceeded",
        ]:
            assert _match_pattern(msg) == "timeout"

    def test_ocr_low_confidence_patterns(self):
        for msg in [
            "OCR returned low confidence",
            "low_confidence result",
            "OCR failed completely",
            "text garbled",
            "output was junk",
        ]:
            assert _match_pattern(msg) == "ocr_low_confidence"

    def test_case_insensitive(self):
        assert _match_pattern("ELEMENT NOT FOUND") == "element_not_found"
        assert _match_pattern("Permission Denied") == "permission_denied"

    def test_no_match_returns_none(self):
        assert _match_pattern("some random error xyzzy") is None
        assert _match_pattern("") is None

    def test_empty_string(self):
        assert _match_pattern("") is None

    def test_first_match_wins(self):
        """When multiple patterns could match, the first registered wins."""
        # "window not found" contains "not found" which matches element_not_found first
        # Actually element_not_found is registered before window_not_found
        result = _match_pattern("window not found")
        assert result == "window_not_found"


class TestRecoverySuggestion:
    def test_is_deterministic(self):
        assert RecoverySuggestion("retry_same").is_deterministic is True
        assert RecoverySuggestion("skip").is_deterministic is True
        assert RecoverySuggestion("abort").is_deterministic is True

    def test_is_not_deterministic(self):
        assert RecoverySuggestion("retry_alternate").is_deterministic is False

    def test_default_values(self):
        s = RecoverySuggestion(strategy="abort")
        assert s.alternate_action is None
        assert s.recovery_prompt == ""
        assert s.confidence == 0.0
        assert s.pattern == ""


class TestRecoveryEngineAnalyzeFailure:
    def setup_method(self):
        self.engine = RecoveryEngine()

    def test_element_not_found(self):
        action = {"action": "click_text", "text": "Submit"}
        result = self.engine.analyze_failure(action, "element not found")
        assert result.pattern == "element_not_found"
        assert result.strategy == "retry_alternate"
        assert result.confidence == 0.6

    def test_permission_denied(self):
        action = {"action": "write_file"}
        result = self.engine.analyze_failure(action, "permission denied")
        assert result.pattern == "permission_denied"
        assert result.strategy == "retry_alternate"

    def test_timeout(self):
        action = {"action": "wait", "duration": 5.0}
        result = self.engine.analyze_failure(action, "operation timed out")
        assert result.pattern == "timeout"
        assert result.strategy == "retry_same"
        # Duration should have doubled
        assert result.alternate_action["duration"] == 10.0

    def test_timeout_caps_at_15(self):
        action = {"action": "wait", "duration": 10.0}
        result = self.engine.analyze_failure(action, "timed out")
        # 10 * 2 = 20, but capped at 15
        assert result.alternate_action["duration"] == 15.0

    def test_ocr_low_confidence(self):
        action = {"action": "read_text"}
        result = self.engine.analyze_failure(action, "OCR returned low confidence")
        assert result.pattern == "ocr_low_confidence"
        assert result.confidence == 0.7

    def test_app_not_found(self):
        action = {"action": "open_app", "name": "firefox"}
        result = self.engine.analyze_failure(action, "app not found")
        assert result.pattern == "app_not_found"
        assert result.alternate_action["action"] == "smart_open"

    def test_click_failed(self):
        action = {"action": "click", "x": 100, "y": 200}
        result = self.engine.analyze_failure(action, "click failed")
        assert result.pattern == "click_failed"
        assert result.strategy == "retry_same"

    def test_input_failed_with_text(self):
        action = {"action": "type_text", "text": "Hello World"}
        result = self.engine.analyze_failure(action, "type_keys failed")
        assert result.pattern == "input_failed"
        assert result.alternate_action["action"] == "hotkey"
        assert result.alternate_action["keys"] == "ctrl+v"

    def test_input_failed_without_text(self):
        action = {"action": "type_text", "text": ""}
        result = self.engine.analyze_failure(action, "keyboard error")
        assert result.pattern == "input_failed"
        assert result.alternate_action is None

    def test_generic_fallback(self):
        action = {"action": "click"}
        result = self.engine.analyze_failure(action, "xyzzy unknown error 12345")
        assert result.pattern == "generic"
        assert result.strategy == "retry_same"
        assert result.confidence == 0.3

    def test_exception_object_input(self):
        """analyze_failure accepts Exception objects, not just strings."""
        action = {"action": "click"}
        exc = ValueError("window not found in list")
        result = self.engine.analyze_failure(action, exc)
        assert result.pattern == "window_not_found"

    def test_empty_error_message(self):
        action = {"action": "click"}
        result = self.engine.analyze_failure(action, "")
        assert result.pattern == "generic"

    def test_context_passed_through(self):
        action = {"action": "click", "x": 10}
        context = {"step": 5, "consecutive_failures": 3}
        result = self.engine.analyze_failure(action, "timeout", context)
        assert result.pattern == "timeout"

    def test_unknown_action_type_in_timeout(self):
        """Timeout with an action lacking duration/wait keys."""
        action = {"action": "click"}
        result = self.engine.analyze_failure(action, "timeout")
        assert result.pattern == "timeout"
        # Should still produce an alternate action (just a copy)
        assert result.alternate_action is not None


class TestRecoveryEngineShouldAutoApply:
    def setup_method(self):
        self.engine = RecoveryEngine()

    def test_auto_apply_high_confidence_deterministic(self):
        suggestion = RecoverySuggestion(strategy="retry_same", confidence=0.8)
        assert self.engine.should_auto_apply(suggestion) is True

    def test_no_auto_apply_low_confidence(self):
        suggestion = RecoverySuggestion(strategy="retry_same", confidence=0.5)
        assert self.engine.should_auto_apply(suggestion) is False

    def test_no_auto_apply_non_deterministic(self):
        suggestion = RecoverySuggestion(strategy="retry_alternate", confidence=0.9)
        assert self.engine.should_auto_apply(suggestion) is False

    def test_boundary_threshold(self):
        """Exactly at threshold (0.7) should NOT apply (must exceed)."""
        suggestion = RecoverySuggestion(strategy="retry_same", confidence=0.7)
        assert self.engine.should_auto_apply(suggestion) is False

    def test_just_above_threshold(self):
        suggestion = RecoverySuggestion(strategy="retry_same", confidence=0.71)
        assert self.engine.should_auto_apply(suggestion) is True


class TestRecoverHandlers:
    def test_element_not_found_with_click_text(self):
        action = {"action": "click_text", "text": "OK"}
        result = _recover_element_not_found(action, "text not found", {})
        assert result.alternate_action["action"] == "type_text"
        assert result.alternate_action["text"] == "OK"

    def test_element_not_found_with_plain_click(self):
        action = {"action": "click", "x": 100}
        result = _recover_element_not_found(action, "element not found", {})
        assert result.alternate_action is None
        assert "list_controls" in result.recovery_prompt

    def test_window_not_found_suggests_alt_tab(self):
        action = {"action": "focus_window"}
        result = _recover_window_not_found(action, "window not found", {})
        assert result.alternate_action["action"] == "hotkey"
        assert result.alternate_action["keys"] == ["alt", "tab"]

    def test_timeout_with_wait_key(self):
        action = {"action": "smart_wait", "wait": 3.0}
        result = _recover_timeout(action, "timed out", {})
        assert result.alternate_action["wait"] == 6.0

    def test_timeout_with_duration_key(self):
        action = {"action": "drag", "duration": 2.0}
        result = _recover_timeout(action, "timeout", {})
        assert result.alternate_action["duration"] == 4.0

    def test_click_failed_generic(self):
        action = {"action": "click", "x": 50, "y": 50}
        result = _recover_click_failed(action, "click failed at coordinate", {})
        assert result.strategy == "retry_same"
        assert result.alternate_action is None

    def test_input_failed_with_multiline_text(self):
        action = {"action": "type_text", "text": "Line 1\nLine 2"}
        result = _recover_input_failed(action, "send_keys failed", {})
        assert result.alternate_action is not None
