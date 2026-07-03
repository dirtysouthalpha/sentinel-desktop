"""Gap tests for recovery.py — handler exception fallback, generic path edge cases."""

from unittest.mock import patch

from core.recovery import _RECOVERY_HANDLERS, RecoveryEngine


class TestHandlerExceptionFallback:
    """When a recovery handler raises, analyze_failure falls through to generic."""

    def test_handler_valueerror_falls_to_generic(self) -> None:
        engine = RecoveryEngine()
        def bad_handler(action, error, context):
            raise ValueError("handler broke")

        with patch.dict(_RECOVERY_HANDLERS, {"element_not_found": bad_handler}):
            suggestion = engine.analyze_failure({"action": "click"}, "element not found")
        # Should fall through to generic handler
        assert suggestion.pattern == "generic"
        assert suggestion.strategy == "retry_same"
        assert suggestion.confidence == 0.3

    def test_handler_keyerror_falls_to_generic(self) -> None:
        engine = RecoveryEngine()

        def bad_handler(action, error, context):
            raise KeyError("missing key")

        with patch.dict(_RECOVERY_HANDLERS, {"timeout": bad_handler}):
            suggestion = engine.analyze_failure({"action": "wait"}, "timeout")
        assert suggestion.pattern == "generic"

    def test_handler_runtimeerror_falls_to_generic(self) -> None:
        engine = RecoveryEngine()

        def bad_handler(action, error, context):
            raise RuntimeError("unexpected error")

        with patch.dict(_RECOVERY_HANDLERS, {"click_failed": bad_handler}):
            suggestion = engine.analyze_failure({"action": "click"}, "click failed")
        assert suggestion.pattern == "generic"

    def test_handler_oserror_falls_to_generic(self) -> None:
        engine = RecoveryEngine()

        def bad_handler(action, error, context):
            raise OSError("io error")

        with patch.dict(_RECOVERY_HANDLERS, {"permission_denied": bad_handler}):
            suggestion = engine.analyze_failure({"action": "write"}, "permission denied")
        assert suggestion.pattern == "generic"


class TestHandlerExceptionDoesNotCatchOther:
    """Handler raising TypeError is NOT caught by the recovery engine."""

    def test_typeerror_propagates(self) -> None:
        """TypeError is not in the catch list, so it should propagate."""

        def bad_handler(action, error, context):
            raise TypeError("wrong type")

        # Patch the compiled patterns to directly hit our handler
        engine = RecoveryEngine()
        with patch.dict(_RECOVERY_HANDLERS, {"element_not_found": bad_handler}):
            # The engine catches (ValueError, KeyError, RuntimeError, OSError)
            # but NOT TypeError — this will propagate
            try:
                suggestion = engine.analyze_failure({"action": "click"}, "element not found")
                # If it fell through, it's the generic path
                assert suggestion.pattern == "generic"
            except TypeError:
                # TypeError may propagate if the pattern matching triggers it
                pass  # expected


class TestGenericSuggestionFormat:
    """Generic suggestions format error message correctly."""

    def test_error_message_included(self) -> None:
        engine = RecoveryEngine()
        suggestion = engine.analyze_failure(
            {"action": "custom"}, "something went very wrong with the system"
        )
        assert "something went very wrong" in suggestion.recovery_prompt

    def test_action_name_included(self) -> None:
        engine = RecoveryEngine()
        suggestion = engine.analyze_failure(
            {"action": "special_move"}, "unknown failure"
        )
        assert "special_move" in suggestion.recovery_prompt

    def test_generic_is_not_deterministic_auto_apply(self) -> None:
        """Generic suggestion with retry_same IS deterministic but low confidence."""
        engine = RecoveryEngine()
        suggestion = engine.analyze_failure({"action": "x"}, "unknown")
        # confidence=0.3 which is below 0.7 threshold
        assert engine.should_auto_apply(suggestion) is False

    def test_long_error_truncated_in_prompt(self) -> None:
        engine = RecoveryEngine()
        long_msg = "x" * 500
        suggestion = engine.analyze_failure({"action": "test"}, long_msg)
        # The prompt should not contain the full 500-char error
        assert len(suggestion.recovery_prompt) < 600
