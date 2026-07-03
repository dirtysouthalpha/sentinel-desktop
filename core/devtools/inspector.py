"""Live desktop inspector — hover over elements to identify them.

Provides a real-time overlay that shows element properties as you move
the mouse. Useful for building automations without guesswork.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from core.platform.base import WindowInfo

logger = logging.getLogger(__name__)


@dataclass
class InspectorSnapshot:
    """What the inspector found at a point."""

    x: int
    y: int
    window: WindowInfo | None = None
    pixel_color: tuple[int, int, int] = (0, 0, 0)
    timestamp: float = 0.0


class DesktopInspector:
    """Live inspector that captures element info as the mouse moves."""

    def __init__(self) -> None:
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: list[callable] = []
        self._last_snapshot: InspectorSnapshot | None = None

    def start(self) -> None:
        """Start tracking the mouse cursor."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._track_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def on_update(self, callback: callable) -> None:
        """Register a callback for inspector updates."""
        self._callbacks.append(callback)

    def _track_loop(self) -> None:
        while self._running:
            try:
                snapshot = self._capture_snapshot()
                self._last_snapshot = snapshot
                for cb in self._callbacks:
                    try:
                        cb(snapshot)
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("Inspector error: %s", exc)
            time.sleep(0.1)

    def _capture_snapshot(self) -> InspectorSnapshot:
        from core.platform import platform
        import ctypes
        try:
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            x, y = pt.x, pt.y

            # Get pixel color
            hdc = ctypes.windll.user32.GetDC(0)
            color = ctypes.windll.gdi32.GetPixel(hdc, x, y)
            ctypes.windll.user32.ReleaseDC(0, hdc)
            r, g, b = color & 0xff, (color >> 8) & 0xff, (color >> 16) & 0xff

            # Get window under cursor
            windows = platform.window_system.get_windows(visible_only=True)
            window = None
            for w in windows:
                if w.x <= x <= w.x + w.width and w.y <= y <= w.y + w.height:
                    window = w
                    break

            return InspectorSnapshot(x=x, y=y, window=window, pixel_color=(r, g, b), timestamp=time.time())
        except Exception:
            return InspectorSnapshot(x=0, y=0, timestamp=time.time())

    @property
    def last_snapshot(self) -> InspectorSnapshot | None:
        return self._last_snapshot


__all__ = ["InspectorSnapshot", "DesktopInspector"]
