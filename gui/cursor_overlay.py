"""Sentinel Desktop v3 — Animated cursor overlay.

Renders a transparent, click-through, always-on-top ring that glides to
the location of every agent action. This is the desktop equivalent of
Sentinel Override's orange operator cursor — visible feedback so the user
can see exactly what the agent is doing without the real mouse moving.

Uses a Tk root on a background thread. Win32 WS_EX_TRANSPARENT makes it
click-through so it never blocks interaction.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import tkinter as tk
from typing import Any

logger = logging.getLogger(__name__)

# Animation defaults
_GLIDE_DURATION = 0.35  # seconds for cursor to glide to target
_RING_RADIUS = 18  # pixels
_PULSE_DURATION = 0.5  # seconds for post-action pulse
_FADE_DURATION = 0.3  # seconds to fade out after pulse
_STEPS_PER_SECOND = 60  # animation smoothness


# Easing function: ease-out cubic
def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


class CursorOverlay:
    """Render an animated cursor overlay on a hidden Tk root.

    Thread-safe — call show_action() from any thread.
    """

    def __init__(self, accent_color: str = "#00F0FF") -> None:
        """Initialize the overlay renderer (does not start the background thread).

        Args:
            accent_color: Hex color string for the cursor ring and label.

        """
        self._accent = accent_color
        self._thread: threading.Thread | None = None
        self._running: bool = False
        self._queue: list[dict[str, Any]] = []
        self._queue_lock = threading.Lock()
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._ring_id: int | None = None
        self._inner_id: int | None = None
        self._label_id: int | None = None
        self._current_x = -100
        self._current_y = -100

    def start(self) -> bool:
        """Start the overlay thread. Returns True if successful."""
        if self._running:
            return True
        try:
            import tkinter as tk  # noqa: F401 – imported to verify availability
        except ImportError:
            logger.warning("tkinter not available — cursor overlay disabled")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop the overlay thread."""
        self._running = False
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except (RuntimeError, tk.TclError) as exc:
                logger.debug("Cursor overlay destroy failed: %s", exc)

    def show_action(self, action: dict[str, Any]) -> None:
        """Queue an action for visual display. Thread-safe."""
        with self._queue_lock:
            self._queue.append(action)

    def set_accent(self, color: str) -> None:
        """Update the accent color."""
        self._accent = color

    # ── Internal ────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Background Tk mainloop."""
        import tkinter as tk

        screen_w, screen_h = self._setup_tk_window(tk)
        self._create_canvas_and_rings(tk, screen_w, screen_h)
        self._make_click_through()
        self._root.after(50, self._process_queue)

        try:
            self._root.mainloop()
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("Cursor overlay mainloop exited: %s", exc)
        finally:
            self._running = False

    def _setup_tk_window(self, tk: Any) -> tuple[int, int]:
        """Create the Tk root as a transparent full-screen overlay.

        Returns:
            (screen_width, screen_height) in pixels.

        """
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.0)
        try:
            self._root.wm_attributes("-transparentcolor", "white")
        except (RuntimeError, tk.TclError) as exc:
            logger.debug("Transparent color attribute not supported: %s", exc)
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        self._root.geometry(f"{screen_w}x{screen_h}+0+0")
        return screen_w, screen_h

    def _create_canvas_and_rings(self, tk: Any, screen_w: int, screen_h: int) -> None:
        """Create the full-screen canvas and the three ring canvas items."""
        self._canvas = tk.Canvas(
            self._root,
            width=screen_w,
            height=screen_h,
            bg="white",
            highlightthickness=0,
        )
        self._canvas.pack()
        self._ring_id = self._canvas.create_oval(
            -100,
            -100,
            -100,
            -100,
            outline=self._accent,
            width=3,
        )
        self._inner_id = self._canvas.create_oval(
            -100,
            -100,
            -100,
            -100,
            fill=self._accent,
            outline="",
        )
        self._label_id = self._canvas.create_text(
            -100,
            -100,
            text="",
            fill="white",
            font=("Segoe UI", 9, "bold"),
            anchor="s",
        )

    def _make_click_through(self) -> None:
        """Set WS_EX_TRANSPARENT | WS_EX_LAYERED on Windows for click-through."""
        try:
            import ctypes

            hwnd = int(self._root.winfo_id())
            GWL_EXSTYLE = -20  # noqa: N806
            WS_EX_TRANSPARENT = 0x20  # noqa: N806
            WS_EX_LAYERED = 0x80000  # noqa: N806
            ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                ex | WS_EX_TRANSPARENT | WS_EX_LAYERED,
            )
        except (OSError, AttributeError) as exc:
            logger.warning("Click-through setup failed (non-Windows?): %s", exc)

    def _process_queue(self) -> None:
        """Process queued actions, animating each one."""
        if not self._running:
            return

        action = None
        with self._queue_lock:
            if self._queue:
                action = self._queue.pop(0)

        if action:
            self._animate_action(action)

        self._root.after(16, self._process_queue)  # ~60fps check

    def _resolve_ring_color(self, action_type: str) -> str:
        """Map action type to ring color."""
        if action_type in ("click", "click_element", "click_image"):
            return self._accent
        if action_type in ("type_text", "type_into_field"):
            return "#95E400"  # lime
        if action_type in ("press_key", "hotkey"):
            return "#FBBC00"  # amber
        if action_type == "scroll":
            return "#8a5cff"  # phantom purple
        return self._accent

    def _glide_to(self, target_x: float, target_y: float, ring_color: str) -> bool:
        """Glide ring from current position to target. Returns False if stopped."""
        start_x, start_y = self._current_x, self._current_y
        glide_steps = int(_GLIDE_DURATION * _STEPS_PER_SECOND)
        for i in range(glide_steps):
            if not self._running:
                return False
            t = _ease_out(i / max(glide_steps, 1))
            cx = start_x + (target_x - start_x) * t
            cy = start_y + (target_y - start_y) * t
            r = _RING_RADIUS
            self._canvas.coords(self._ring_id, cx - r, cy - r, cx + r, cy + r)
            inner_r = r * 0.3
            self._canvas.coords(
                self._inner_id,
                cx - inner_r,
                cy - inner_r,
                cx + inner_r,
                cy + inner_r,
            )
            self._canvas.itemconfig(self._inner_id, fill=ring_color, stipple="gray50")
            self._canvas.itemconfig(self._ring_id, outline=ring_color)
            self._root.attributes("-alpha", 0.85)
            self._root.update_idletasks()
            time.sleep(1.0 / _STEPS_PER_SECOND)
        self._current_x, self._current_y = target_x, target_y
        return True

    def _pulse_at(self, target_x: float, target_y: float) -> bool:
        """Pulse ring at target position. Returns False if stopped."""
        pulse_steps = int(_PULSE_DURATION * _STEPS_PER_SECOND)
        for i in range(pulse_steps):
            if not self._running:
                return False
            t = i / max(pulse_steps, 1)
            scale = 1.0 + 0.5 * math.sin(t * math.pi)
            r = _RING_RADIUS * scale
            self._canvas.coords(
                self._ring_id,
                target_x - r,
                target_y - r,
                target_x + r,
                target_y + r,
            )
            self._root.update_idletasks()
            time.sleep(1.0 / _STEPS_PER_SECOND)
        return True

    def _fade_out(self) -> None:
        """Fade ring to transparent and hide all canvas items."""
        fade_steps = int(_FADE_DURATION * _STEPS_PER_SECOND)
        for i in range(fade_steps):
            if not self._running:
                break
            alpha = 0.85 * (1.0 - i / max(fade_steps, 1))
            self._root.attributes("-alpha", alpha)
            self._root.update_idletasks()
            time.sleep(1.0 / _STEPS_PER_SECOND)
        self._root.attributes("-alpha", 0.0)
        self._canvas.coords(self._ring_id, -100, -100, -100, -100)
        self._canvas.coords(self._inner_id, -100, -100, -100, -100)
        self._canvas.coords(self._label_id, -100, -100)

    def _animate_action(self, action: dict[str, Any]) -> None:
        """Animate a single action: glide → pulse → fade."""
        target_x = action.get("x", 0)
        target_y = action.get("y", 0)
        label = action.get("label", action.get("type", ""))
        ring_color = self._resolve_ring_color(action.get("type", ""))

        if not self._glide_to(target_x, target_y, ring_color):
            return

        if label:
            self._canvas.coords(self._label_id, target_x, target_y - _RING_RADIUS - 6)
            self._canvas.itemconfig(self._label_id, text=label, fill=ring_color)

        if not self._pulse_at(target_x, target_y):
            return

        self._fade_out()


# ── Singleton ───────────────────────────────────────────────────────

_overlay: CursorOverlay | None = None


def get_overlay() -> CursorOverlay:
    """Get or create the singleton overlay."""
    global _overlay
    if _overlay is None:
        _overlay = CursorOverlay()
    return _overlay


def start_overlay(accent_color: str = "#00F0FF") -> bool:
    """Start the cursor overlay. Returns True if successful."""
    o = get_overlay()
    o.set_accent(accent_color)
    return o.start()


def show_action(action: dict[str, Any]) -> None:
    """Show an action on the overlay. Thread-safe."""
    get_overlay().show_action(action)


def stop_overlay() -> None:
    """Stop the cursor overlay."""
    global _overlay
    if _overlay:
        _overlay.stop()
        _overlay = None
