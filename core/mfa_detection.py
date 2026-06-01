"""Sentinel Desktop v2 — MFA / UAC / credential prompt detector.

Detects multi-factor authentication, User Account Control, and credential
dialogs on the Windows desktop and signals the agent to pause until the user
handles them. This is the desktop equivalent of Sentinel Override's MFA
auto-pause feature.

Detection strategy (first match wins):
  1. **Window title check** — scan for known auth dialog titles.
  2. **OCR text check** — run pytesseract on the screenshot and match
     MFA / UAC / credential text patterns.
  3. **UIA check** — walk the accessibility tree for password edit controls
     or text elements that match auth prompts.

Thread-safe. Graceful no-op on non-Windows. Uses only PIL for screenshot
analysis, pytesseract for OCR (optional), and uiautomation for UIA (optional).
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform gate
# ---------------------------------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"

# ---------------------------------------------------------------------------
# Integration constants
# ---------------------------------------------------------------------------

AUTH_WINDOW_TITLES: list[tuple[str, str]] = [
    ("Windows Security", "credential"),
    ("User Account Control", "uac"),
    ("UAC", "uac"),
    ("Enter your password", "credential"),
    ("Verify your identity", "mfa"),
    ("Sign in", "credential"),
    ("Microsoft account", "credential"),
    ("Two-factor authentication", "2fa"),
    ("2FA", "2fa"),
    ("Enter the code", "2fa"),
    ("Authentication required", "mfa"),
    ("Windows Hello", "pin"),
    ("Security verification", "mfa"),
    ("Credential Manager", "credential"),
    ("Enter credentials", "credential"),
    ("PIN", "pin"),
]

# Generic substrings — if *any* window title contains these, classify.
_GENERIC_TITLE_KEYWORDS: list[tuple[str, str]] = [
    ("credential", "credential"),
    ("authentication", "mfa"),
]

MFA_PATTERNS: list[tuple[str, str]] = [
    ("verify your identity", "mfa"),
    ("enter the code", "2fa"),
    ("approve sign-in", "mfa"),
    ("approve the request", "mfa"),
    ("6-digit code", "2fa"),
    ("authenticator app", "mfa"),
    ("otp", "mfa"),
    ("one-time password", "mfa"),
    ("do you want to allow", "uac"),
    ("user account control", "uac"),
    ("enter your password", "credential"),
    ("authentication required", "mfa"),
    ("security verification", "mfa"),
    ("two-step verification", "mfa"),
    ("two-factor authentication", "2fa"),
    ("enter your pin", "pin"),
    ("windows hello", "pin"),
    ("sign-in attempt", "mfa"),
    ("unusual sign-in", "mfa"),
    ("push notification", "mfa"),
]

# Keywords that strongly indicate a UAC prompt specifically.
UAC_KEYWORDS: list[str] = [
    "user account control",
    "do you want to allow",
    "uac",
    "allow this app to make changes",
    "do you want to allow this app",
    "windows needs your permission",
    "an unidentified program wants access",
]

# ---------------------------------------------------------------------------
# Optional-dependency probes
# ---------------------------------------------------------------------------

_TESSERACT_OK: bool | None = None
_pytesseract = None  # type: ignore[assignment]


def _have_tesseract() -> bool:
    """Lazily probe for pytesseract + Tesseract binary."""
    global _TESSERACT_OK, _pytesseract
    if _TESSERACT_OK is not None:
        return _TESSERACT_OK
    try:
        import pytesseract  # type: ignore

        pytesseract.get_tesseract_version()
        _pytesseract = pytesseract
        _TESSERACT_OK = True
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        logger.debug("MFA OCR tier disabled — pytesseract unavailable (%s)", exc)
        _TESSERACT_OK = False
    return _TESSERACT_OK


_UIA_AVAILABLE: bool | None = None
_auto = None  # uiautomation module ref


def _have_uia() -> bool:
    """Lazily probe for the *uiautomation* package."""
    global _UIA_AVAILABLE, _auto
    if _UIA_AVAILABLE is not None:
        return _UIA_AVAILABLE
    try:
        import uiautomation as auto  # type: ignore

        _auto = auto
        _UIA_AVAILABLE = True
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        logger.debug("MFA UIA tier disabled — uiautomation unavailable (%s)", exc)
        _UIA_AVAILABLE = False
    return _UIA_AVAILABLE


# ---------------------------------------------------------------------------
# DetectionResult
# ---------------------------------------------------------------------------


@dataclass
class DetectionResult:
    """Represents the outcome of an MFA / UAC / credential detection pass.

    Attributes:
        detected: Whether an auth prompt was found.
        type: Detection category — ``"mfa"`` | ``"uac"`` | ``"credential"``
              | ``"2fa"`` | ``"pin"`` | ``""``.
        prompt_text: The text shown in the prompt (extracted via OCR or title).
        window_title: The window title of the auth dialog.
        confidence: Detection confidence in ``[0, 1]``.
        action: Recommended action — ``"pause_agent"`` | ``"notify_user"``
                | ``"none"``.

    """

    detected: bool = False
    type: str = ""
    prompt_text: str = ""
    window_title: str = ""
    confidence: float = 0.0
    action: str = "none"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_result() -> DetectionResult:
    """Return a fresh, undetected result."""
    return DetectionResult()


def _classify_action(det_type: str, confidence: float) -> str:
    """Decide the recommended action from detection type and confidence."""
    if not det_type or confidence < 0.3:
        return "none"
    # UAC and credential prompts always pause the agent — they block
    # input anyway so there's nothing the agent can do.
    if det_type in ("uac", "credential"):
        return "pause_agent"
    if det_type in ("mfa", "2fa", "pin") and confidence >= 0.5:
        return "pause_agent"
    return "notify_user"


# ---------------------------------------------------------------------------
# Window title scanning
# ---------------------------------------------------------------------------


def _get_window_titles() -> list[str]:
    """Return titles of all visible windows (Windows-only, best-effort)."""
    titles: list[str] = []
    if not _IS_WINDOWS:
        return titles
    try:
        import win32gui  # type: ignore

        def _enum(hwnd: int, _lparam: int) -> None:
            """EnumWindows callback — collect visible window titles."""
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    titles.append(title)

        win32gui.EnumWindows(_enum, None)
    except (OSError, AttributeError, RuntimeError) as exc:
        logger.warning("win32gui EnumWindows failed, falling back: %s", exc)
        # Fall back to our own window_manager if win32gui is unavailable.
        try:
            from core import window_manager as wm

            for w in wm.list_windows():
                t = w.get("title", "")
                if t:
                    titles.append(t)
        except (ImportError, OSError, AttributeError, RuntimeError) as exc:
            logger.warning("window title enumeration failed: %s", exc)
    return titles


def _match_window_title(titles: list[str]) -> DetectionResult | None:
    """Check *titles* against :data:`AUTH_WINDOW_TITLES`.

    Returns the first matching :class:`DetectionResult`, or ``None``.
    """
    for title in titles:
        tl = title.lower()
        # Specific known titles
        for substring, det_type in AUTH_WINDOW_TITLES:
            if substring.lower() in tl:
                return DetectionResult(
                    detected=True,
                    type=det_type,
                    prompt_text=title,
                    window_title=title,
                    confidence=0.95,
                    action="pause_agent",
                )
        # Generic keyword match
        for keyword, det_type in _GENERIC_TITLE_KEYWORDS:
            if keyword in tl:
                return DetectionResult(
                    detected=True,
                    type=det_type,
                    prompt_text=title,
                    window_title=title,
                    confidence=0.85,
                    action="pause_agent",
                )
    return None


# ---------------------------------------------------------------------------
# OCR text scanning
# ---------------------------------------------------------------------------


def _ocr_check(screenshot: Image.Image) -> DetectionResult | None:
    """OCR the *screenshot* and scan for MFA/UAC text patterns.

    Returns a :class:`DetectionResult` on the first match, or ``None``.
    """
    if not _have_tesseract():
        return None

    try:
        from core.ocr import preprocess_for_ocr

        processed = preprocess_for_ocr(screenshot)
        text = _pytesseract.image_to_string(processed)  # type: ignore[union-attr]
    except (OSError, RuntimeError, ValueError) as exc:
        logger.debug("MFA OCR scan failed: %s", exc)
        return None

    if not text:
        return None

    text_lower = text.lower()

    for pattern, det_type in MFA_PATTERNS:
        if pattern.lower() in text_lower:
            # Boost confidence if multiple patterns match
            match_count = sum(1 for p, _ in MFA_PATTERNS if p.lower() in text_lower)
            confidence = min(0.6 + match_count * 0.08, 0.95)

            # UAC-specific boost
            is_uac = any(kw in text_lower for kw in UAC_KEYWORDS)
            if is_uac:
                det_type = "uac"
                confidence = max(confidence, 0.85)

            # Extract a short prompt excerpt around the match
            excerpt = _extract_excerpt(text, pattern)

            return DetectionResult(
                detected=True,
                type=det_type,
                prompt_text=excerpt,
                window_title="",
                confidence=confidence,
                action=_classify_action(det_type, confidence),
            )

    return None


def _extract_excerpt(text: str, pattern: str, context_chars: int = 80) -> str:
    """Return a short text excerpt centred on *pattern* within *text*."""
    idx = text.lower().find(pattern.lower())
    if idx < 0:
        return text[:120].strip()
    start = max(0, idx - context_chars // 2)
    end = min(len(text), idx + len(pattern) + context_chars // 2)
    excerpt = text[start:end].strip()
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(text):
        excerpt = excerpt + "…"
    return excerpt


# ---------------------------------------------------------------------------
# UIA scanning
# ---------------------------------------------------------------------------


def _uia_check() -> DetectionResult | None:
    """Walk the accessibility tree for password fields / auth text elements.

    Returns a :class:`DetectionResult` if an auth prompt is identified,
    or ``None``.
    """
    if not _have_uia() or not _IS_WINDOWS:
        return None

    try:
        auto = _auto  # type: ignore[union-attr]
        root = auto.GetRootControl()
        for win in root.GetChildren():
            try:
                title = win.Name or ""
            except (OSError, AttributeError, RuntimeError) as exc:
                logger.debug("Failed to read window name: %s", exc)
                title = ""

            # Skip windows already matched by title — the title checker has
            # higher confidence and handles those.
            tl = title.lower()
            if any(substr.lower() in tl for substr, _ in AUTH_WINDOW_TITLES):
                continue

            result = _scan_window_for_auth(win, title)
            if result is not None:
                return result

    except (OSError, AttributeError, RuntimeError) as exc:
        logger.debug("MFA UIA scan failed: %s", exc)

    return None


def _scan_children_for_auth(
    win: Any,
) -> tuple[bool, bool, list[str]]:
    """Scan a window's immediate children for password fields and MFA text patterns.

    Returns:
        ``(found_password, found_auth_text, prompt_text_parts)``

    """
    found_password = False
    found_auth_text = False
    prompt_text_parts: list[str] = []

    for ctrl in win.GetChildren():
        ctrl_type = _get_control_type(ctrl)
        if ctrl_type is None:
            continue
        if ctrl_type == "EditControl":
            if _check_password_control(ctrl):
                found_password = True
        if ctrl_type in ("TextControl", "StaticControl"):
            auth_found, text_part = _check_text_control_for_auth(ctrl)
            if auth_found:
                found_auth_text = True
                prompt_text_parts.append(text_part)

    return found_password, found_auth_text, prompt_text_parts


def _get_control_type(ctrl: Any) -> str | None:
    """Get the control type, handling exceptions."""
    try:
        return ctrl.ControlTypeName
    except (OSError, AttributeError, RuntimeError) as exc:
        logger.debug("Failed to read control type: %s", exc)
        return None


def _check_password_control(ctrl: Any) -> bool:
    """Check if a control is a password field."""
    try:
        return getattr(ctrl, "IsPassword", False)
    except (OSError, AttributeError, RuntimeError) as exc:
        logger.debug("IsPassword check failed: %s", exc)
        return False


def _check_text_control_for_auth(ctrl: Any) -> tuple[bool, str]:
    """Check if a text control contains auth-related text."""
    try:
        text = (ctrl.Name or "").strip()
        if not text:
            return False, ""
        tl_text = text.lower()
        for pattern, _det_type in MFA_PATTERNS:
            if pattern.lower() in tl_text:
                return True, text[:120]
        return False, ""
    except (OSError, AttributeError, RuntimeError) as exc:
        logger.debug("Text pattern matching failed: %s", exc)
        return False, ""


def _scan_window_for_auth(win: Any, title: str) -> DetectionResult | None:
    """Scan one top-level window's immediate children for auth indicators.

    Checks for password ``EditControl`` fields and text controls matching
    known MFA/credential patterns. Returns a :class:`DetectionResult` on
    match, or ``None``.
    """
    found_password, found_auth_text, prompt_text_parts = _scan_children_for_auth(win)
    if not (found_password or found_auth_text):
        return None

    det_type = "credential" if found_password else "mfa"
    prompt = " | ".join(prompt_text_parts[:3]) if prompt_text_parts else title
    confidence = 0.8 if found_password else 0.7
    return DetectionResult(
        detected=True,
        type=det_type,
        prompt_text=prompt,
        window_title=title,
        confidence=confidence,
        action=_classify_action(det_type, confidence),
    )


# ---------------------------------------------------------------------------
# MFADetector
# ---------------------------------------------------------------------------


class MFADetector:
    """Detects MFA / UAC / credential prompts on the desktop.

    Typical usage::

        detector = MFADetector()

        # One-shot check:
        result = detector.check_screen(screenshot_image)
        if result.detected:
            print(f"MFA prompt detected: {result.type}")

        # Background monitoring:
        def on_mfa(det_type: str, prompt_text: str) -> None:
            engine.pause(reason=f"MFA: {det_type}")

        detector.start_monitoring(on_mfa)
        # ... later ...
        detector.stop_monitoring()

    All public methods are thread-safe.
    """

    def __init__(self, cooldown_seconds: float = 10.0) -> None:
        """Initialize the MFA detector.

        Args:
            cooldown_seconds: Minimum seconds between repeated detections of
                the same prompt (prevents notification spam).

        """
        self._lock = threading.Lock()
        self._last_detection: DetectionResult | None = None
        self._last_detection_time: float = 0.0
        self._last_prompt_sig: str = ""  # for cooldown dedup
        self._cooldown = cooldown_seconds

        # Monitoring state
        self._monitor_thread: threading.Thread | None = None
        self._monitor_stop = threading.Event()
        self._callback: Callable[[str, str], None] | None = None
        self._interval: float = 2.0

    # ------------------------------------------------------------------
    # Public detection methods
    # ------------------------------------------------------------------

    def check_screen(self, screenshot: Image.Image) -> DetectionResult:
        """Analyse a *screenshot* for MFA / UAC / credential prompts.

        Runs three detection tiers in order (window title → OCR → UIA);
        the first match wins.

        Args:
            screenshot: A PIL ``Image`` of the desktop.

        Returns:
            A :class:`DetectionResult` describing what was found.

        """
        if not _IS_WINDOWS:
            return _empty_result()

        # Tier 1: Window title check (fast, no image processing).
        result = self.check_window_titles()
        if result.detected:
            return result

        # Tier 2: OCR text check.
        result = _ocr_check(screenshot)
        if result is not None and result.detected:
            with self._lock:
                self._last_detection = result
                self._last_detection_time = time.monotonic()
            return result

        # Tier 3: UIA check.
        result = _uia_check()
        if result is not None and result.detected:
            with self._lock:
                self._last_detection = result
                self._last_detection_time = time.monotonic()
            return result

        # Nothing detected.
        with self._lock:
            self._last_detection = None
        return _empty_result()

    def check_window_titles(self) -> DetectionResult:
        """Check currently open window titles for known auth dialogs.

        Returns:
            A :class:`DetectionResult`. This method does not perform OCR.

        """
        if not _IS_WINDOWS:
            return _empty_result()

        titles = _get_window_titles()
        result = _match_window_title(titles)
        if result is not None:
            with self._lock:
                self._last_detection = result
                self._last_detection_time = time.monotonic()
            return result

        return _empty_result()

    # ------------------------------------------------------------------
    # Background monitoring
    # ------------------------------------------------------------------

    def start_monitoring(
        self,
        callback: Callable[[str, str], None],
        interval: float = 2.0,
    ) -> None:
        """Start background polling for auth prompts.

        Spawns a daemon thread that checks for MFA/UAC prompts every
        *interval* seconds. When a prompt is detected, *callback* is
        called with ``(detection_type, prompt_text)``.

        If monitoring is already active, the old thread is stopped first.

        Args:
            callback: ``callback(type_str, prompt_text)`` — called from
                the monitor thread when a prompt is detected.
            interval: Polling interval in seconds (default 2.0).

        """
        self.stop_monitoring()

        self._callback = callback
        self._interval = max(0.5, interval)
        self._monitor_stop.clear()

        thread = threading.Thread(
            target=self._monitor_loop,
            name="mfa-detector",
            daemon=True,
        )
        self._monitor_thread = thread
        thread.start()
        logger.info(
            "MFA monitoring started (interval=%.1fs, cooldown=%.1fs)",
            self._interval,
            self._cooldown,
        )

    def stop_monitoring(self) -> None:
        """Stop the background monitoring thread (if running)."""
        self._monitor_stop.set()
        thread = self._monitor_thread
        self._monitor_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._interval + 2.0)
            logger.info("MFA monitoring stopped")

    def get_last_detection(self) -> DetectionResult | None:
        """Return the most recent :class:`DetectionResult`, or ``None``."""
        with self._lock:
            return self._last_detection

    # ------------------------------------------------------------------
    # Monitor loop (runs on background thread)
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Background loop: poll for auth prompts and invoke callback."""
        # Import here to avoid circular-import issues at module level.
        from core.screenshot import capture_screen

        was_detected = False

        while not self._monitor_stop.is_set():
            try:
                result = self._poll_once(capture_screen)
            except (OSError, RuntimeError, ValueError) as exc:
                logger.debug("MFA monitor poll error: %s", exc)
                result = _empty_result()

            was_detected = self._handle_poll_result(result, time.monotonic(), was_detected)
            self._monitor_stop.wait(timeout=self._interval)

    def _handle_poll_result(
        self, result: DetectionResult, now: float, was_detected: bool
    ) -> bool:
        """Process one poll result; update state and invoke callback. Returns new was_detected."""
        if result.detected:
            sig = f"{result.type}:{result.window_title}:{result.prompt_text[:40]}"
            with self._lock:
                in_cooldown = (
                    sig == self._last_prompt_sig
                    and (now - self._last_detection_time) < self._cooldown
                )
            if not in_cooldown:
                with self._lock:
                    self._last_detection = result
                    self._last_detection_time = now
                    self._last_prompt_sig = sig
                if self._callback is not None:
                    try:
                        self._callback(result.type, result.prompt_text)
                    except (RuntimeError, OSError, ValueError) as exc:
                        logger.warning("MFA callback error: %s", exc)
                logger.info(
                    "MFA detected: type=%s confidence=%.2f title=%r",
                    result.type,
                    result.confidence,
                    result.window_title[:60],
                )
                return True
        elif was_detected:
            logger.info("MFA prompt no longer visible — auto-resume")
            with self._lock:
                self._last_detection = None
                self._last_prompt_sig = ""
            return False
        return was_detected

    def _poll_once(
        self,
        capture_fn: Callable[[], Image.Image],
    ) -> DetectionResult:
        """Execute a single detection pass.

        Args:
            capture_fn: Callable returning a PIL screenshot image.

        Returns:
            A :class:`DetectionResult`.

        """
        # Tier 1: Window title
        result = self.check_window_titles()
        if result.detected:
            return result

        # Tier 2: OCR
        try:
            screenshot = capture_fn()
        except (OSError, RuntimeError) as exc:
            logger.debug("MFA monitor screenshot failed: %s", exc)
            screenshot = None

        if screenshot is not None:
            ocr_result = _ocr_check(screenshot)
            if ocr_result is not None and ocr_result.detected:
                return ocr_result

        # Tier 3: UIA
        uia_result = _uia_check()
        if uia_result is not None and uia_result.detected:
            return uia_result

        return _empty_result()
