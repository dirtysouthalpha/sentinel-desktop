"""Window management: list, find, focus, resize, close windows."""
import logging
import platform

logger = logging.getLogger(__name__)

if platform.system() == "Windows":
    try:
        import win32gui
        import win32con
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
                    windows.append({
                        "title": title,
                        "x": rect[0], "y": rect[1],
                        "width": rect[2] - rect[0],
                        "height": rect[3] - rect[1],
                        "is_focused": hwnd == win32gui.GetForegroundWindow(),
                        "hwnd": hwnd,
                    })
        win32gui.EnumWindows(_enum, None)
    elif HAS_PGW:
        try:
            for w in pgw.getAllWindows():
                if w.title:
                    windows.append({
                        "title": w.title,
                        "x": w.left, "y": w.top,
                        "width": w.width, "height": w.height,
                        "is_focused": w.isActive,
                    })
        except Exception as e:
            logger.error("list_windows via pygetwindow failed: %s", e)
    else:
        logger.warning("No window management library available")
    return windows


def focus_window(title: str) -> bool:
    """Bring a window to the foreground by partial title match."""
    if HAS_WIN32:
        def _find(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                if title.lower() in win32gui.GetWindowText(hwnd).lower():
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
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
                wins[0].activate()
                return True
        except Exception:
            pass
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
