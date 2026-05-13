"""
Sentinel Desktop v3.0 — Self-healing recovery manager.

Provides automatic failure analysis, popup auto-dismiss, retry logic, and
fallback strategies when an action fails.  Designed for Windows desktop
automation with graceful degradation on non-Windows platforms.

Recovery flow
-------------
1. An action fails → :meth:`handle_failure` analyses the error type.
2. Depending on the failure category a :class:`RecoveryAction` is chosen:
   - window_not_found → RETRY_WITH_ALT
   - element_not_found → RETRY
   - popup_detected   → DISMISS_POPUP_AND_RETRY
   - timeout          → RETRY
   - attempt > max    → ABORT
3. The caller can then invoke :meth:`retry_with_fallback` or
   :meth:`dismiss_popup` as directed by the recovery action.

Thread-safe.  All Windows-specific imports are guarded so the module can be
imported on any platform without crashing.
"""

from __future__ import annotations

import logging
import platform
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform gate
# ---------------------------------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"

# Lazy win32gui reference — set inside :meth:`_ensure_win32`.
_win32gui: Any = None
_win32con: Any = None
_win32api: Any = None


def _ensure_win32() -> bool:
    """Attempt to import win32 modules.  Returns *True* on success."""
    global _win32gui, _win32con, _win32api
    if _win32gui is not None:
        return True
    if not _IS_WINDOWS:
        return False
    try:
        import win32api  # type: ignore
        import win32con  # type: ignore
        import win32gui  # type: ignore

        _win32gui = win32gui
        _win32con = win32con
        _win32api = win32api
        return True
    except Exception as exc:
        logger.warning("win32 modules unavailable — popup detection disabled: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class RecoveryAction(Enum):
    """Possible recovery decisions returned by :meth:`handle_failure`."""

    RETRY = "retry"
    RETRY_WITH_ALT = "retry_with_alt"
    SKIP = "skip"
    ABORT = "abort"
    DISMISS_POPUP_AND_RETRY = "dismiss_popup_and_retry"


@dataclass
class PopupInfo:
    """Describes a detected popup window."""

    hwnd: int
    title: str
    class_name: str
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0
    matched_keyword: str = ""

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_POPUP_KEYWORDS: list[str] = [
    "error",
    "warning",
    "confirm",
    "cancel",
    "close",
    "exception",
    "access denied",
    "failed",
    "could not",
    "unable to",
    "retry",
    "abort",
    "ignore",
    "don't send",
]

_DEFAULT_CONFIG: dict[str, Any] = {
    "max_retries": 2,
    "retry_delay": 1.0,
    "dismiss_popups": True,
    "popup_keywords": _DEFAULT_POPUP_KEYWORDS,
}

# ---------------------------------------------------------------------------
# Fallback mapping — maps a failed action type to an ordered list of
# alternatives that the recovery manager should try.
# ---------------------------------------------------------------------------

_FALLBACK_MAP: dict[str, list[str]] = {
    "click": ["click_image", "click_text"],
    "click_image": ["click_text", "click"],
    "click_text": ["click_image", "click"],
    "type_text": ["clipboard_paste"],
    "set_text": ["clipboard_paste"],
}


# ---------------------------------------------------------------------------
# RecoveryManager
# ---------------------------------------------------------------------------


class RecoveryManager:
    """Analyse action failures and orchestrate recovery.

    Parameters
    ----------
    action_executor:
        An :class:`~core.action_executor.ActionExecutor` instance used to
        dispatch fallback actions.  If *None* the manager operates in
        analysis-only mode (it will return recovery decisions but cannot
        execute retries itself).
    config:
        Override default settings.  Recognised keys are *max_retries*,
        *retry_delay*, *dismiss_popups*, and *popup_keywords*.
    """

    def __init__(
        self,
        action_executor: Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        merged = {**_DEFAULT_CONFIG, **(config or {})}
        self.max_retries: int = int(merged["max_retries"])
        self.retry_delay: float = float(merged["retry_delay"])
        self.dismiss_popups: bool = bool(merged["dismiss_popups"])
        self.popup_keywords: list[str] = list(merged["popup_keywords"])

        self._executor = action_executor

        # --- internal bookkeeping ---
        self._total_failures: int = 0
        self._total_retries: int = 0
        self._total_popup_dismissals: int = 0
        self._total_fallbacks: int = 0
        self._total_aborts: int = 0
        self._total_skips: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_failure(
        self,
        action: dict[str, Any],
        result: dict[str, Any],
        attempt: int,
    ) -> RecoveryAction:
        """Analyse a failure and decide the recovery strategy.

        Parameters
        ----------
        action:
            The action dict that was executed (e.g. ``{"type": "click", ...}``).
        result:
            Execution result dict — must contain at least ``"success": False``
            and optionally ``"error"`` / ``"error_type"`` keys.
        attempt:
            1-based attempt counter.

        Returns
        -------
        RecoveryAction
            The recommended recovery action for the caller.
        """
        self._total_failures += 1
        action_type = action.get("type", "unknown")
        error_type = result.get("error_type", "")
        error_msg = str(result.get("error", "")).lower()

        logger.info(
            "Handling failure: action=%s attempt=%d error_type=%s",
            action_type,
            attempt,
            error_type,
        )

        # 1. Check for popups first — they can interfere with any action.
        if self.dismiss_popups:
            popups = self.check_for_popups()
            if popups:
                logger.warning(
                    "Popup detected during failure: %s — will dismiss and retry",
                    popups[0].title,
                )
                return RecoveryAction.DISMISS_POPUP_AND_RETRY

        # 2. Exceeded max retries → abort.
        if attempt > self.max_retries:
            logger.warning(
                "Max retries (%d) exceeded for action %s — aborting",
                self.max_retries,
                action_type,
            )
            self._total_aborts += 1
            return RecoveryAction.ABORT

        # 3. Error-specific routing.
        if "window_not_found" in error_type or "window not found" in error_msg:
            logger.info("Window not found — will retry with alternative strategy")
            return RecoveryAction.RETRY_WITH_ALT

        if "element_not_found" in error_type or "element not found" in error_msg:
            logger.info("Element not found — will retry")
            self._total_retries += 1
            return RecoveryAction.RETRY

        if "timeout" in error_type or "timeout" in error_msg or "timed out" in error_msg:
            logger.info("Timeout detected — will retry")
            self._total_retries += 1
            return RecoveryAction.RETRY

        if (
            "permission" in error_msg
            or "access denied" in error_msg
            or "access is denied" in error_msg
        ):
            logger.warning("Permission error — skipping action")
            self._total_skips += 1
            return RecoveryAction.SKIP

        # 4. Generic fallback — retry if retries remain.
        if attempt <= self.max_retries:
            self._total_retries += 1
            return RecoveryAction.RETRY

        self._total_aborts += 1
        return RecoveryAction.ABORT

    # ------------------------------------------------------------------
    # Popup detection
    # ------------------------------------------------------------------

    def check_for_popups(self) -> list[PopupInfo]:
        """Scan all top-level windows for titles matching known popup keywords.

        Uses ``win32gui.EnumWindows`` on Windows.  Returns an empty list on
        non-Windows platforms or when win32 is unavailable.
        """
        if not _ensure_win32():
            logger.debug("win32 unavailable — skipping popup scan")
            return []

        popups: list[PopupInfo] = []

        def _enum_callback(hwnd: int, _: Any) -> None:
            if not _win32gui.IsWindowVisible(hwnd):
                return
            title = _win32gui.GetWindowText(hwnd)
            if not title:
                return
            title_lower = title.lower()
            for kw in self.popup_keywords:
                if kw.lower() in title_lower:
                    try:
                        rect = _win32gui.GetWindowRect(hwnd)
                        class_name = _win32gui.GetClassName(hwnd)
                    except Exception:
                        rect = (0, 0, 0, 0)
                        class_name = ""
                    popups.append(
                        PopupInfo(
                            hwnd=hwnd,
                            title=title,
                            class_name=class_name,
                            left=rect[0],
                            top=rect[1],
                            right=rect[2],
                            bottom=rect[3],
                            matched_keyword=kw,
                        )
                    )
                    break  # one keyword match per window is enough

        try:
            _win32gui.EnumWindows(_enum_callback, None)
        except Exception as exc:
            logger.error("EnumWindows failed during popup scan: %s", exc)

        if popups:
            logger.debug("Detected %d popup(s): %s", len(popups), [p.title for p in popups])
        return popups

    # ------------------------------------------------------------------
    # Popup dismissal
    # ------------------------------------------------------------------

    def dismiss_popup(self, popup: PopupInfo) -> bool:
        """Attempt to dismiss a popup window.

        Strategy (in order):
          1. Send ``WM_CLOSE`` to the popup.
          2. Send ``VK_ESCAPE`` via ``keybd_event``.
          3. If those fail, try to find and click a "Cancel" / "Close" /
             "OK" button in the popup.

        Returns *True* if the window appears to have been closed.
        """
        if not _ensure_win32():
            logger.warning("win32 unavailable — cannot dismiss popup")
            return False

        logger.info("Dismissing popup: hwnd=%d title=%r", popup.hwnd, popup.title)
        self._total_popup_dismissals += 1

        # --- Strategy 1: WM_CLOSE ---
        try:
            _win32gui.PostMessage(popup.hwnd, _win32con.WM_CLOSE, 0, 0)
            time.sleep(0.3)
            if not _win32gui.IsWindow(popup.hwnd):
                logger.info("Popup dismissed via WM_CLOSE")
                return True
        except Exception as exc:
            logger.debug("WM_CLOSE failed: %s", exc)

        # --- Strategy 2: VK_ESCAPE ---
        try:
            _win32api.keybd_event(0x1B, 0, 0, 0)  # key down
            _win32api.keybd_event(0x1B, 0, _win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.3)
            if not _win32gui.IsWindow(popup.hwnd):
                logger.info("Popup dismissed via Escape key")
                return True
        except Exception as exc:
            logger.debug("Escape key failed: %s", exc)

        # --- Strategy 3: Find & click Cancel / Close / OK button ---
        dismiss_captions = ("cancel", "close", "ok", "no", "&no", "don't send", "ignore")
        child_found = False

        def _button_callback(child_hwnd: int, __: Any) -> None:
            nonlocal child_found
            if child_found:
                return
            try:
                text = _win32gui.GetWindowText(child_hwnd).lower().strip()
                if text and text in dismiss_captions:
                    _win32gui.PostMessage(child_hwnd, _win32con.BM_CLICK, 0, 0)
                    child_found = True
            except Exception:
                pass

        try:
            _win32gui.EnumChildWindows(popup.hwnd, _button_callback, None)
            if child_found:
                time.sleep(0.3)
                if not _win32gui.IsWindow(popup.hwnd):
                    logger.info("Popup dismissed via button click")
                    return True
        except Exception as exc:
            logger.debug("Child button search failed: %s", exc)

        still_alive = _win32gui.IsWindow(popup.hwnd)
        if not still_alive:
            return True

        logger.warning("Failed to dismiss popup hwnd=%d title=%r", popup.hwnd, popup.title)
        return False

    # ------------------------------------------------------------------
    # Fallback / retry with alternative strategy
    # ------------------------------------------------------------------

    def retry_with_fallback(
        self,
        action: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Try an alternative action based on the failure.

        Fallback chains (first available alternative wins):
          - ``click`` → ``click_image`` → ``click_text``
          - ``type_text`` → ``clipboard_paste`` (clipboard + Ctrl+V)

        If the executor is not set, returns a suggestion dict instead.
        """
        action_type = action.get("type", "")
        alternatives = _FALLBACK_MAP.get(action_type, [])
        self._total_fallbacks += 1

        if not alternatives:
            logger.info("No fallback defined for action type %r", action_type)
            return {
                "success": False,
                "error": f"no fallback for {action_type}",
                "fallback_attempted": False,
            }

        for alt_type in alternatives:
            logger.info("Attempting fallback: %s → %s", action_type, alt_type)
            alt_action = self._build_alt_action(action, alt_type)
            if alt_action is None:
                continue

            if self._executor is None:
                return {
                    "success": False,
                    "fallback_suggested": alt_action,
                    "error": "no executor available to run fallback",
                }

            try:
                fallback_result = self._executor.execute(alt_action)
                if isinstance(fallback_result, dict) and fallback_result.get("success"):
                    logger.info("Fallback %s succeeded", alt_type)
                    return {
                        "success": True,
                        "fallback_type": alt_type,
                        "original_type": action_type,
                        "result": fallback_result,
                    }
                logger.debug("Fallback %s did not succeed, trying next", alt_type)
            except Exception as exc:
                logger.warning("Fallback %s raised exception: %s", alt_type, exc)

        return {
            "success": False,
            "error": f"all fallbacks exhausted for {action_type}",
            "fallbacks_tried": alternatives,
        }

    # ------------------------------------------------------------------
    # Retry decision
    # ------------------------------------------------------------------

    def should_retry(self, action_type: str, error: str, attempt: int) -> bool:
        """Return *True* if the action is worth retrying.

        Considers the attempt count, error severity, and action type.
        Non-retryable errors (permission, authentication) always return
        *False*.
        """
        error_lower = error.lower()

        # Never retry these.
        non_retryable = [
            "permission",
            "access denied",
            "access is denied",
            "authentication",
            "unauthorized",
            "login failed",
        ]
        for phrase in non_retryable:
            if phrase in error_lower:
                return False

        if attempt > self.max_retries:
            return False

        return True

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return a dictionary of recovery statistics."""
        return {
            "total_failures": self._total_failures,
            "total_retries": self._total_retries,
            "total_popup_dismissals": self._total_popup_dismissals,
            "total_fallbacks": self._total_fallbacks,
            "total_aborts": self._total_aborts,
            "total_skips": self._total_skips,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "dismiss_popups_enabled": self.dismiss_popups,
            "popup_keywords_count": len(self.popup_keywords),
            "platform": platform.system(),
            "win32_available": _win32gui is not None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_alt_action(
        self,
        original: dict[str, Any],
        alt_type: str,
    ) -> dict[str, Any] | None:
        """Build an alternative action dict from the original action.

        Returns *None* if the alternative cannot be constructed (e.g. missing
        required parameters).
        """
        base = {k: v for k, v in original.items() if k != "type"}
        base["type"] = alt_type

        # For clipboard_paste, include the text payload.
        if alt_type == "clipboard_paste":
            text = original.get("text", "")
            if not text:
                logger.debug("clipboard_paste fallback skipped — no text in original action")
                return None
            base["text"] = text
            base["hotkey"] = "ctrl+v"

        return base
