"""Failure tracking and recovery prompt injection.

Centralizes the consecutive-failure counter and recovery logic that was
previously spread across two ``AgentEngine`` methods.

Design note: the ``_consecutive_failures`` counter lives on ``AgentEngine``
(some tests read/write it directly on bare ``__new__`` instances).  This
tracker holds a weak reference to the engine and mutates the counter there.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FailureTracker:
    """Manages consecutive-failure counting and recovery prompt injection.

    Holds a reference to the engine and the threshold configuration so the
    agent loop can stay focused on orchestration.  ``AgentEngine`` creates one
    during ``__init__`` and delegates its ``_handle_action_failure`` and
    ``_handle_consecutive_failure`` methods here.

    The ``consecutive_failures`` property is a pass-through to the engine's
    counter for external readers.
    """

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    @property
    def consecutive_failures(self) -> int:
        """Current consecutive failure count (delegates to engine)."""
        return self._engine._consecutive_failures

    def reset(self) -> None:
        """Reset the consecutive failure counter after a successful action."""
        self._engine._consecutive_failures = 0

    def handle_action_failure(
        self,
        action: dict[str, Any],
        action_name: str,
        error_msg: str,
        messages: list[dict[str, Any]],
    ) -> str | None:
        """Process a failed action: consult recovery engine and inject prompts.

        Increments the consecutive failure counter, asks the recovery engine
        for a suggestion, logs the event, and injects recovery messages into
        the conversation history.  Also checks failure thresholds and injects
        a strong recovery prompt when consecutive failures mount.

        Args:
            action: The action dict that failed.
            action_name: Short name of the action (e.g. ``"click"``).
            error_msg: Error output from the executor.
            messages: Conversation history list (mutated in-place).

        Returns:
            ``"abort"`` if the run should terminate (max failures reached),
            ``"recover"`` if a strong recovery prompt was injected, or
            ``None`` for a normal handled failure.
        """
        engine = self._engine
        engine._consecutive_failures += 1
        logger.warning(
            "Action '%s' failed (consecutive_failures=%d): %s",
            action_name,
            engine._consecutive_failures,
            error_msg[:200],
        )

        # Consult recovery engine
        suggestion = engine._recovery_engine.analyze_failure(
            action,
            error_msg,
            {"step": engine.step, "consecutive_failures": engine._consecutive_failures},
        )
        engine.logger.log_event(
            "recovery_suggestion",
            {
                "pattern": suggestion.pattern,
                "strategy": suggestion.strategy,
                "confidence": suggestion.confidence,
                "action": action_name,
            },
        )

        # Build recovery message for the LLM
        recovery_msg = f"Action '{action_name}' failed: {error_msg[:300]}."
        if suggestion.recovery_prompt:
            recovery_msg += f"\n\nRecovery hint: {suggestion.recovery_prompt}"

        messages.append({"role": "user", "content": recovery_msg})

        # Check failure thresholds
        if engine._consecutive_failures >= engine.MAX_CONSECUTIVE_FAILURES:
            error_summary = (
                f"Run terminated after {engine._consecutive_failures} consecutive failures. "
                f"Last error: {error_msg[:200]}"
            )
            engine.notes.append(error_summary)
            engine.logger.log_event(
                "abort",
                {
                    "reason": "max_consecutive_failures",
                    "count": engine._consecutive_failures,
                    "last_error": error_msg[:200],
                },
            )
            return "abort"

        if engine._consecutive_failures >= engine.RECOVERY_PROMPT_THRESHOLD:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "[SYSTEM RECOVERY] You have had multiple consecutive failures. "
                        "Please completely change your approach. Consider: "
                        "1) Taking a fresh screenshot to reassess, "
                        "2) Using a different action type "
                        "(e.g., list_controls, read_text), "
                        "3) Trying keyboard navigation instead of mouse clicks, "
                        "4) Finishing with a note if the goal is partially achieved."
                    ),
                }
            )
            return "recover"

        return None

    def handle_consecutive_failure(
        self,
        failure_type: str,
        messages: list[dict[str, Any]],
    ) -> str:
        """Track consecutive failures and inject recovery prompts when needed.

        Centralizes the duplicated failure-tracking logic from the main agent
        loop.  Increments ``_consecutive_failures`` and decides whether to
        inject a recovery/nudge prompt or abort the run.

        Args:
            failure_type: ``"llm_call"`` when the LLM call itself failed,
                ``"parse"`` when the response couldn't be parsed as valid JSON.
            messages: The running conversation list (mutated in-place).

        Returns:
            ``"abort"`` if ``MAX_CONSECUTIVE_FAILURES`` has been reached,
            ``"continue"`` otherwise.
        """
        engine = self._engine
        engine._consecutive_failures += 1
        logger.warning(
            "%s failure (consecutive_failures=%d)",
            "LLM call" if failure_type == "llm_call" else "Parse",
            engine._consecutive_failures,
        )

        if failure_type == "parse":
            engine.notes.append(f"Step {engine.step}: No valid action parsed from LLM response")
            messages.append(
                {
                    "role": "user",
                    "content": "Please respond with a valid JSON action. Only JSON, no other text.",
                }
            )

        if engine._consecutive_failures >= engine.MAX_CONSECUTIVE_FAILURES:
            engine.notes.append(f"Terminating: {engine._consecutive_failures} consecutive failures")
            engine.logger.log_event(
                "abort",
                {
                    "reason": "max_consecutive_failures",
                    "count": engine._consecutive_failures,
                },
            )
            return "abort"

        if engine._consecutive_failures >= engine.RECOVERY_PROMPT_THRESHOLD:
            if failure_type == "llm_call":
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "[SYSTEM] Multiple consecutive failures have occurred. "
                            "Please take a completely different approach. "
                            "Re-evaluate the situation from the current screenshot "
                            "and try an alternative strategy."
                        ),
                    }
                )
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "[SYSTEM] Multiple parse failures. Please return a simple "
                            '{"action": "finish", "summary": "..."} '
                            'or {"action": "note", "text": "..."}.'
                        ),
                    }
                )

        return "continue"
