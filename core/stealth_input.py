"""
Sentinel Desktop v2 — Stealth input.

Backbone of the optional "stealth" mode that lets the agent click and type
WITHOUT hijacking the user's real mouse and keyboard.

Two transports:

1. **PostMessage to specific HWNDs**
   ``WindowFromPoint(x,y)`` finds the window under a target coordinate, then we
   ``PostMessage`` ``WM_LBUTTONDOWN``/``WM_LBUTTONUP`` (or ``WM_CHAR`` for typing)
   directly to it. The system cursor never moves, and the user can keep typing
   in another window concurrently.

2. **UIAutomation InvokePattern**
   For UIA targets the agent already located by name, calling
   ``element.GetInvokePattern().Invoke()`` triggers the control's action via
   the accessibility tree — also with no cursor movement.

Neither approach works against every app — Chromium-based apps in particular
ignore many synthesized window messages, and apps that bypass UIA won't see
Invoke. Callers should always be prepared to fall back to physical input
(``pyautogui``) when stealth fails.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import win32gui  # type: ignore
    import win32api  # type: ignore
    import win32con  # type: ignore
    _HAS_WIN32 = True
except Exception:
    _HAS_WIN32 = False


def is_available() -> bool:
    """True if the stealth transports can actually be used on this OS."""
    return _HAS_WIN32


# ---------------------------------------------------------------------------
# Mouse: PostMessage click
# ---------------------------------------------------------------------------

def post_click(x: int, y: int, button: str = "left",
               clicks: int = 1, delay: float = 0.02) -> bool:
    """Send a click to the window at screen coord (x, y) without moving the cursor.

    Returns True if at least one click message was posted successfully.
    """
    if not _HAS_WIN32:
        return False
    try:
        hwnd = win32gui.WindowFromPoint((int(x), int(y)))
        if not hwnd:
            return False
        # Translate screen → client coords for the actual target window.
        cx, cy = win32gui.ScreenToClient(hwnd, (int(x), int(y)))
        lparam = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
        if button == "right":
            down, up = win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP
            wparam = win32con.MK_RBUTTON
        elif button == "middle":
            down, up = win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP
            wparam = win32con.MK_MBUTTON
        else:
            down, up = win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP
            wparam = win32con.MK_LBUTTON
        for _ in range(max(1, clicks)):
            win32api.PostMessage(hwnd, down, wparam, lparam)
            time.sleep(delay)
            win32api.PostMessage(hwnd, up, 0, lparam)
            time.sleep(delay)
        return True
    except Exception as exc:
        logger.debug("post_click failed at (%s,%s): %s", x, y, exc)
        return False


# ---------------------------------------------------------------------------
# Keyboard: PostMessage WM_CHAR
# ---------------------------------------------------------------------------

def post_text(text: str, hwnd: Optional[int] = None, delay: float = 0.005) -> bool:
    """Send WM_CHAR per character to *hwnd* (or the foreground window if None).

    Returns True if all characters were posted.
    """
    if not _HAS_WIN32 or not text:
        return False
    try:
        if hwnd is None:
            hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        # Some apps prefer the focused control under the foreground window —
        # GetGUIThreadInfo gives that if available.
        focus_hwnd = _get_focus_hwnd(hwnd) or hwnd
        for ch in text:
            # WM_CHAR delivers a single character as if the user typed it.
            win32api.PostMessage(focus_hwnd, win32con.WM_CHAR, ord(ch), 0)
            if delay:
                time.sleep(delay)
        return True
    except Exception as exc:
        logger.debug("post_text failed: %s", exc)
        return False


def post_key(vk_code: int, hwnd: Optional[int] = None) -> bool:
    """Send a single virtual-key press (WM_KEYDOWN + WM_KEYUP) to *hwnd*."""
    if not _HAS_WIN32:
        return False
    try:
        if hwnd is None:
            hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0)
        time.sleep(0.01)
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0)
        return True
    except Exception as exc:
        logger.debug("post_key failed: %s", exc)
        return False


# Map of common key names → virtual key codes for post_key.
VK_NAMES = {
    "enter": 0x0D, "return": 0x0D,
    "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def post_named_key(name: str, hwnd: Optional[int] = None) -> bool:
    vk = VK_NAMES.get((name or "").lower())
    if vk is None:
        # Single-character fallback.
        if name and len(name) == 1:
            return post_text(name, hwnd=hwnd)
        return False
    return post_key(vk, hwnd=hwnd)


# Modifier key codes for chorded hotkeys.
_MOD_VK = {
    "ctrl": 0x11, "control": 0x11,
    "shift": 0x10,
    "alt": 0x12, "menu": 0x12,
    "win": 0x5B, "windows": 0x5B, "meta": 0x5B,
}


def post_hotkey(keys, hwnd: Optional[int] = None) -> bool:
    """Send a chorded hotkey (e.g. Ctrl+C) via WM_KEYDOWN/UP messages.

    Note: many apps require *real* input state for modifier handling — e.g.
    Chromium-based apps watch the real keyboard's modifier flags rather than
    just receiving the messages. When this returns False the caller should
    fall back to physical hotkey.
    """
    if not _HAS_WIN32 or not keys:
        return False
    try:
        if hwnd is None:
            hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        target = _get_focus_hwnd(hwnd) or hwnd

        mod_codes = []
        main_codes = []
        for k in keys:
            k = str(k).lower()
            if k in _MOD_VK:
                mod_codes.append(_MOD_VK[k])
            else:
                vk = VK_NAMES.get(k)
                if vk is None:
                    if len(k) == 1:
                        vk = ord(k.upper())
                    else:
                        return False
                main_codes.append(vk)
        if not main_codes:
            return False

        for vk in mod_codes:
            win32api.PostMessage(target, win32con.WM_KEYDOWN, vk, 0)
        for vk in main_codes:
            win32api.PostMessage(target, win32con.WM_KEYDOWN, vk, 0)
            time.sleep(0.005)
            win32api.PostMessage(target, win32con.WM_KEYUP, vk, 0)
        for vk in reversed(mod_codes):
            win32api.PostMessage(target, win32con.WM_KEYUP, vk, 0)
        return True
    except Exception as exc:
        logger.debug("post_hotkey failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _get_focus_hwnd(parent: int) -> Optional[int]:
    """Return the focused-control HWND inside *parent*'s thread, if any."""
    try:
        import ctypes
        thread_id = win32api.GetWindowThreadProcessId(parent)[0]
        info = _GUI_THREAD_INFO()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            return int(info.hwndFocus) or None
    except Exception:
        return None
    return None


# ctypes Struct for GetGUIThreadInfo — declared lazily so imports stay cheap
# on non-Windows.
if _HAS_WIN32:
    import ctypes
    from ctypes import wintypes

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class _GUI_THREAD_INFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hwndActive", wintypes.HWND),
            ("hwndFocus", wintypes.HWND),
            ("hwndCapture", wintypes.HWND),
            ("hwndMenuOwner", wintypes.HWND),
            ("hwndMoveSize", wintypes.HWND),
            ("hwndCaret", wintypes.HWND),
            ("rcCaret", _RECT),
        ]
else:
    class _GUI_THREAD_INFO:  # type: ignore[no-redef]
        pass
