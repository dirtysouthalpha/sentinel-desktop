"""Sentinel Desktop v3.0 — Window management utilities.

Provides functions to list, find, focus, resize, and close windows.
Cross-platform support with Windows-specific enhancements via win32gui.
"""

import logging
import platform
from typing import Any

logger = logging.getLogger(__name__)

if platform.system() == "Windows":
    try:
        import win32con
        import win32gui

        HAS_WIN32 = True
    except ImportError:
        HAS_WIN32 = False
    try:
        import pygetwindow as pgw

        HAS_PGW = True
    except ImportError:
        HAS_PGW = False
    try:
        import pywintypes

        _Win32Error = pywintypes.error  # type: ignore[attr-defined]
    except ImportError:
        _Win32Error = OSError  # type: ignore[misc,assignment]
else:
    HAS_WIN32 = False
    HAS_PGW = False
    _Win32Error = OSError  # type: ignore[misc,assignment]


# Constants for window validation
_MIN_WINDOW_SIZE = 200  # Minimum width/height for valid windows
_MIN_COORDINATE = -32000  # Windows uses this for minimized/hidden windows
_MIN_RECT_COMPONENTS = 4  # Expected number of components in a rectangle (x, y, w, h)


def list_windows() -> list[dict[str, Any]]:
    """List all visible windows with title, position, size, focused state."""
    windows = []
    if HAS_WIN32:

        def _enum(hwnd: int, _: Any) -> None:
            """EnumWindows callback — collect visible windows with titles."""
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    rect = win32gui.GetWindowRect(hwnd)
                    windows.append(
                        {
                            "title": title,
                            "x": rect[0],
                            "y": rect[1],
                            "width": rect[2] - rect[0],
                            "height": rect[3] - rect[1],
                            "is_focused": hwnd == win32gui.GetForegroundWindow(),
                            "hwnd": hwnd,
                        },
                    )

        try:
            win32gui.EnumWindows(_enum, None)
        except _Win32Error as exc:
            logger.error("list_windows EnumWindows failed: %s", exc)
    elif HAS_PGW:
        try:
            for w in pgw.getAllWindows():
                if w.title:
                    windows.append(
                        {
                            "title": w.title,
                            "x": w.left,
                            "y": w.top,
                            "width": w.width,
                            "height": w.height,
                            "is_focused": w.isActive,
                        },
                    )
        except (OSError, RuntimeError) as e:
            logger.error("list_windows via pygetwindow failed: %s", e)
    else:
        logger.warning("No window management library available")
    return windows


def focus_window(title: str) -> bool:
    """Bring a window to the foreground by partial title match.

    Aggressively restores minimized windows AND attempts to bypass Windows'
    SetForegroundWindow restriction with a brief Alt key tap (a long-standing
    workaround that lets a non-foreground process raise another window).
    """
    if HAS_WIN32:
        return _focus_window_win32(title)
    elif HAS_PGW:
        return _focus_window_pgw(title)
    return False


def _focus_window_win32(title: str) -> bool:
    """Focus a window using Win32 API."""
    target = _find_window_by_title(title)
    if target is None:
        return False
    hwnd = target.get("hwnd")
    if not hwnd:
        return False
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        _alt_tap_trick()
        win32gui.SetForegroundWindow(hwnd)
        return True
    except _Win32Error as exc:
        logger.warning("focus_window(%s) failed: %s", title, exc)
        return False


def _find_window_by_title(title: str) -> dict[str, Any] | None:
    """Find a window by partial title match."""
    needle = title.lower()
    for w in list_windows():
        if needle in (w.get("title") or "").lower():
            return w
    return None


def _alt_tap_trick() -> None:
    """Perform Alt-tap trick to bypass SetForegroundWindow restrictions."""
    try:
        import ctypes

        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # Alt down
        ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)  # Alt up
    except OSError as exc:
        logger.debug("Alt-tap trick failed: %s", exc)


def _focus_window_pgw(title: str) -> bool:
    """Focus a window using PyGetWindow."""
    try:
        wins = pgw.getWindowsWithTitle(title)
        if wins:
            wins[0].activate()
            return True
    except (OSError, RuntimeError) as exc:
        logger.debug("pgw focus_window(%s) failed: %s", title, exc)
    return False


# Window-title substrings of the Sentinel Desktop GUI itself. ``read_text``
# uses this to avoid OCR'ing our own chat window when focus snaps back to us
# between agent steps.
SELF_WINDOW_HINTS = ("sentinel desktop",)


def _is_self_window(title: str) -> bool:
    """Return ``True`` if *title* matches a known Sentinel Desktop window hint."""
    if not title:
        return False
    low = title.lower()
    return any(h in low for h in SELF_WINDOW_HINTS)


def get_focused_window_rect() -> tuple[int, int, int, int] | None:
    """Return (x, y, width, height) of the foreground window, or None."""
    if HAS_WIN32:
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            rect = win32gui.GetWindowRect(hwnd)
            x, y = rect[0], rect[1]
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w <= 0 or h <= 0:
                return None
            return (x, y, w, h)
        except _Win32Error as exc:
            logger.debug("get_focused_window_rect failed: %s", exc)
            return None
    if HAS_PGW:
        try:
            w = pgw.getActiveWindow()
            if w and w.width > 0 and w.height > 0:
                return (w.left, w.top, w.width, w.height)
        except (OSError, RuntimeError) as exc:
            logger.debug("pgw get_focused_window_rect failed: %s", exc)
    return None


def get_target_window_rect() -> tuple[int, int, int, int, str] | None:
    """Return geometry for the target window, avoiding Sentinel Desktop itself.

    In that case we fall back to the most recent *other* visible window.
    Returns None if no suitable window exists.
    """
    focused_title, focused_rect = _get_foreground_window_info()
    if (
        focused_rect
        and not _is_self_window(focused_title)
        and focused_rect[2] > 0
        and focused_rect[3] > 0
    ):
        return (*focused_rect, focused_title)
    return _find_best_candidate_window()


def _get_foreground_window_info() -> tuple[str, tuple[int, int, int, int] | None]:
    """Get the foreground window title and rect."""
    focused_title = ""
    focused_rect = None
    if HAS_WIN32:
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                focused_title = win32gui.GetWindowText(hwnd) or ""
                r = win32gui.GetWindowRect(hwnd)
                focused_rect = (r[0], r[1], r[2] - r[0], r[3] - r[1])
        except _Win32Error as exc:
            logger.debug("get_target_window_rect foreground lookup failed: %s", exc)
    return focused_title, focused_rect


def _find_best_candidate_window() -> tuple[int, int, int, int, str] | None:
    """Find the best candidate window from visible windows."""
    candidates = _collect_candidate_windows()
    candidates.sort(key=lambda w: (0 if w.get("is_focused") else 1, -w.get("width", 0)))
    if candidates:
        c = candidates[0]
        return (c["x"], c["y"], c["width"], c["height"], c["title"])
    return None


def _collect_candidate_windows() -> list[dict[str, Any]]:
    """Collect visible windows that are valid candidates."""
    candidates = []
    try:
        for w in list_windows():
            title = w.get("title") or ""
            if not title or _is_self_window(title):
                continue
            if w.get("width", 0) <= _MIN_WINDOW_SIZE or w.get("height", 0) <= _MIN_WINDOW_SIZE:
                continue
            candidates.append(w)
    except (OSError, RuntimeError) as exc:
        logger.debug("get_target_window_rect candidate scan failed: %s", exc)
    return candidates


def get_window_rect(title: str) -> tuple[int, int, int, int] | None:
    """Return (x, y, w, h) for a window whose title contains *title*, or None.

    Reuses ``list_windows`` so we use the same enumeration path as everything
    else — and we get the auto-restore side effect of attempting to surface
    minimized windows before reporting their rects.
    """
    if not title:
        return None
    needle = title.lower()
    # Try the high-level path first — it's the same one ``list_windows`` uses,
    # so anything visible to the agent is visible here too.
    try:
        for w in list_windows():
            t = (w.get("title") or "").lower()
            if needle in t:
                rect = (w["x"], w["y"], w["width"], w["height"])
                if _looks_minimized(rect) and "hwnd" in w:
                    # Try to restore so capture_region gets real pixels.
                    restore_window_hwnd(w["hwnd"])
                    # Re-fetch the post-restore rect.
                    for w2 in list_windows():
                        if (w2.get("title") or "").lower() == (w.get("title") or "").lower():
                            rect = (w2["x"], w2["y"], w2["width"], w2["height"])
                            break
                return rect
    except (_Win32Error, OSError) as exc:
        logger.debug("get_window_rect via list_windows failed: %s", exc)
    return None


def _looks_minimized(rect: tuple[int, int, int, int] | None) -> bool:
    """Windows parks minimized windows at (-32000, -32000) — detect that.

    Also catches degenerate / zero-sized rectangles.
    """
    if not rect or len(rect) < _MIN_RECT_COMPONENTS:
        return True
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return True
    return bool(x <= _MIN_COORDINATE or y <= _MIN_COORDINATE)


def restore_window_hwnd(hwnd: int) -> bool:
    """Restore a window by hwnd if it's minimized. Best-effort, never raises."""
    if not HAS_WIN32 or not hwnd:
        return False
    try:
        # SW_RESTORE = 9; activates and restores from minimized/maximized.
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        return True
    except _Win32Error as exc:
        logger.debug("restore_window_hwnd(%s) failed: %s", hwnd, exc)
        return False


def restore_window(title: str) -> bool:
    """Restore a window by partial title match.

    Returns True if a match was found and the restore call was issued.
    """
    if not title:
        return False
    needle = title.lower()
    try:
        for w in list_windows():
            if needle in (w.get("title") or "").lower():
                hwnd = w.get("hwnd")
                if hwnd is not None:
                    return restore_window_hwnd(hwnd)
    except (OSError, _Win32Error) as exc:
        logger.warning("restore_window(%s) enumeration failed: %s", title, exc)
    return False


def close_window(title: str) -> bool:
    """Close the first window matching *title* (partial, case-insensitive).

    Returns ``True`` only if a matching window was found and WM_CLOSE was
    posted.  Subsequent matching windows are left alone — call again to
    close the next one.
    """
    if HAS_WIN32:
        found = False

        def _find(hwnd: int, _: Any) -> None:
            """EnumWindows callback — post WM_CLOSE to the first matching window."""
            nonlocal found
            if found:
                return  # Already closed one; stop iterating.
            if (
                win32gui.IsWindowVisible(hwnd)
                and title.lower() in win32gui.GetWindowText(hwnd).lower()
            ):
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                found = True

        try:
            win32gui.EnumWindows(_find, None)
            return found
        except _Win32Error as exc:
            logger.warning("close_window(%s) enum failed: %s", title, exc)
            return False
    elif HAS_PGW:
        try:
            wins = pgw.getWindowsWithTitle(title)
            if wins:
                wins[0].close()
                return True
        except (OSError, RuntimeError) as exc:
            logger.debug("pgw close_window(%s) failed: %s", title, exc)
    return False
