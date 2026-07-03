"""Retry planner with escalation strategies.

When an action fails, instead of crashing, try alternative approaches:
- Different selector
- Keyboard fallback (Tab + Enter instead of click)
- CLI fallback (command line equivalent)
- Skip and continue
- Ask operator
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RetryStrategy:
    """Defines how to retry a failed action."""

    def __init__(self, name: str) -> None:
        self.name = name

    def apply(self, action: dict[str, Any], attempt: int) -> dict[str, Any] | None:
        """Return modified action dict for this retry attempt, or None to give up."""
        raise NotImplementedError


class SelectorFallbackStrategy(RetryStrategy):
    """Try alternative CSS/xpath/accessibility selectors."""

    def __init__(self, selectors: list[str]) -> None:
        super().__init__("selector_fallback")
        self._selectors = selectors

    def apply(self, action: dict[str, Any], attempt: int) -> dict[str, Any] | None:
        if attempt < len(self._selectors):
            new_action = dict(action)
            new_action["selector"] = self._selectors[attempt]
            return new_action
        return None


class KeyboardFallbackStrategy(RetryStrategy):
    """Replace a click with keyboard navigation."""

    def __init__(self, key_sequence: list[str] | None = None) -> None:
        super().__init__("keyboard_fallback")
        self._keys = key_sequence or ["Tab", "Return"]

    def apply(self, action: dict[str, Any], attempt: int) -> dict[str, Any] | None:
        if attempt == 0:
            new_action = dict(action)
            new_action["action"] = "hotkey"
            new_action["keys"] = self._keys
            del new_action["selector"]
            return new_action
        return None


class CoordAdjustmentStrategy(RetryStrategy):
    """Nudge coordinates by small offsets when element slightly moved."""

    def __init__(self, offsets: list[tuple[int, int]] | None = None) -> None:
        super().__init__("coord_adjustment")
        self._offsets = offsets or [(0, 5), (0, -5), (5, 0), (-5, 0), (0, 10)]

    def apply(self, action: dict[str, Any], attempt: int) -> dict[str, Any] | None:
        if attempt < len(self._offsets) and "x" in action:
            new_action = dict(action)
            dx, dy = self._offsets[attempt]
            new_action["x"] = action.get("x", 0) + dx
            new_action["y"] = action.get("y", 0) + dy
            return new_action
        return None


class CLIFallbackStrategy(RetryStrategy):
    """Replace GUI action with CLI equivalent."""

    def __init__(self, cli_commands: list[str]) -> None:
        super().__init__("cli_fallback")
        self._commands = cli_commands

    def apply(self, action: dict[str, Any], attempt: int) -> dict[str, Any] | None:
        if attempt < len(self._commands):
            new_action = dict(action)
            new_action["action"] = "shell"
            new_action["command"] = self._commands[attempt]
            return new_action
        return None


@dataclass
class RetryResult:
    """Outcome of a retry sequence."""

    success: bool
    attempts: int
    final_action: dict[str, Any] | None = None
    error: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)


class RetryPlanner:
    """Plan and execute retries with multiple strategies."""

    def __init__(self, max_attempts: int = 3, delay_between: float = 1.0) -> None:
        self._max = max_attempts
        self._delay = delay_between
        self._strategies: list[RetryStrategy] = []

    def add_strategy(self, strategy: RetryStrategy) -> None:
        self._strategies.append(strategy)

    def execute(self, action: dict[str, Any], executor: Callable[[dict[str, Any]], bool]) -> RetryResult:
        """Try an action with all registered strategies as fallbacks.

        executor: callable that takes an action dict and returns True on success.
        """
        history = []
        current_action = dict(action)

        for attempt in range(self._max):
            logger.debug("Retry attempt %d/%d: %s", attempt + 1, self._max, current_action)
            history.append(dict(current_action))

            try:
                if executor(current_action):
                    return RetryResult(success=True, attempts=attempt + 1, final_action=current_action, history=history)
            except Exception as exc:
                logger.debug("Attempt %d failed: %s", attempt + 1, exc)

            # Try next strategy
            if attempt < self._max - 1:
                next_action = None
                for strategy in self._strategies:
                    next_action = strategy.apply(action, attempt)
                    if next_action:
                        logger.info("Retry strategy '%s' activated", strategy.name)
                        current_action = next_action
                        break
                if not next_action:
                    break  # No more strategies

            if self._delay > 0:
                time.sleep(self._delay)

        return RetryResult(success=False, attempts=len(history), final_action=current_action, history=history)


__all__ = [
    "RetryStrategy",
    "SelectorFallbackStrategy",
    "KeyboardFallbackStrategy",
    "CoordAdjustmentStrategy",
    "CLIFallbackStrategy",
    "RetryResult",
    "RetryPlanner",
]
