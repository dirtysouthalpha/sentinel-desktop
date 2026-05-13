"""Window management: list, find, focus, resize, close windows."""

import logging
import platform

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
else:
    HAS_WIN32 = False
    HAS_PGW = False


def list_windows() -> list:
    """List all visible windows with title, position, size, focused state."""
    windows = []
    if HAS_WIN32:

        def _enum(hwnd, _):
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
                        }
                    )

        win32gui.EnumWindows(_enum, None)
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
                        }
                    )
        except Exception as e:
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
        needle = title.lower()
        target = None
        for w in list_windows():
            if needle in (w.get("title") or "").lower():
                target = w
                break
        if target is None:
            return False
        hwnd = target.get("hwnd")
        if not hwnd:
            return False
        try:
            # Restore if minimized.
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            # The Alt-tap trick: some Windows versions block SetForegroundWindow
            # unless the calling thread has recent input. Sending a key press
            # primes the input state.
            try:
                import ctypes

                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # Alt down
                ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)  # Alt up
            except Exception:
                pass
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as exc:
            logger.debug("focus_window(%s) failed: %s", title, exc)
            return False
    elif HAS_PGW:
        try:
            wins = pgw.getWindowsWithTitle(title)
            if wins:
                wins[0].activate()
                return True
        except Exception:
            pass
    return False


# Window-title substrings of the Sentinel Desktop GUI itself. ``read_text``
# uses this to avoid OCR'ing our own chat window when focus snaps back to us
# between agent steps.
SELF_WINDOW_HINTS = ("sentinel desktop",)


def _is_self_window(title: str) -> bool:
    if not title:
        return False
    low = title.lower()
    return any(h in low for h in SELF_WINDOW_HINTS)


def get_focused_window_rect():
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
        except Exception as exc:
            logger.debug("get_focused_window_rect failed: %s", exc)
            return None
    if HAS_PGW:
        try:
            w = pgw.getActiveWindow()
            if w and w.width > 0 and w.height > 0:
                return (w.left, w.top, w.width, w.height)
        except Exception:
            pass
    return None


def get_target_window_rect():
    """Return (x, y, w, h, title) for the window the agent likely wants to
    inspect — the foreground window, unless that's Sentinel Desktop itself
    (which often happens between actions when focus snaps back to the GUI).

    In that case we fall back to the most recent *other* visible window.
    Returns None if no suitable window exists.
    """
    focused_title = ""
    focused_rect = None
    if HAS_WIN32:
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                focused_title = win32gui.GetWindowText(hwnd) or ""
                r = win32gui.GetWindowRect(hwnd)
                focused_rect = (r[0], r[1], r[2] - r[0], r[3] - r[1])
        except Exception:
            pass
    # If the foreground IS another app, use it.
    if focused_rect and not _is_self_window(focused_title):
        if focused_rect[2] > 0 and focused_rect[3] > 0:
            return (*focused_rect, focused_title)

    # Otherwise scan visible windows for the next-best candidate.
    candidates = []
    try:
        for w in list_windows():
            title = w.get("title") or ""
            if not title or _is_self_window(title):
                continue
            if w.get("width", 0) <= 200 or w.get("height", 0) <= 200:
                # Skip tiny utility windows (tray notifications etc.).
                continue
            candidates.append(w)
    except Exception:
        pass

    # Prefer a candidate that was focused; failing that, the first.
    candidates.sort(key=lambda w: (0 if w.get("is_focused") else 1, -w.get("width", 0)))
    if candidates:
        c = candidates[0]
        return (c["x"], c["y"], c["width"], c["height"], c["title"])
    return None


def get_window_rect(title: str):
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
                if _looks_minimized(rect):
                    # Try to restore so capture_region gets real pixels.
                    if "hwnd" in w:
                        restore_window_hwnd(w["hwnd"])
                        # Re-fetch the post-restore rect.
                        for w2 in list_windows():
                            if (w2.get("title") or "").lower() == (w.get("title") or "").lower():
                                rect = (w2["x"], w2["y"], w2["width"], w2["height"])
                                break
                return rect
    except Exception as exc:
        logger.debug("get_window_rect via list_windows failed: %s", exc)
    return None


def _looks_minimized(rect) -> bool:
    """Windows parks minimized windows at (-32000, -32000) — detect that.

    Also catches degenerate / zero-sized rectangles.
    """
    if not rect or len(rect) < 4:
        return True
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return True
    if x <= -32000 or y <= -32000:
        return True
    return False


def restore_window_hwnd(hwnd) -> bool:
    """Restore a window by hwnd if it's minimized. Best-effort, never raises."""
    if not HAS_WIN32 or not hwnd:
        return False
    try:
        # SW_RESTORE = 9; activates and restores from minimized/maximized.
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        return True
    except Exception as exc:
        logger.debug("restore_window_hwnd(%s) failed: %s", hwnd, exc)
        return False


def restore_window(title: str) -> bool:
    """Restore a window by partial title match. Returns True if a match was
    found and the restore call was issued."""
    if not title:
        return False
    needle = title.lower()
    for w in list_windows():
        if needle in (w.get("title") or "").lower():
            return restore_window_hwnd(w.get("hwnd"))
    return False


def close_window(title: str) -> bool:
    """Close a window by partial title match."""
    if HAS_WIN32:

        def _find(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                if title.lower() in win32gui.GetWindowText(hwnd).lower():
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    return True
            return False

        try:
            win32gui.EnumWindows(_find, None)
            return True
        except Exception:
            return False
    elif HAS_PGW:
        try:
            wins = pgw.getWindowsWithTitle(title)
            if wins:
                wins[0].close()
                return True
        except Exception:
            pass
    return False
