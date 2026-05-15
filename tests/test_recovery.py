"""Tests for core.recovery — Self-healing Recovery Engine."""

from __future__ import annotations

import pytest

from core.recovery import (
    RecoveryEngine,
    RecoverySuggestion,
    _match_pattern,
    _compile_patterns,
    _FAILURE_PATTERNS,
    _RECOVERY_HANDLERS,
)


# ---------------------------------------------------------------------------
# RecoverySuggestion dataclass
# ---------------------------------------------------------------------------


class TestRecoverySuggestion:
    def test_is_deterministic_retry_same(self) -> None:
        s = RecoverySuggestion(strategy="retry_same")
        assert s.is_deterministic is True

    def test_is_deterministic_skip(self) -> None:
        s = RecoverySuggestion(strategy="skip")
        assert s.is_deterministic is True

    def test_is_deterministic_abort(self) -> None:
        s = RecoverySuggestion(strategy="abort")
        assert s.is_deterministic is True

    def test_is_deterministic_retry_alternate(self) -> None:
        s = RecoverySuggestion(strategy="retry_alternate")
        assert s.is_deterministic is False

    def test_defaults(self) -> None:
        s = RecoverySuggestion(strategy="retry_same")
        assert s.alternate_action is None
        assert s.recovery_prompt == ""
        assert s.confidence == 0.0
        assert s.pattern == ""


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------


class TestPatternMatching:
    """Test _match_pattern against each registered failure pattern."""

    def test_element_not_found_variants(self) -> None:
        for msg in [
            "element not found",
            "Text not found on screen",
            "Could not find the button",
            "Element not located",
        ]:
            assert _match_pattern(msg) == "element_not_found", msg

    def test_permission_denied_variants(self) -> None:
        for msg in [
            "Permission denied",
            "Access denied to file",
            "Access is denied",
            "Unauthorized access",
        ]:
            assert _match_pattern(msg) == "permission_denied", msg

    def test_window_not_found_variants(self) -> None:
        for msg in [
            "Window not found",
            "No window matching criteria",
        ]:
            assert _match_pattern(msg) == "window_not_found", msg

    def test_window_not_located_matches_element(self) -> None:
        # "not located" is in the element_not_found pattern which is checked first
        assert _match_pattern("Window Chrome not located") == "element_not_found"

    def test_timeout_variants(self) -> None:
        for msg in [
            "Timeout waiting for element",
            "Operation timed out",
            "Deadline exceeded",
        ]:
            assert _match_pattern(msg) == "timeout", msg

    def test_ocr_low_confidence_variants(self) -> None:
        for msg in [
            "OCR low confidence",
            "low_confidence threshold",
            "OCR failed to read",
            "garbled text output",
            "junk result from OCR",
        ]:
            assert _match_pattern(msg) == "ocr_low_confidence", msg

    def test_app_not_found_variants(self) -> None:
        for msg in [
            "App not found",
            "Application not found",
            "Could not launch app",
            "not installed on system",
        ]:
            assert _match_pattern(msg) == "app_not_found", msg

    def test_click_failed_variants(self) -> None:
        for msg in [
            "Click failed at position",
            "Click error on button",
            "Coordinate out of range",
        ]:
            assert _match_pattern(msg) == "click_failed", msg

    def test_input_failed_variants(self) -> None:
        for msg in [
            "Type failed",
            "Keyboard error",
            "send_keys failed",
        ]:
            assert _match_pattern(msg) == "input_failed", msg

    def test_unknown_returns_none(self) -> None:
        assert _match_pattern("something completely unrelated") is None

    def test_empty_string(self) -> None:
        assert _match_pattern("") is None

    def test_case_insensitive(self) -> None:
        assert _match_pattern("TIMEOUT") == "timeout"
        assert _match_pattern("Element NOT FOUND") == "element_not_found"


class TestCompilePatterns:
    def test_compiled_once(self) -> None:
        patterns = _compile_patterns()
        assert len(patterns) == len(_FAILURE_PATTERNS)
        # Each pattern should be a compiled regex
        for pat, name in patterns:
            assert hasattr(pat, "search")
            assert isinstance(name, str)

    def test_pattern_names_match_handlers(self) -> None:
        """Every pattern name should have a corresponding handler."""
        for _, name in _FAILURE_PATTERNS:
            assert name in _RECOVERY_HANDLERS, f"Missing handler for pattern: {name}"


# ---------------------------------------------------------------------------
# Recovery handlers
# ---------------------------------------------------------------------------


class TestRecoveryHandlers:
    """Test each individual recovery handler directly."""

    def test_element_not_found_basic(self) -> None:
        handler = _RECOVERY_HANDLERS["element_not_found"]
        result = handler({"action": "click"}, "element not found", {})
        assert isinstance(result, RecoverySuggestion)
        assert result.strategy == "retry_alternate"
        assert result.confidence == 0.6
        assert result.pattern == "element_not_found"

    def test_element_not_found_click_text(self) -> None:
        handler = _RECOVERY_HANDLERS["element_not_found"]
        result = handler({"action": "click_text", "text": "Submit"}, "text not found", {})
        assert result.alternate_action == {"action": "type_text", "text": "Submit"}

    def test_element_not_found_non_click_text(self) -> None:
        handler = _RECOVERY_HANDLERS["element_not_found"]
        result = handler({"action": "click"}, "not found", {})
        assert result.alternate_action is None

    def test_permission_denied(self) -> None:
        handler = _RECOVERY_HANDLERS["permission_denied"]
        result = handler({}, "permission denied", {})
        assert result.strategy == "retry_alternate"
        assert result.confidence == 0.5
        assert "UAC" in result.recovery_prompt

    def test_window_not_found(self) -> None:
        handler = _RECOVERY_HANDLERS["window_not_found"]
        result = handler({}, "window not found", {})
        assert result.strategy == "retry_alternate"
        assert result.alternate_action == {"action": "hotkey", "keys": "alt+tab"}

    def test_timeout_with_duration(self) -> None:
        handler = _RECOVERY_HANDLERS["timeout"]
        action = {"action": "wait", "duration": 2.0}
        result = handler(action, "timeout", {})
        assert result.strategy == "retry_same"
        assert result.alternate_action["duration"] == 4.0

    def test_timeout_with_wait(self) -> None:
        handler = _RECOVERY_HANDLERS["timeout"]
        action = {"action": "smart_wait", "wait": 3.0}
        result = handler(action, "timeout", {})
        assert result.alternate_action["wait"] == 6.0

    def test_timeout_capped_at_15(self) -> None:
        handler = _RECOVERY_HANDLERS["timeout"]
        action = {"action": "wait", "duration": 10.0}
        result = handler(action, "timeout", {})
        assert result.alternate_action["duration"] == 15.0

    def test_ocr_low_confidence(self) -> None:
        handler = _RECOVERY_HANDLERS["ocr_low_confidence"]
        result = handler({}, "OCR low confidence", {})
        assert result.strategy == "retry_alternate"
        assert result.confidence == 0.7
        assert "list_controls" in result.recovery_prompt

    def test_app_not_found(self) -> None:
        handler = _RECOVERY_HANDLERS["app_not_found"]
        result = handler({"action": "open_app", "app": "Chrome"}, "app not found", {})
        assert result.strategy == "retry_alternate"
        assert result.alternate_action == {"action": "smart_open", "query": "Chrome"}

    def test_app_not_found_with_name(self) -> None:
        handler = _RECOVERY_HANDLERS["app_not_found"]
        result = handler({"action": "launch", "name": "Firefox"}, "not found", {})
        assert result.alternate_action == {"action": "smart_open", "query": "Firefox"}

    def test_app_not_found_with_path(self) -> None:
        handler = _RECOVERY_HANDLERS["app_not_found"]
        result = handler({"action": "start", "path": "C:\\app.exe"}, "not found", {})
        assert result.alternate_action == {"action": "smart_open", "query": "C:\\app.exe"}

    def test_click_failed(self) -> None:
        handler = _RECOVERY_HANDLERS["click_failed"]
        result = handler({}, "click failed", {})
        assert result.strategy == "retry_same"
        assert result.confidence == 0.55

    def test_input_failed_with_text(self) -> None:
        handler = _RECOVERY_HANDLERS["input_failed"]
        result = handler({"action": "type_text", "text": "hello"}, "type failed", {})
        assert result.strategy == "retry_alternate"
        assert result.alternate_action == {"action": "hotkey", "keys": "ctrl+v"}
        assert "Ctrl+V" in result.recovery_prompt

    def test_input_failed_without_text(self) -> None:
        handler = _RECOVERY_HANDLERS["input_failed"]
        result = handler({"action": "press_key"}, "keyboard error", {})
        assert result.alternate_action is None


# ---------------------------------------------------------------------------
# RecoveryEngine
# ---------------------------------------------------------------------------


class TestRecoveryEngine:
    def setup_method(self) -> None:
        self.engine = RecoveryEngine()

    def test_analyze_failure_element_not_found(self) -> None:
        suggestion = self.engine.analyze_failure(
            {"action": "click"}, "element not found on screen"
        )
        assert suggestion.pattern == "element_not_found"
        assert suggestion.confidence > 0

    def test_analyze_failure_with_exception(self) -> None:
        suggestion = self.engine.analyze_failure(
            {"action": "click"}, RuntimeError("element not found")
        )
        assert suggestion.pattern == "element_not_found"

    def test_analyze_failure_unknown_returns_generic(self) -> None:
        suggestion = self.engine.analyze_failure(
            {"action": "custom_action"}, "something bizarre happened"
        )
        assert suggestion.pattern == "generic"
        assert suggestion.strategy == "retry_same"
        assert suggestion.confidence == 0.3

    def test_analyze_failure_with_context(self) -> None:
        suggestion = self.engine.analyze_failure(
            {"action": "click"}, "timeout", context={"step": 5}
        )
        assert suggestion.pattern == "timeout"

    def test_analyze_failure_empty_context(self) -> None:
        suggestion = self.engine.analyze_failure(
            {"action": "click"}, "timeout", context=None
        )
        assert suggestion.pattern == "timeout"

    def test_should_auto_apply_high_confidence_deterministic(self) -> None:
        s = RecoverySuggestion(strategy="retry_same", confidence=0.8)
        assert self.engine.should_auto_apply(s) is True

    def test_should_auto_apply_low_confidence(self) -> None:
        s = RecoverySuggestion(strategy="retry_same", confidence=0.5)
        assert self.engine.should_auto_apply(s) is False

    def test_should_auto_apply_nondeterministic(self) -> None:
        s = RecoverySuggestion(strategy="retry_alternate", confidence=0.9)
        assert self.engine.should_auto_apply(s) is False

    def test_should_auto_apply_exact_threshold(self) -> None:
        s = RecoverySuggestion(strategy="retry_same", confidence=0.7)
        # Threshold is 0.7, confidence must be > 0.7
        assert self.engine.should_auto_apply(s) is False

    def test_should_auto_apply_skip(self) -> None:
        s = RecoverySuggestion(strategy="skip", confidence=0.8)
        assert self.engine.should_auto_apply(s) is True

    def test_should_auto_apply_abort(self) -> None:
        s = RecoverySuggestion(strategy="abort", confidence=0.9)
        assert self.engine.should_auto_apply(s) is True

    def test_generic_suggestion_includes_action_name(self) -> None:
        suggestion = self.engine.analyze_failure(
            {"action": "my_special_action"}, "weird error xyz"
        )
        assert "my_special_action" in suggestion.recovery_prompt

    def test_generic_suggestion_truncates_long_error(self) -> None:
        long_error = "x" * 500
        suggestion = self.engine.analyze_failure(
            {"action": "test"}, long_error
        )
        assert len(suggestion.recovery_prompt) < 500


# ---------------------------------------------------------------------------
# Integration: each failure pattern round-trips through the engine
# ---------------------------------------------------------------------------


class TestEnginePatternIntegration:
    """Ensure every registered pattern can be triggered through the engine."""

    ENGINE = RecoveryEngine()

    @pytest.mark.parametrize(
        "error_msg,expected_pattern",
        [
            ("element not found", "element_not_found"),
            ("permission denied", "permission_denied"),
            ("window not found", "window_not_found"),
            ("timeout waiting", "timeout"),
            ("OCR low confidence", "ocr_low_confidence"),
            ("app not found", "app_not_found"),
            ("click failed", "click_failed"),
            ("type failed", "input_failed"),
        ],
    )
    def test_pattern_round_trip(self, error_msg: str, expected_pattern: str) -> None:
        suggestion = self.ENGINE.analyze_failure({"action": "test"}, error_msg)
        assert suggestion.pattern == expected_pattern
        assert suggestion.confidence > 0
        assert suggestion.strategy in (
            "retry_same",
            "retry_alternate",
            "skip",
            "abort",
        )
