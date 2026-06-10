"""Sentinel Desktop v16.0 — Advanced window management.

Provides resize, move, minimize, maximize, restore, get_monitors.
Uses pygetwindow + win32gui on Windows, wmctrl/wnck on Linux.

Usage::

    from core.window_control import (
        resize_window, move_window, minimize_window,
        maximize_window, restore_window, get_monitors,
    )
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"


# ── Monitor info ─────────────────────────────────────────────────────────────

def get_monitors() -> list[dict[str, Any]]:
    """Return info about all connected monitors.

    Returns:
        List of dicts with ``index``, ``x``, ``y``, ``width``, ``height``,
        ``is_primary``.
    """
    if _IS_WINDOWS:
        return _get_monitors_win32()
    return _get_monitors_screeninfo()


def _get_monitors_win32() -> list[dict[str, Any]]:
    """Enumerate monitors via win32api.EnumDisplayMonitors."""
    monitors = []
    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32
        rects: list[tuple[int, int, int, int]] = []

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(RECT), ctypes.c_double,
        )

        def _callback(hMonitor, hdcMonitor, lprcMonitor, dwData):  # noqa: N802
            r = lprcMonitor.contents
            rects.append((r.left, r.top, r.right, r.bottom))
            return True

        proc = MONITORENUMPROC(_callback)
        user32.EnumDisplayMonitors(None, None, proc, 0)

        for i, (x, y, x2, y2) in enumerate(rects):
            monitors.append({
                "index": i,
                "x": x, "y": y,
                "width": x2 - x,
                "height": y2 - y,
                "is_primary": (x == 0 and y == 0),
            })
    except Exception:
        # Fallback: use mss
        try:
            import mss  # type: ignore

            with mss.mss() as sct:
                for i, mon in enumerate(sct.monitors[1:], 0):  # [0] is virtual
                    monitors.append({
                        "index": i,
                        "x": mon["left"], "y": mon["top"],
                        "width": mon["width"], "height": mon["height"],
                        "is_primary": (mon["left"] == 0 and mon["top"] == 0),
                    })
        except Exception as exc:
            logger.warning("get_monitors failed: %s", exc)
    return monitors


def _get_monitors_screeninfo() -> list[dict[str, Any]]:
    """Enumerate monitors via screeninfo (cross-platform)."""
    try:
        from screeninfo import get_monitors as _gm  # type: ignore

        return [
            {
                "index": i,
                "x": m.x, "y": m.y,
                "width": m.width, "height": m.height,
                "is_primary": getattr(m, "is_primary", i == 0),
            }
            for i, m in enumerate(_gm())
        ]
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("screeninfo get_monitors failed: %s", exc)
    return [{"index": 0, "x": 0, "y": 0, "width": 1920, "height": 1080, "is_primary": True}]


# ── Window operations ────────────────────────────────────────────────────────

def _find_window(title: str) -> Any | None:
    """Find a window by title substring. Returns pygetwindow Window or None."""
    try:
        import pygetwindow as gw  # type: ignore

        wins = gw.getWindowsWithTitle(title)
        return wins[0] if wins else None
    except ImportError:
        logger.debug("pygetwindow not available")
        return None
    except Exception as exc:
        logger.debug("find_window(%r) failed: %s", title, exc)
        return None


def resize_window(title: str, width: int, height: int) -> dict[str, Any]:
    """Resize a window to *width* x *height* pixels.

    Args:
        title:  Window title (partial match).
        width:  Target width in pixels.
        height: Target height in pixels.

    Returns:
        Result dict with ``success`` and ``output``.
    """
    win = _find_window(title)
    if win is None:
        return {"success": False, "output": f"Window not found: {title!r}"}
    try:
        win.resizeTo(width, height)
        return {"success": True, "output": f"Resized '{title}' to {width}x{height}"}
    except Exception as exc:
        return {"success": False, "output": f"resize failed: {exc}"}


def move_window(title: str, x: int, y: int) -> dict[str, Any]:
    """Move a window's top-left corner to (*x*, *y*).

    Args:
        title: Window title (partial match).
        x:     Target X position.
        y:     Target Y position.
    """
    win = _find_window(title)
    if win is None:
        return {"success": False, "output": f"Window not found: {title!r}"}
    try:
        win.moveTo(x, y)
        return {"success": True, "output": f"Moved '{title}' to ({x}, {y})"}
    except Exception as exc:
        return {"success": False, "output": f"move failed: {exc}"}


def minimize_window(title: str) -> dict[str, Any]:
    """Minimize (iconify) a window by title."""
    win = _find_window(title)
    if win is None:
        return {"success": False, "output": f"Window not found: {title!r}"}
    try:
        win.minimize()
        return {"success": True, "output": f"Minimized '{title}'"}
    except Exception as exc:
        return {"success": False, "output": f"minimize failed: {exc}"}


def maximize_window(title: str) -> dict[str, Any]:
    """Maximize a window by title."""
    win = _find_window(title)
    if win is None:
        return {"success": False, "output": f"Window not found: {title!r}"}
    try:
        win.maximize()
        return {"success": True, "output": f"Maximized '{title}'"}
    except Exception as exc:
        return {"success": False, "output": f"maximize failed: {exc}"}


def restore_window(title: str) -> dict[str, Any]:
    """Restore a minimized or maximized window to normal state."""
    win = _find_window(title)
    if win is None:
        return {"success": False, "output": f"Window not found: {title!r}"}
    try:
        win.restore()
        return {"success": True, "output": f"Restored '{title}'"}
    except Exception as exc:
        return {"success": False, "output": f"restore failed: {exc}"}


def get_window_state(title: str) -> dict[str, Any]:
    """Return the current state and geometry of a window.

    Returns dict with ``title``, ``x``, ``y``, ``width``, ``height``,
    ``is_minimized``, ``is_maximized``, ``is_active``.
    """
    win = _find_window(title)
    if win is None:
        return {"success": False, "output": f"Window not found: {title!r}"}
    try:
        return {
            "success": True,
            "title": win.title,
            "x": win.left,
            "y": win.top,
            "width": win.width,
            "height": win.height,
            "is_minimized": win.isMinimized,
            "is_maximized": win.isMaximized,
            "is_active": win.isActive,
        }
    except Exception as exc:
        return {"success": False, "output": f"get_window_state failed: {exc}"}
