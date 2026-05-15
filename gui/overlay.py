"""
Sentinel Desktop v2 — Action overlay.

Pops a transparent, click-through, always-on-top window for ~400ms at the
location of every state-changing action. Visible feedback during automation
makes it easy to follow what the agent is doing (and lets you scrub away
from the cursor before it acts).

Implementation notes:
* Pure Tk so we don't add another GUI dep.
* Click-through is set via Win32 ``WS_EX_TRANSPARENT`` on Windows; other OSes
  just get a regular topmost window (still functional, just not click-through).
* The overlay is *thread-safe to invoke*: ``show_action(...)`` schedules the
  draw on the main thread via ``root.after``.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import Any

logger = logging.getLogger(__name__)


_SHOW_MS = 420  # how long the indicator stays visible
_RING_RADIUS = 28


class ActionOverlay:
    """Owns a hidden Tk root and exposes ``show_action()`` for cross-thread use."""

    def __init__(self, master: Any) -> None:
        self.master = master
        self._lock = threading.Lock()
        self._current: _Indicator | None = None

    def show_action(self, action: dict[str, Any]) -> None:
        """Render a brief indicator for *action*. Safe from any thread."""
        coords = _coords_from_action(action)
        if coords is None:
            return
        label = _label_for_action(action)
        # Marshal to the Tk main thread.
        try:
            self.master.after(0, self._show_main, coords, label, action.get("action", ""))
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("overlay schedule failed: %s", exc)

    # ── main-thread implementation ─────────────────────────────────

    def _show_main(self, coords: tuple[int, int], label: str, action_name: str) -> None:
        x, y = coords
        try:
            with self._lock:
                if self._current is not None:
                    self._current.destroy()
                self._current = _Indicator(self.master, x=x, y=y, label=label, kind=action_name)
            # Auto-dismiss.
            self.master.after(_SHOW_MS, self._dismiss)
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("overlay draw failed: %s", exc)

    def _dismiss(self) -> None:
        with self._lock:
            if self._current is not None:
                try:
                    self._current.destroy()
                except (RuntimeError, tk.TclError) as exc:
                    logger.debug("Overlay destroy failed: %s", exc)
                self._current = None


class _Indicator:
    """A single overlay instance — created and destroyed in <1 second."""

    def __init__(self, master: Any, *, x: int, y: int, label: str, kind: str) -> None:
        import tkinter as tk

        self.tk = tk

        diameter = _RING_RADIUS * 2
        text_w = max(120, len(label) * 8)
        w = max(diameter, text_w) + 24
        h = diameter + 30

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.85)
            self.win.attributes("-transparentcolor", "#010203")
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("Overlay transparency attributes not supported: %s", exc)
        # Position centered on (x, y).
        gx = max(0, x - w // 2)
        gy = max(0, y - h // 2)
        self.win.geometry(f"{w}x{h}+{gx}+{gy}")

        self.canvas = tk.Canvas(
            self.win,
            width=w,
            height=h,
            highlightthickness=0,
            bg="#010203",  # the transparent color
        )
        self.canvas.pack(fill="both", expand=True)

        cx = w // 2
        cy = (h - 26) // 2  # room for label
        color = _color_for_kind(kind)

        # Ring
        self.canvas.create_oval(
            cx - _RING_RADIUS,
            cy - _RING_RADIUS,
            cx + _RING_RADIUS,
            cy + _RING_RADIUS,
            outline=color,
            width=4,
        )
        # Crosshair dot
        self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=color, outline=color)

        # Label background
        label = (label or "").strip()
        if label:
            text_y = h - 14
            self.canvas.create_rectangle(
                4,
                text_y - 11,
                w - 4,
                text_y + 10,
                fill="#0A0C10",
                outline=color,
                width=1,
            )
            self.canvas.create_text(
                cx,
                text_y,
                text=label,
                fill="#e2e2e8",
                font=("Segoe UI", 9, "bold"),
            )

        # Make the whole window click-through on Windows.
        _make_clickthrough(self.win)

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("Indicator destroy failed: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coords_from_action(action: dict[str, Any]) -> tuple[int, int] | None:
    """Pull (x, y) from an action dict if it has them."""
    if "x" in action and "y" in action:
        try:
            return int(action["x"]), int(action["y"])
        except (TypeError, ValueError):
            return None
    pos = action.get("position")
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        try:
            return int(pos[0]), int(pos[1])
        except (TypeError, ValueError):
            return None
    return None


def _label_for_action(action: dict[str, Any]) -> str:
    name = action.get("action", "")
    if name == "click":
        return f"click ({action.get('x', '?')}, {action.get('y', '?')})"
    if name == "click_text":
        return f"click text: {str(action.get('text', ''))[:40]}"
    if name == "click_control":
        return f"click control: {str(action.get('name', ''))[:40]}"
    if name == "type_text":
        return f"type: {str(action.get('text', ''))[:40]}"
    if name == "set_text":
        return f"set text: {str(action.get('name', ''))[:40]}"
    if name == "hotkey":
        keys = action.get("keys") or []
        return "hotkey: " + "+".join(map(str, keys))[:40]
    if name == "press_key":
        return f"press: {action.get('key', '')}"
    if name == "scroll":
        return f"scroll: {action.get('amount', '')}"
    return name or "action"


def _color_for_kind(kind: str) -> str:
    if kind in ("click_text", "click_control"):
        return "#95E400"  # lime green (Override success) — high-confidence
    if kind == "type_text" or kind == "set_text":
        return "#00F0FF"  # cyan (Override accent) — input
    if kind in ("hotkey", "press_key"):
        return "#FBBC00"  # amber (Override warning) — keys
    return "#e8793a"  # sentinel orange — default


def _make_clickthrough(window: Any) -> None:
    """Make a Tk window click-through on Windows.

    Adds the WS_EX_TRANSPARENT extended style so clicks pass to the window
    behind. No-ops on non-Windows.
    """
    try:
        import sys

        if sys.platform != "win32":
            return
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000

        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            return
        # GetWindowLongW for both 32- and 64-bit safety.
        user32 = ctypes.windll.user32
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.restype = ctypes.c_long

        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
    except Exception as exc:
        logger.debug("clickthrough setup failed: %s", exc)
