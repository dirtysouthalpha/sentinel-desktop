"""Edge-case tests for core/recovery.py not covered by earlier suites.

Covers:
- Handler raises ValueError/KeyError/RuntimeError/OSError → falls back to generic
- Malformed action dict (missing keys) passed to individual handlers
- context=None passed to analyze_failure
- error argument as Exception object (not string)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.recovery import _RECOVERY_HANDLERS, RecoveryEngine, _match_pattern

# ---------------------------------------------------------------------------
# analyze_failure — exception in handler falls back to generic
# ---------------------------------------------------------------------------


class TestHandlerExceptionFallback:
    """When a matched handler raises, analyze_failure returns the generic suggestion."""

    def _engine_with_failing_handler(self, exc: Exception) -> RecoveryEngine:
        engine = RecoveryEngine()
        return engine

    @pytest.mark.parametrize(
        "exc_type",
        [ValueError("bad value"), KeyError("missing key"), RuntimeError("runtime boom"), OSError("os fail")],
    )
    def test_handler_exception_returns_generic(self, exc_type: Exception) -> None:
        engine = RecoveryEngine()
        # element_not_found pattern is reliably matched
        error_msg = "element not found: button"
        assert _match_pattern(error_msg) == "element_not_found"

        with patch.dict(
            "core.recovery._RECOVERY_HANDLERS",
            {"element_not_found": lambda *_: (_ for _ in ()).throw(exc_type)},
        ):
            suggestion = engine.analyze_failure({"action": "click"}, error_msg)

        assert suggestion.pattern == "generic"
        assert suggestion.strategy == "retry_same"
        assert suggestion.confidence == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# analyze_failure — context=None
# ---------------------------------------------------------------------------


class TestContextNone:
    def test_context_none_defaults_to_empty_dict(self) -> None:
        engine = RecoveryEngine()
        # Should not raise; context=None is handled internally
        suggestion = engine.analyze_failure({"action": "move"}, "some weird error", context=None)
        assert suggestion is not None

    def test_context_none_unknown_error_generic(self) -> None:
        engine = RecoveryEngine()
        suggestion = engine.analyze_failure({"action": "type"}, "completely unknown failure", context=None)
        assert suggestion.pattern == "generic"


# ---------------------------------------------------------------------------
# analyze_failure — error as Exception object
# ---------------------------------------------------------------------------


class TestErrorAsException:
    def test_exception_object_is_stringified(self) -> None:
        engine = RecoveryEngine()
        exc = RuntimeError("element not found: dialog")
        suggestion = engine.analyze_failure({"action": "click"}, exc)
        # Should still match the pattern from the stringified message
        assert suggestion.pattern != "generic"

    def test_exception_without_matching_pattern(self) -> None:
        engine = RecoveryEngine()
        exc = ValueError("some totally unknown failure")
        suggestion = engine.analyze_failure({"action": "scroll"}, exc)
        assert suggestion.pattern == "generic"
        assert "scroll" in suggestion.recovery_prompt


# ---------------------------------------------------------------------------
# Individual handlers — malformed / minimal action dicts
# ---------------------------------------------------------------------------


class TestHandlerMalformedAction:
    """All handlers must tolerate an empty action dict gracefully."""

    @pytest.mark.parametrize("pattern", list(_RECOVERY_HANDLERS.keys()))
    def test_handler_empty_action(self, pattern: str) -> None:
        handler = _RECOVERY_HANDLERS[pattern]
        # Should not raise, even with an empty action dict
        suggestion = handler({}, "some error", {})
        assert suggestion is not None

    def test_input_failed_no_text_uses_fallback_prompt(self) -> None:
        handler = _RECOVERY_HANDLERS["input_failed"]
        suggestion = handler({}, "keyboard input failed", {})
        # With no 'text' field, alternate_action should be None
        assert suggestion.alternate_action is None
        assert "keyboard" in suggestion.recovery_prompt.lower()

    def test_input_failed_with_text_suggests_paste(self) -> None:
        handler = _RECOVERY_HANDLERS["input_failed"]
        suggestion = handler({"text": "hello world"}, "keyboard input failed", {})
        assert suggestion.alternate_action is not None
        assert suggestion.alternate_action.get("keys") == "ctrl+v"
