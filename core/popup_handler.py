"""
Sentinel Desktop v3.1 -- Automatic Popup Dialog Detection and Dismissal.

Detects and dismisses common popup dialogs that block desktop automation.
Uses screenshot + OCR to identify popup text and matches against a library
of known popup patterns (UAC, save prompts, error dialogs, certificate
warnings, update notifications, print dialogs, etc.).

Each pattern defines:
  - regex for title bar text
  - regex for body text
  - default dismissal action (button text to click or keyboard shortcut)

The module is pure-detection -- it reports what it found and what action
to take. The engine loop decides whether to auto-dismiss or escalate.

Typical usage::

    from core.popup_handler import PopupHandler

    handler = PopupHandler()
    result = handler.check_and_dismiss(screenshot)
    if result.detected:
        print(f"Popup: {result.popup_type} — {result.dismiss_action}")
"""

from __future__ import annotations

import logging
import platform
import re
import time
from dataclasses import dataclass

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform gate
# ---------------------------------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"

# ---------------------------------------------------------------------------
# PopupPattern
# ---------------------------------------------------------------------------


@dataclass
class PopupPattern:
    """Definition of a known popup dialog type.

    Attributes:
        name: Human-readable pattern name (e.g. ``"save_prompt"``).
        title_regex: Regex applied to the popup's title bar text.
            Empty string means "match anything" (skip title check).
        body_regex: Regex applied to OCR'd body text of the popup.
            Empty string means "match anything" (skip body check).
        dismiss_action: How to dismiss the popup. Either a button label
            like ``"Don't Save"`` or a keyboard shortcut like ``"escape"``.
        dismiss_type: ``"button"`` or ``"key"``.
        confidence_base: Base confidence when this pattern matches (0-1).
        description: Short human-readable description.
    """

    name: str
    title_regex: str
    body_regex: str
    dismiss_action: str
    dismiss_type: str = "button"  # "button" or "key"
    confidence_base: float = 0.85
    description: str = ""

    def __post_init__(self) -> None:
        """Compile title and body regex patterns eagerly for fast matching."""
        # Compile regex patterns eagerly for reuse
        self._title_pat = re.compile(self.title_regex, re.IGNORECASE) if self.title_regex else None
        self._body_pat = re.compile(self.body_regex, re.IGNORECASE) if self.body_regex else None

    def match(self, title_text: str, body_text: str) -> float:
        """Return a confidence score (0-1) if this pattern matches, else 0.

        Both title and body regexes must match (if defined). The confidence
        is boosted when *both* title and body match vs. only one.
        """
        title_match = self._title_pat.search(title_text) if self._title_pat else True
        body_match = self._body_pat.search(body_text) if self._body_pat else True

        if not title_match or not body_match:
            return 0.0

        # Confidence boost when both dimensions match
        has_title = self._title_pat is not None
        has_body = self._body_pat is not None

        if has_title and has_body:
            return min(self.confidence_base + 0.10, 1.0)
        elif has_title or has_body:
            return self.confidence_base
        else:
            # No regexes defined — wildcard pattern, lower confidence
            return 0.3


# ---------------------------------------------------------------------------
# Built-in popup patterns
# ---------------------------------------------------------------------------

BUILTIN_PATTERNS: list[PopupPattern] = [
    # ── Save / close prompts ────────────────────────────────────────────
    PopupPattern(
        name="save_changes",
        title_regex=r"save changes|do you want to save|save\?",
        body_regex=r"save (changes|before|your work)|unsaved",
        dismiss_action="Don't Save",
        dismiss_type="button",
        confidence_base=0.85,
        description="Application save-changes-before-close prompt",
    ),
    PopupPattern(
        name="save_changes_alt",
        title_regex=r"confirm|close",
        body_regex=r"do you want to save (changes|the file)|unsaved changes",
        dismiss_action="Don't Save",
        dismiss_type="button",
        confidence_base=0.80,
        description="Alternative save-changes wording",
    ),
    # ── Error dialogs ───────────────────────────────────────────────────
    PopupPattern(
        name="error_dialog",
        title_regex=r"error|exception|fatal|critical",
        body_regex=r"an error (has )?occurred|exception|failed to|could not|unhandled",
        dismiss_action="OK",
        dismiss_type="button",
        confidence_base=0.80,
        description="Generic error dialog",
    ),
    PopupPattern(
        name="error_dialog_close",
        title_regex=r"error|warning|problem",
        body_regex=r"",
        dismiss_action="escape",
        dismiss_type="key",
        confidence_base=0.60,
        description="Error dialog with Escape key fallback",
    ),
    # ── Certificate warnings ────────────────────────────────────────────
    PopupPattern(
        name="certificate_warning",
        title_regex=r"certificate|security (warning|alert|risk)",
        body_regex=r"certificate|security certificate|issuer|not trusted|"
        r"self-signed|untrusted|connection is not (secure|private)|"
        r"there is a problem|your connection is not",
        dismiss_action="Continue",
        dismiss_type="button",
        confidence_base=0.80,
        description="SSL/TLS certificate warning in browser",
    ),
    PopupPattern(
        name="certificate_warning_advanced",
        title_regex=r"certificate|security|warning",
        body_regex=r"proceed|continue to.*unsafe|accept the risk|i understand",
        dismiss_action="Proceed",
        dismiss_type="button",
        confidence_base=0.75,
        description="Browser advanced certificate bypass prompt",
    ),
    # ── Update notifications ────────────────────────────────────────────
    PopupPattern(
        name="update_notification",
        title_regex=r"update(s)? available|software update|check for updates|"
        r"new version|upgrade",
        body_regex=r"(new )?update|download( and install)?|remind me|later|"
        r"skip (this )?update|version \d",
        dismiss_action="Later",
        dismiss_type="button",
        confidence_base=0.80,
        description="Software update notification",
    ),
    PopupPattern(
        name="update_notification_close",
        title_regex=r"update|upgrade",
        body_regex=r"",
        dismiss_action="escape",
        dismiss_type="key",
        confidence_base=0.55,
        description="Update popup with Escape key fallback",
    ),
    # ── Print dialogs ───────────────────────────────────────────────────
    PopupPattern(
        name="print_dialog",
        title_regex=r"print",
        body_regex=r"printer|copies|pages|print range|paper size|"
        r"select printer|layout|orientation",
        dismiss_action="escape",
        dismiss_type="key",
        confidence_base=0.80,
        description="Print dialog",
    ),
    # ── UAC (light -- not full credential, just Yes/No elevation) ───────
    PopupPattern(
        name="uac_prompt",
        title_regex=r"user account control|uac",
        body_regex=r"do you want to (allow|let)|allow.*to make changes|"
        r"needs your permission",
        dismiss_action="Yes",
        dismiss_type="button",
        confidence_base=0.90,
        description="User Account Control elevation prompt",
    ),
    # ── Confirm / overwrite dialogs ─────────────────────────────────────
    PopupPattern(
        name="confirm_replace",
        title_regex=r"(confirm|replace|overwrite) (file|folder|save)",
        body_regex=r"already exists|overwrite|replace (the )?existing|"
        r"same (name|location)",
        dismiss_action="Yes",
        dismiss_type="button",
        confidence_base=0.80,
        description="File overwrite confirmation",
    ),
    PopupPattern(
        name="confirm_delete",
        title_regex=r"(confirm|delete) (file|folder|item)",
        body_regex=r"(are you )?sure (you want )?to delete|permanently|"
        r"move to (the )?recycle|cannot be undone",
        dismiss_action="Yes",
        dismiss_type="button",
        confidence_base=0.80,
        description="Delete confirmation dialog",
    ),
    # ── "Are you sure you want to leave?" ───────────────────────────────
    PopupPattern(
        name="leave_page",
        title_regex=r"(leave|stay on) (this )?page|confirm navigation",
        body_regex=r"(leave|stay on) (this )?page|unsaved (data|changes)|"
        r"changes (you made|will be lost)",
        dismiss_action="Leave",
        dismiss_type="button",
        confidence_base=0.80,
        description="Browser leave-page confirmation",
    ),
    # ── Open / save file dialog (in the way) ────────────────────────────
    PopupPattern(
        name="file_dialog",
        title_regex=r"(open|save|browse) (file|as|for)",
        body_regex=r"file name|look in|folder|browse",
        dismiss_action="escape",
        dismiss_type="key",
        confidence_base=0.70,
        description="File open/save dialog blocking automation",
    ),
    # ── Network / connectivity ──────────────────────────────────────────
    PopupPattern(
        name="network_error",
        title_regex=r"(network|connection) (error|failed|problem|timed? out)",
        body_regex=r"(unable to|cannot) connect|network (error|unreachable)|"
        r"timed? out|server (not found|refused|unreachable)|dns|proxy",
        dismiss_action="OK",
        dismiss_type="button",
        confidence_base=0.75,
        description="Network error popup",
    ),
    # ── Privacy / consent popups ────────────────────────────────────────
    PopupPattern(
        name="privacy_consent",
        title_regex=r"privacy|consent|cookies|terms|gdpr",
        body_regex=r"accept (all )?(cookies|terms)|agree|consent|"
        r"privacy policy|data (collection|processing)",
        dismiss_action="Accept",
        dismiss_type="button",
        confidence_base=0.70,
        description="Privacy/cookie consent popup",
    ),
]

# ---------------------------------------------------------------------------
# PopupDetectionResult
# ---------------------------------------------------------------------------


@dataclass
class PopupDetectionResult:
    """Result of a popup detection and dismissal attempt.

    Attributes:
        detected: Whether a popup was detected.
        popup_type: Pattern name that matched (e.g. ``"save_changes"``).
        confidence: Detection confidence in ``[0, 1]``.
        dismiss_action: The recommended dismiss action (button label or key).
        dismiss_type: ``"button"`` or ``"key"``.
        title_text: Extracted title bar text.
        body_text: Extracted body text (truncated).
        dismissed: Whether the popup was successfully dismissed.
        pattern_description: Human-readable description of the matched pattern.
    """

    detected: bool = False
    popup_type: str = ""
    confidence: float = 0.0
    dismiss_action: str = ""
    dismiss_type: str = "button"
    title_text: str = ""
    body_text: str = ""
    dismissed: bool = False
    pattern_description: str = ""


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
    except Exception as exc:
        logger.debug("PopupHandler OCR disabled -- pytesseract unavailable (%s)", exc)
        _TESSERACT_OK = False
    return _TESSERACT_OK


# ---------------------------------------------------------------------------
# OCR helper
# ---------------------------------------------------------------------------


def _ocr_text(image: Image.Image) -> str:
    """OCR an image and return extracted text. Returns empty string on failure."""
    if not _have_tesseract():
        return ""
    try:
        from core.ocr import preprocess_for_ocr

        processed = preprocess_for_ocr(image)
    except ImportError:
        processed = image
    except (OSError, RuntimeError, ValueError) as exc:
        logger.debug("PopupHandler preprocess_for_ocr failed: %s", exc)
        processed = image

    try:
        return _pytesseract.image_to_string(processed)  # type: ignore[union-attr]
    except Exception as exc:
        logger.debug("PopupHandler OCR failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Window title extraction (Windows-only)
# ---------------------------------------------------------------------------


def _get_foreground_window_title() -> str:
    """Return the title of the foreground window (Windows-only)."""
    if not _IS_WINDOWS:
        return ""
    try:
        import win32gui  # type: ignore

        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd) or ""
    except (ImportError, OSError, AttributeError):
        pass
    try:
        from core import window_manager as wm

        windows = wm.list_windows()
        if windows:
            return windows[0].get("title", "")
    except (ImportError, OSError, AttributeError):
        pass
    return ""


# ---------------------------------------------------------------------------
# PopupHandler
# ---------------------------------------------------------------------------


class PopupHandler:
    """Detects and dismisses common popup dialogs that block automation.

    The main entry point is :meth:`check_and_dismiss`, which:

    1. Captures (or accepts) a screenshot.
    2. OCRs the screen for title and body text.
    3. Matches against registered popup patterns.
    4. Returns a :class:`PopupDetectionResult` with the best match.

    The engine loop can then auto-dismiss the popup or escalate to the user.

    Usage::

        handler = PopupHandler()
        result = handler.check_and_dismiss(screenshot)
        if result.detected:
            handler.dismiss(result)
    """

    # Minimum confidence to consider a popup "detected"
    DETECTION_THRESHOLD = 0.55

    # Cooldown between repeated identical detections (seconds)
    COOLDOWN_SECONDS = 5.0

    # Maximum dismiss attempts for the same popup before giving up
    MAX_DISMISS_ATTEMPTS = 3

    def __init__(
        self,
        patterns: list[PopupPattern] | None = None,
        auto_dismiss: bool = False,
    ) -> None:
        """Initialise the popup handler.

        Args:
            patterns: Custom list of patterns. If ``None``, uses
                :data:`BUILTIN_PATTERNS`.
            auto_dismiss: If ``True``, :meth:`check_and_dismiss` will
                attempt to dismiss popups automatically.
        """
        self._patterns = patterns if patterns is not None else list(BUILTIN_PATTERNS)
        self.auto_dismiss = auto_dismiss

        # Cooldown state
        self._last_popup_type: str = ""
        self._last_detection_time: float = 0.0
        self._dismiss_attempts: int = 0

    # ------------------------------------------------------------------
    # Pattern management
    # ------------------------------------------------------------------

    def add_pattern(self, pattern: PopupPattern) -> None:
        """Register an additional popup pattern."""
        self._patterns.append(pattern)

    def remove_pattern(self, name: str) -> bool:
        """Remove a pattern by name. Returns True if found and removed."""
        before = len(self._patterns)
        self._patterns = [p for p in self._patterns if p.name != name]
        return len(self._patterns) < before

    @property
    def patterns(self) -> list[PopupPattern]:
        """Return a copy of the current pattern list."""
        return list(self._patterns)

    # ------------------------------------------------------------------
    # Core detection
    # ------------------------------------------------------------------

    def detect(
        self,
        title_text: str,
        body_text: str,
    ) -> PopupDetectionResult:
        """Match OCR text against registered popup patterns.

        Args:
            title_text: Text extracted from the popup's title bar.
            body_text: Text extracted from the popup's body area.

        Returns:
            The best-matching :class:`PopupDetectionResult`, or an
            undetected result if nothing matches above threshold.
        """
        best_score = 0.0
        best_pattern: PopupPattern | None = None

        for pattern in self._patterns:
            score = pattern.match(title_text, body_text)
            if score > best_score:
                best_score = score
                best_pattern = pattern

        if best_score < self.DETECTION_THRESHOLD or best_pattern is None:
            return PopupDetectionResult()

        return PopupDetectionResult(
            detected=True,
            popup_type=best_pattern.name,
            confidence=best_score,
            dismiss_action=best_pattern.dismiss_action,
            dismiss_type=best_pattern.dismiss_type,
            title_text=title_text[:200],
            body_text=body_text[:500],
            pattern_description=best_pattern.description,
        )

    # ------------------------------------------------------------------
    # Screenshot-based detection
    # ------------------------------------------------------------------

    def detect_from_screenshot(
        self,
        screenshot: Image.Image,
    ) -> PopupDetectionResult:
        """OCR a screenshot and detect popup dialogs.

        This is the primary detection method for headless / non-Windows
        environments. It OCRs the entire screenshot and runs pattern
        matching on the extracted text.

        Args:
            screenshot: PIL Image of the screen.

        Returns:
            A :class:`PopupDetectionResult`.
        """
        ocr_output = _ocr_text(screenshot)
        if not ocr_output or not ocr_output.strip():
            return PopupDetectionResult()

        # Heuristic split: first non-empty line is "title", rest is "body".
        lines = [line.strip() for line in ocr_output.splitlines() if line.strip()]
        # Defensive: ``ocr_output.strip()`` above is already truthy here and every
        # ``splitlines()`` boundary is whitespace, so ``lines`` is necessarily
        # non-empty — but keep the guard in case ``_ocr_text`` ever changes.
        if not lines:  # pragma: no cover
            return PopupDetectionResult()

        title_text = lines[0] if lines else ""
        body_text = " ".join(lines[1:]) if len(lines) > 1 else ""

        return self.detect(title_text, body_text)

    # ------------------------------------------------------------------
    # Combined check + optional dismiss
    # ------------------------------------------------------------------

    def check_and_dismiss(
        self,
        screenshot: Image.Image | None = None,
    ) -> PopupDetectionResult:
        """Check for popup dialogs and optionally dismiss them.

        This is the main entry point for the engine loop. It:

        1. Captures a screenshot if not provided.
        2. Gets the foreground window title (Windows-only).
        3. OCRs the screenshot.
        4. Matches against popup patterns.
        5. If ``auto_dismiss=True``, attempts to dismiss the popup.
        6. Enforces a cooldown to avoid re-dismissing the same popup.

        Args:
            screenshot: Optional PIL Image. If ``None``, captures one.

        Returns:
            A :class:`PopupDetectionResult` with detection and dismissal
            status.
        """
        inputs = self._prepare_detection_inputs(screenshot)
        if inputs is None:
            return PopupDetectionResult()
        title_text, body_text = inputs

        result = self.detect(title_text, body_text)
        if not result.detected:
            self._dismiss_attempts = 0
            return result

        return self._apply_cooldown_and_dismiss(result)

    def _prepare_detection_inputs(
        self, screenshot: Image.Image | None
    ) -> tuple[str, str] | None:
        """Capture screenshot (if needed), OCR it, and extract title/body text.

        Returns:
            (title_text, body_text) on success, or None if screenshot capture fails.
        """
        if screenshot is None:
            try:
                from core.screenshot import capture_screen

                screenshot = capture_screen()
            except Exception as exc:
                logger.debug("PopupHandler screenshot capture failed: %s", exc)
                return None

        title_text = _get_foreground_window_title()
        ocr_output = _ocr_text(screenshot)
        lines = (
            [line.strip() for line in ocr_output.splitlines() if line.strip()] if ocr_output else []
        )
        if not title_text and lines:
            title_text = lines[0]
        body_text = " ".join(lines[1:]) if len(lines) > 1 else ""
        return title_text, body_text

    def _apply_cooldown_and_dismiss(self, result: PopupDetectionResult) -> PopupDetectionResult:
        """Apply cooldown guard and conditionally auto-dismiss a detected popup."""
        now = time.monotonic()
        if (
            result.popup_type == self._last_popup_type
            and (now - self._last_detection_time) < self.COOLDOWN_SECONDS
        ):
            logger.debug(
                "PopupHandler: cooldown active for %s (%.1fs remaining)",
                result.popup_type,
                self.COOLDOWN_SECONDS - (now - self._last_detection_time),
            )
            result.dismissed = False
            return result

        self._last_popup_type = result.popup_type
        self._last_detection_time = now

        if self.auto_dismiss and self._dismiss_attempts < self.MAX_DISMISS_ATTEMPTS:
            result = self.dismiss(result)

        return result

    # ------------------------------------------------------------------
    # Dismissal
    # ------------------------------------------------------------------

    def dismiss(self, result: PopupDetectionResult) -> PopupDetectionResult:
        """Attempt to dismiss a detected popup.

        Dispatches either a button click or a key press based on the
        result's ``dismiss_type``.

        Args:
            result: A detected popup result.

        Returns:
            The same result with ``dismissed`` set to ``True`` on success.
        """
        if not result.detected:
            return result

        self._dismiss_attempts += 1
        dismissed = False

        if result.dismiss_type == "key":
            dismissed = self._send_key(result.dismiss_action)
        else:
            dismissed = self._click_button(result.dismiss_action)

        if dismissed:
            logger.info(
                "PopupHandler: dismissed popup %r via %s %r",
                result.popup_type,
                result.dismiss_type,
                result.dismiss_action,
            )
            result.dismissed = True
            self._dismiss_attempts = 0
        else:
            logger.warning(
                "PopupHandler: failed to dismiss popup %r (attempt %d/%d)",
                result.popup_type,
                self._dismiss_attempts,
                self.MAX_DISMISS_ATTEMPTS,
            )

        return result

    # ------------------------------------------------------------------
    # Low-level dismiss helpers
    # ------------------------------------------------------------------

    def _send_key(self, key: str) -> bool:
        """Send a key press to dismiss a popup. Returns True on success."""
        key_lower = key.lower().strip()

        # Map common names to pyautogui key names
        key_map = {
            "escape": "escape",
            "esc": "escape",
            "enter": "enter",
            "return": "enter",
            "tab": "tab",
            "space": "space",
        }
        mapped = key_map.get(key_lower, key_lower)

        try:
            import pyautogui

            pyautogui.press(mapped)
            return True
        except Exception as exc:
            logger.debug("PopupHandler key press failed: %s", exc)
            return False

    def _click_button(self, button_text: str) -> bool:
        """Click a button by its text label. Returns True on success."""
        # Strategy 1: OCR find_text
        try:
            from core import ocr

            pos = ocr.find_text(button_text, fuzzy=True)
            if pos is not None:
                import pyautogui

                pyautogui.click(pos[0], pos[1])
                return True
        except Exception as exc:
            logger.debug("PopupHandler OCR click failed: %s", exc)

        # Strategy 2: UIAutomation click by name
        try:
            from core import ui_tree

            ui_pos = ui_tree.click_control(name=button_text)
            if ui_pos is not None:
                return True
        except Exception as exc:
            logger.debug("PopupHandler UIA click failed: %s", exc)

        # Strategy 3: Win32 FindWindowEx / EnumChildWindows button search
        if _IS_WINDOWS:
            try:
                import win32con  # type: ignore
                import win32gui  # type: ignore

                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    button_hwnd = self._find_button_hwnd(hwnd, button_text)
                    if button_hwnd:
                        win32gui.SendMessage(button_hwnd, win32con.BM_CLICK, 0, 0)
                        return True
            except Exception as exc:
                logger.debug("PopupHandler Win32 button click failed: %s", exc)

        return False

    def _find_button_hwnd(self, parent_hwnd: int, button_text: str) -> int | None:
        """Find a child button HWND by text (Windows-only)."""
        if not _IS_WINDOWS:
            return None

        found: list[int] = []
        target = button_text.lower()

        def _enum(hwnd: int, _lparam: int) -> None:
            """EnumWindows callback — collect buttons matching the target text."""
            try:
                import win32gui  # type: ignore

                text = win32gui.GetWindowText(hwnd).lower()
                class_name = win32gui.GetClassName(hwnd).lower()
                if target in text and "button" in class_name:
                    found.append(hwnd)
            except (ImportError, OSError, AttributeError):
                pass

        try:
            import win32gui  # type: ignore

            win32gui.EnumChildWindows(parent_hwnd, _enum, None)
        except (ImportError, OSError, AttributeError):
            pass

        return found[0] if found else None

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset cooldown and dismiss attempt state."""
        self._last_popup_type = ""
        self._last_detection_time = 0.0
        self._dismiss_attempts = 0
