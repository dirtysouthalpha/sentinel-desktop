"""
Sentinel Desktop v2 — Global failsafe hotkey.

Listens for three rapid Esc presses (within ~1.5 seconds) and invokes a
shutdown callback. pyautogui's move-mouse-to-corner failsafe doesn't always
work when the agent is mid-action, so this gives the user a keyboard
escape hatch.

Uses the ``keyboard`` package if available. On Linux that needs root, so we
fall back to a no-op silently rather than crashing the app.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Time window (seconds) for three Esc presses to count as a panic stop.
PANIC_WINDOW_SECONDS = 1.5
PANIC_PRESS_COUNT = 3


class FailsafeListener:
    """Background thread that calls ``on_panic`` after three rapid Esc presses."""

    def __init__(self, on_panic: Callable[[], None]) -> None:
        self._on_panic = on_panic
        self._presses: deque = deque(maxlen=PANIC_PRESS_COUNT)
        self._lock = threading.Lock()
        self._started = False
        self._stopped = False
        self._hotkey_handle = None
        self._kb = None  # holds the imported keyboard module if available

    def start(self) -> bool:
        """Start listening. Returns True if hooks were installed.

        Failures are logged but never raised — the agent must still run if
        the hotkey can't be registered (e.g. missing permissions).
        """
        if self._started:
            return True
        try:
            import keyboard  # type: ignore
        except Exception as exc:
            logger.info(
                "Esc-x3 failsafe disabled (the 'keyboard' package is unavailable: %s)",
                exc,
            )
            return False

        try:
            self._hotkey_handle = keyboard.on_press_key("esc", self._on_esc)
            self._kb = keyboard
            self._started = True
            logger.info("Esc x3 failsafe armed (press Esc three times to stop)")
            return True
        except Exception as exc:
            logger.warning("Could not install Esc failsafe hook: %s", exc)
            return False

    def stop(self) -> None:
        """Uninstall the global hook. Safe to call multiple times."""
        if self._stopped or not self._started or self._kb is None:
            return
        try:
            if self._hotkey_handle is not None:
                self._kb.unhook(self._hotkey_handle)
        except Exception as exc:
            logger.debug("Failsafe unhook failed: %s", exc)
        finally:
            self._stopped = True

    # -- internal -------------------------------------------------------

    def _on_esc(self, _event) -> None:
        now = time.monotonic()
        with self._lock:
            self._presses.append(now)
            if len(self._presses) < PANIC_PRESS_COUNT:
                return
            window = self._presses[-1] - self._presses[0]
            if window > PANIC_WINDOW_SECONDS:
                return
            # Reset so a fourth Esc shortly after doesn't re-trigger.
            self._presses.clear()
        logger.warning("PANIC: Esc x3 detected — stopping agent")
        try:
            self._on_panic()
        except Exception as exc:
            logger.error("on_panic callback raised: %s", exc)


# Convenience module-level wrapper so callers don't have to manage the object.
_active: Optional[FailsafeListener] = None


def arm(on_panic: Callable[[], None]) -> bool:
    """Install a global Esc-x3 listener. Returns True on success."""
    global _active
    if _active is not None:
        _active.stop()
    _active = FailsafeListener(on_panic)
    return _active.start()


def disarm() -> None:
    """Remove the global listener if any."""
    global _active
    if _active is not None:
        _active.stop()
        _active = None
