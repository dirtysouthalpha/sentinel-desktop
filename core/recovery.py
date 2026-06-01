"""Sentinel Desktop v3.1 -- Self-healing Recovery Engine.

Analyzes action failures and suggests recovery strategies so the agent
loop can keep making progress instead of terminating on every error.

Typical usage::

    from core.recovery import RecoveryEngine

    engine = RecoveryEngine()
    suggestion = engine.analyze_failure(action, exc, context)
    if engine.should_auto_apply(suggestion):
        # use suggestion.alternate_action or inject suggestion.recovery_prompt
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RecoverySuggestion:
    """A recovery strategy produced by :class:`RecoveryEngine`."""

    strategy: str  # "retry_same" | "retry_alternate" | "skip" | "abort"
    alternate_action: dict[str, Any] | None = None
    recovery_prompt: str = ""
    confidence: float = 0.0  # 0-1 how likely this recovery is to work
    pattern: str = ""  # which failure pattern matched

    @property
    def is_deterministic(self) -> bool:
        """True when the strategy doesn't depend on LLM creativity."""
        return self.strategy in ("retry_same", "skip", "abort")


# ---------------------------------------------------------------------------
# Failure pattern definitions
# ---------------------------------------------------------------------------

# Each pattern is (regex-on-error-message, handler-function).
# The handler receives (action, error, context) and returns a RecoverySuggestion.

_FAILURE_PATTERNS: list[tuple[str, str]] = [
    # (compiled-regex is built lazily; raw pattern string stored here)
    (r"element not found|text not found|could not find|not located", "element_not_found"),
    (r"permission denied|access denied|access is denied|unauthorized", "permission_denied"),
    (r"window not found|no window matching|window .* not located", "window_not_found"),
    (r"timeout|timed out|deadline exceeded", "timeout"),
    (r"ocr.*low confidence|low_confidence|ocr.*failed|garbled|junk", "ocr_low_confidence"),
    (r"app not found|application not found|could not launch|not installed", "app_not_found"),
    (r"click.*fail|click error|coordinate.*out of range", "click_failed"),
    (r"type.*fail|keyboard.*error|send_keys.*fail", "input_failed"),
]


def _compile_patterns() -> list[tuple[re.Pattern, str]]:
    """Compile regex patterns once on first use."""
    return [(re.compile(p, re.IGNORECASE), name) for p, name in _FAILURE_PATTERNS]


_compiled_patterns: list[tuple[re.Pattern, str]] | None = None


def _match_pattern(error_msg: str) -> str | None:
    """Try to match *error_msg* against a known recovery pattern.

    Returns the pattern name on match, otherwise ``None``.
    """
    global _compiled_patterns
    if _compiled_patterns is None:
        _compiled_patterns = _compile_patterns()
    for pat, name in _compiled_patterns:
        if pat.search(error_msg):
            return name
    return None


# ---------------------------------------------------------------------------
# Recovery handlers
# ---------------------------------------------------------------------------


def _recover_element_not_found(
    action: dict[str, Any], error: str, context: dict[str, Any]
) -> RecoverySuggestion:
    """Suggest OCR scan + keyboard alternative when an element can't be found."""
    action_type = action.get("action", "")
    alt = None
    prompt = (
        "The target element was not found on screen. "
        "Take a fresh screenshot and use list_controls or OCR read_text "
        "to locate the element, then try again with updated coordinates."
    )

    # If it was a click_text, try suggesting a keyboard-driven alternative
    if action_type == "click_text":
        text = action.get("text", "")
        alt = {
            "action": "type_text",
            "text": text,
        }
        prompt = (
            f"Text '{text}' was not found via OCR for clicking. "
            "Consider using list_controls to find the UI element, "
            "or navigate to it with Tab/Arrow keys and press Enter."
        )

    return RecoverySuggestion(
        strategy="retry_alternate",
        alternate_action=alt,
        recovery_prompt=prompt,
        confidence=0.6,
        pattern="element_not_found",
    )


def _recover_permission_denied(
    action: dict[str, Any], error: str, context: dict[str, Any]
) -> RecoverySuggestion:
    """Check for UAC dialog, suggest elevation or alternate path."""
    prompt = (
        "A permission error occurred. Check if a UAC/elevation dialog is "
        "open on screen. If so, you may need to click 'Yes' to elevate. "
        "Otherwise, try an alternate file path or action that doesn't require "
        "elevation."
    )
    return RecoverySuggestion(
        strategy="retry_alternate",
        alternate_action=None,
        recovery_prompt=prompt,
        confidence=0.5,
        pattern="permission_denied",
    )


def _recover_window_not_found(
    action: dict[str, Any], error: str, context: dict[str, Any]
) -> RecoverySuggestion:
    """List windows, look for similar names, try alt-tab."""
    prompt = (
        "The target window was not found. Try pressing Alt+Tab to cycle "
        "through open windows, or use list_controls/read_text on the current "
        "screen to verify what's visible. The window title may have changed."
    )
    # Suggest alt-tab as an alternate action
    alt = {
        "action": "hotkey",
        "keys": ["alt", "tab"],
    }
    return RecoverySuggestion(
        strategy="retry_alternate",
        alternate_action=alt,
        recovery_prompt=prompt,
        confidence=0.55,
        pattern="window_not_found",
    )


def _recover_timeout(
    action: dict[str, Any], error: str, context: dict[str, Any]
) -> RecoverySuggestion:
    """Increase wait, check for loading indicators."""
    # Suggest a longer wait
    current_wait = action.get("duration", action.get("wait", 1.0))
    new_wait = min(current_wait * 2, 15.0)
    alt = dict(action)  # shallow copy
    if "duration" in alt:
        alt["duration"] = new_wait
    elif "wait" in alt:
        alt["wait"] = new_wait

    prompt = (
        f"A timeout occurred. The operation may need more time. "
        f"Retrying with increased wait ({new_wait}s). "
        "Check for loading spinners or progress bars on screen."
    )
    return RecoverySuggestion(
        strategy="retry_same",
        alternate_action=alt,
        recovery_prompt=prompt,
        confidence=0.65,
        pattern="timeout",
    )


def _recover_ocr_low_confidence(
    action: dict[str, Any], error: str, context: dict[str, Any]
) -> RecoverySuggestion:
    """Suggest UIA control navigation instead of OCR."""
    prompt = (
        "OCR produced low-confidence results. Try using list_controls "
        "to navigate via UIAutomation instead of relying on text recognition. "
        "You can also use click_control with the automation_id or control name."
    )
    return RecoverySuggestion(
        strategy="retry_alternate",
        alternate_action=None,
        recovery_prompt=prompt,
        confidence=0.7,
        pattern="ocr_low_confidence",
    )


def _recover_app_not_found(
    action: dict[str, Any], error: str, context: dict[str, Any]
) -> RecoverySuggestion:
    """Search common install paths, suggest alternatives."""
    app_name = action.get("app", action.get("name", action.get("path", "")))
    prompt = (
        f"Application '{app_name}' could not be found or launched. "
        "Try searching common install paths (e.g. Start Menu, Desktop), "
        "or use start_process with the full executable path. "
        "You can also try smart_open which searches multiple locations."
    )
    # Suggest smart_open as an alternative
    alt = {
        "action": "smart_open",
        "query": app_name,
    }
    return RecoverySuggestion(
        strategy="retry_alternate",
        alternate_action=alt,
        recovery_prompt=prompt,
        confidence=0.6,
        pattern="app_not_found",
    )


def _recover_click_failed(
    action: dict[str, Any], error: str, context: dict[str, Any]
) -> RecoverySuggestion:
    """Generic click failure -- suggest re-screenshot and retry."""
    prompt = (
        "A click action failed. Take a fresh screenshot to get updated "
        "coordinates, verify the target is still visible, and retry."
    )
    return RecoverySuggestion(
        strategy="retry_same",
        alternate_action=None,
        recovery_prompt=prompt,
        confidence=0.55,
        pattern="click_failed",
    )


def _recover_input_failed(
    action: dict[str, Any], error: str, context: dict[str, Any]
) -> RecoverySuggestion:
    """Keyboard input failure -- suggest clipboard paste as alternative."""
    text = action.get("text", "")
    alt = None
    prompt = "A keyboard input action failed. "
    if text:
        alt = {
            "action": "hotkey",
            "keys": "ctrl+v",
        }
        prompt += (
            "Try copying the text to clipboard first and then using Ctrl+V "
            "to paste instead of typing it character by character."
        )
    else:
        prompt += "Try a different keyboard approach or use the on-screen keyboard."

    return RecoverySuggestion(
        strategy="retry_alternate",
        alternate_action=alt,
        recovery_prompt=prompt,
        confidence=0.5,
        pattern="input_failed",
    )


# Map pattern names to handler functions
_RecoveryHandler = Callable[[dict[str, Any], str, dict[str, Any]], "RecoverySuggestion"]

_RECOVERY_HANDLERS: dict[str, _RecoveryHandler] = {
    "element_not_found": _recover_element_not_found,
    "permission_denied": _recover_permission_denied,
    "window_not_found": _recover_window_not_found,
    "timeout": _recover_timeout,
    "ocr_low_confidence": _recover_ocr_low_confidence,
    "app_not_found": _recover_app_not_found,
    "click_failed": _recover_click_failed,
    "input_failed": _recover_input_failed,
}


# ---------------------------------------------------------------------------
# RecoveryEngine
# ---------------------------------------------------------------------------


class RecoveryEngine:
    """Analyzes action failures and produces recovery suggestions.

    The engine loop calls ``analyze_failure()`` when an action throws an
    exception or returns an error result. If ``should_auto_apply()`` is
    True, the suggestion can be applied automatically without involving
    the LLM.
    """

    # Threshold for auto-applying a suggestion.
    AUTO_APPLY_CONFIDENCE_THRESHOLD = 0.7

    def analyze_failure(
        self,
        action: dict[str, Any],
        error: Exception | str,
        context: dict[str, Any] | None = None,
    ) -> RecoverySuggestion:
        """Analyze a failed action and return a recovery suggestion.

        Args:
            action: The action dict that failed.
            error: The exception or error message string.
            context: Optional dict with extra context (e.g. step number,
                     screenshot available, etc.).

        Returns:
            A :class:`RecoverySuggestion` with the best recovery strategy.

        """
        context = context or {}
        error_msg = str(error)

        # Try to match against known failure patterns
        pattern = _match_pattern(error_msg)

        if pattern and pattern in _RECOVERY_HANDLERS:
            handler = _RECOVERY_HANDLERS[pattern]
            try:
                suggestion = handler(action, error_msg, context)
                logger.info(
                    "Recovery analysis: pattern=%s strategy=%s confidence=%.2f",
                    pattern,
                    suggestion.strategy,
                    suggestion.confidence,
                )
                return suggestion
            except (ValueError, KeyError, RuntimeError, OSError):
                logger.exception("Recovery handler for %s failed", pattern)

        # Default: generic retry suggestion
        action_name = action.get("action", "unknown")
        return RecoverySuggestion(
            strategy="retry_same",
            alternate_action=None,
            recovery_prompt=(
                f"Action '{action_name}' failed with: {error_msg[:200]}. "
                "Try a different approach to accomplish the goal."
            ),
            confidence=0.3,
            pattern="generic",
        )

    def should_auto_apply(self, suggestion: RecoverySuggestion) -> bool:
        """Return True if the suggestion can be applied automatically.

        A suggestion is auto-applied when its confidence exceeds the
        threshold AND its strategy is deterministic (no LLM creativity
        needed).
        """
        return (
            suggestion.confidence > self.AUTO_APPLY_CONFIDENCE_THRESHOLD
            and suggestion.is_deterministic
        )
