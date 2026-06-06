"""Advanced failure scenario tests for core/recovery.py.

Covers:
- Cascading failures (when recovery actions themselves would fail)
- Context corruption and edge cases
- Extreme input values and resource pressure
- Thread safety in pattern matching
- Recovery suggestion edge cases
"""

from __future__ import annotations

import threading
import time

import pytest

from core.recovery import (
    _RECOVERY_HANDLERS,
    RecoveryEngine,
    RecoverySuggestion,
    _match_pattern,
)

# ---------------------------------------------------------------------------
# Cascading failure scenarios
# ---------------------------------------------------------------------------


class TestCascadingFailures:
    """Test scenarios where recovery actions themselves would fail."""

    def test_recovery_action_with_invalid_coords(self):
        """Test recovery suggestion for click failure with out-of-range coordinates."""
        engine = RecoveryEngine()
        action = {"action": "click", "x": -9999, "y": -9999}
        error = "click failed: coordinate out of range"
        suggestion = engine.analyze_failure(action, error, {})
        # Should still provide a suggestion despite bad coordinates
        assert suggestion is not None
        assert suggestion.pattern == "click_failed"

    def test_recovery_with_malformed_alternate_action(self):
        """Test that alternate_action is always valid even with bad input."""
        engine = RecoveryEngine()
        # Test with timeout handler that creates alternate action
        action = {"action": "wait", "duration": "invalid"}  # Invalid duration
        error = "timeout occurred"
        suggestion = engine.analyze_failure(action, error, {})
        # Should still provide a valid suggestion
        assert suggestion is not None
        assert suggestion.pattern == "timeout"

    def test_recovery_suggestion_for_ocr_failure_with_no_text(self):
        """Test OCR recovery when there's literally no text to work with."""
        engine = RecoveryEngine()
        action = {"action": "click", "text": ""}  # Empty text
        error = "element not found:  (blank search)"
        suggestion = engine.analyze_failure(action, error, {})
        # Should still provide a strategy
        assert suggestion is not None
        assert suggestion.strategy in ("retry_alternate", "retry_same", "skip")


# ---------------------------------------------------------------------------
# Context corruption and edge cases
# ---------------------------------------------------------------------------


class TestContextEdgeCases:
    """Test recovery engine with corrupted or unusual context data."""

    def test_context_with_circular_reference(self):
        """Test that circular references in context don't cause crashes."""
        engine = RecoveryEngine()
        # Create context with circular reference
        context = {}
        context["self"] = context
        action = {"action": "click"}
        error = "element not found"
        # Should handle circular reference gracefully
        suggestion = engine.analyze_failure(action, error, context)
        assert suggestion is not None

    def test_context_with_unicode_error_messages(self):
        """Test recovery engine handles unicode characters in error messages."""
        engine = RecoveryEngine()
        action = {"action": "type"}
        # Use unicode characters that might cause encoding issues
        error = "element not found: 按钮🔍搜索🚫"
        suggestion = engine.analyze_failure(action, error, {})
        assert suggestion is not None
        assert suggestion.pattern == "element_not_found"

    def test_context_with_extremely_large_dict(self):
        """Test recovery engine with very large context dict."""
        engine = RecoveryEngine()
        # Create a massive context dict
        context = {f"key_{i}": f"value_{i}" * 100 for i in range(1000)}
        action = {"action": "click"}
        error = "timeout"
        # Should handle large context without performance issues
        start = time.time()
        suggestion = engine.analyze_failure(action, error, context)
        elapsed = time.time() - start
        assert suggestion is not None
        assert elapsed < 1.0  # Should complete in reasonable time


# ---------------------------------------------------------------------------
# Extreme input values
# ---------------------------------------------------------------------------


class TestExtremeInputs:
    """Test recovery engine with extreme or pathological inputs."""

    def test_very_long_action_dict(self):
        """Test with action dict containing many fields."""
        engine = RecoveryEngine()
        action = {"action": "click"}
        # Add many fields to the action dict
        for i in range(100):
            action[f"field_{i}"] = f"value_{i}" * 100
        error = "element not found"
        suggestion = engine.analyze_failure(action, error, {})
        assert suggestion is not None

    def test_very_long_error_message(self):
        """Test with extremely long error message."""
        engine = RecoveryEngine()
        action = {"action": "click"}
        # Create a very long error message
        error = "element not found: " + "x" * 10000
        suggestion = engine.analyze_failure(action, error, {})
        assert suggestion is not None
        # Recovery prompt should be truncated/not too long
        assert len(suggestion.recovery_prompt) < 2000

    def test_error_message_with_special_characters(self):
        """Test error message with regex special characters."""
        engine = RecoveryEngine()
        action = {"action": "click"}
        # Error with regex special chars
        error = "element not found: .*[](){}^$|+?\\"
        suggestion = engine.analyze_failure(action, error, {})
        assert suggestion is not None

    def test_action_with_null_values(self):
        """Test action dict with None values."""
        engine = RecoveryEngine()
        action = {"action": "click", "x": None, "y": None, "text": None}
        error = "click failed"
        suggestion = engine.analyze_failure(action, error, {})
        assert suggestion is not None


# ---------------------------------------------------------------------------
# Timeout recovery calculation edge cases
# ---------------------------------------------------------------------------


class TestTimeoutRecoveryEdgeCases:
    """Test edge cases in timeout recovery calculation."""

    def test_timeout_recovery_with_negative_duration(self):
        """Test timeout recovery with negative duration value."""
        engine = RecoveryEngine()
        action = {"action": "wait", "duration": -5.0}  # Negative duration
        error = "timeout"
        suggestion = engine.analyze_failure(action, error, {})
        assert suggestion is not None
        assert suggestion.pattern == "timeout"
        # Alternate action should have safe duration value
        if suggestion.alternate_action:
            new_duration = suggestion.alternate_action.get(
                "duration", suggestion.alternate_action.get("wait", 0)
            )
            assert new_duration >= 0

    def test_timeout_recovery_with_zero_duration(self):
        """Test timeout recovery with zero duration."""
        engine = RecoveryEngine()
        action = {"action": "wait", "duration": 0}
        error = "timeout"
        suggestion = engine.analyze_failure(action, error, {})
        assert suggestion is not None
        # Should increase from zero
        if suggestion.alternate_action:
            new_duration = suggestion.alternate_action.get(
                "duration", suggestion.alternate_action.get("wait", 0)
            )
            assert new_duration > 0

    def test_timeout_recovery_with_very_large_duration(self):
        """Test timeout recovery with very large duration (cap at 15s)."""
        engine = RecoveryEngine()
        action = {"action": "wait", "duration": 1000.0}  # Very large
        error = "timeout"
        suggestion = engine.analyze_failure(action, error, {})
        assert suggestion is not None
        # Should cap at 15 seconds max
        if suggestion.alternate_action:
            new_duration = suggestion.alternate_action.get(
                "duration", suggestion.alternate_action.get("wait", 0)
            )
            assert new_duration <= 15.0


# ---------------------------------------------------------------------------
# Thread safety in pattern matching
# ---------------------------------------------------------------------------


class TestPatternMatchingThreadSafety:
    """Test thread safety of pattern matching compilation."""

    def test_concurrent_pattern_matching(self):
        """Test that pattern matching works correctly with concurrent calls."""
        results = []
        errors = []

        def match_in_thread(msg: str):
            try:
                result = _match_pattern(msg)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = []
        test_messages = [
            "element not found",
            "timeout occurred",
            "permission denied",
            "click failed",
            "input failed",
        ]

        # Create multiple threads calling pattern matching simultaneously
        for msg in test_messages * 5:  # 25 concurrent calls
            t = threading.Thread(target=match_in_thread, args=(msg,))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Should complete without errors
        assert len(errors) == 0
        assert len(results) == 25


# ---------------------------------------------------------------------------
# Recovery suggestion validation
# ---------------------------------------------------------------------------


class TestRecoverySuggestionValidation:
    """Test that all recovery suggestions meet validity requirements."""

    def test_all_handlers_return_valid_suggestions(self):
        """Test that all recovery handlers return valid RecoverySuggestion objects."""
        RecoveryEngine()
        test_action = {"action": "click", "x": 100, "y": 100}
        test_error = "test error"
        test_context = {}

        for pattern_name, handler in _RECOVERY_HANDLERS.items():
            # Create a pattern-matching error for each handler
            if "element_not_found" in pattern_name:
                test_error = "element not found"
            elif "permission_denied" in pattern_name:
                test_error = "permission denied"
            elif "window_not_found" in pattern_name:
                test_error = "window not found"
            elif "timeout" in pattern_name:
                test_error = "timeout"
            elif "ocr_low_confidence" in pattern_name:
                test_error = "ocr low confidence"
            elif "app_not_found" in pattern_name:
                test_error = "app not found"
            elif "click_failed" in pattern_name:
                test_error = "click failed"
            elif "input_failed" in pattern_name:
                test_error = "input failed"

            try:
                suggestion = handler(test_action, test_error, test_context)
                assert isinstance(suggestion, RecoverySuggestion)
                assert hasattr(suggestion, "strategy")
                assert hasattr(suggestion, "confidence")
                assert 0.0 <= suggestion.confidence <= 1.0
            except Exception as e:
                pytest.fail(f"Handler {pattern_name} raised exception: {e}")

    def test_should_auto_apply_threshold(self):
        """Test that should_auto_apply respects the confidence threshold."""
        engine = RecoveryEngine()

        # Create suggestion with low confidence
        low_conf = RecoverySuggestion(strategy="retry_same", confidence=0.5)
        assert engine.should_auto_apply(low_conf) is False

        # Create suggestion with high confidence
        high_conf = RecoverySuggestion(strategy="retry_same", confidence=0.8)
        assert engine.should_auto_apply(high_conf) is True

        # Test at exactly threshold (0.7) - should be False since threshold is >
        threshold = RecoverySuggestion(strategy="retry_same", confidence=0.7)
        assert engine.should_auto_apply(threshold) is False

        # Test just above threshold
        just_above = RecoverySuggestion(strategy="retry_same", confidence=0.71)
        assert engine.should_auto_apply(just_above) is True
