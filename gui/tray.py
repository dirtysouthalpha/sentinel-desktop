"""
Sentinel Desktop v2 — System tray integration.

Optional. When ``pystray`` is installed, the GUI can minimize itself to a
system tray icon instead of cluttering the taskbar — and the user can
right-click the icon to show/hide the window, stop a running agent, or
quit cleanly.

Without ``pystray`` everything degrades to the normal taskbar behaviour;
no error is shown.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

try:
    import pystray  # type: ignore
    from PIL import Image, ImageDraw

    _HAS_TRAY = True
except ImportError:
    _HAS_TRAY = False
    logger.debug("pystray/Pillow not available — tray icon disabled")


def is_available() -> bool:
    return _HAS_TRAY


def _make_icon_image() -> Image.Image:
    """Generate a simple orange hexagon icon (Sentinel brand) for the tray."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Hexagon
    import math

    cx, cy, r = size / 2, size / 2, size * 0.42
    points = [
        (cx + r * math.cos(math.radians(60 * i - 30)), cy + r * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]
    draw.polygon(points, fill=(232, 121, 58, 255), outline=(255, 200, 150, 255))
    return img


class SentinelTray:
    """Manages a single tray icon for the GUI.

    Construct, then call :meth:`run` from a background thread; it blocks the
    thread for the icon's lifetime. Stop via :meth:`stop`.
    """

    def __init__(
        self,
        on_show: Callable[[], None],
        on_hide: Callable[[], None],
        on_stop_agent: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        self._on_show = on_show
        self._on_hide = on_hide
        self._on_stop_agent = on_stop_agent
        self._on_quit = on_quit
        self._icon = None
        self._thread: threading.Thread | None = None

    def run(self) -> bool:
        """Start the tray icon. Returns True if it's running; False if pystray
        isn't available."""
        if not _HAS_TRAY:
            return False

        def _quit(icon: Any, item: Any) -> None:
            try:
                if self._on_quit:
                    self._on_quit()
            finally:
                icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("Show Sentinel", lambda i, _: self._on_show(), default=True),
            pystray.MenuItem("Hide", lambda i, _: self._on_hide()),
            pystray.MenuItem(
                "Stop running agent",
                lambda i, _: self._on_stop_agent() if self._on_stop_agent else None,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Sentinel", _quit),
        )
        self._icon = pystray.Icon(
            name="sentinel-desktop",
            icon=_make_icon_image(),
            title="Sentinel Desktop v2",
            menu=menu,
        )

        def _runner() -> None:
            try:
                self._icon.run()
            except Exception as exc:
                logger.warning("pystray run failed: %s", exc)

        self._thread = threading.Thread(target=_runner, daemon=True)
        self._thread.start()
        return True

    def notify(self, title: str, message: str) -> None:
        """Show a brief desktop notification via the tray icon."""
        if not self._icon:
            return
        try:
            self._icon.notify(message, title=title)
        except Exception as exc:
            logger.debug("tray notify failed: %s", exc)

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception as exc:
                logger.debug("Tray stop failed: %s", exc)
            self._icon = None
