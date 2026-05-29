"""
Sentinel Desktop v3.0 — System Tray Icon.

Manages a persistent system tray icon with a rich context menu for quick
access to common actions: starting tasks, recording, running scripts, and
launching IT support quick actions (Disk Cleanup, Network Diagnostics,
Event Log export).

Uses ``pystray`` for the tray icon itself and ``Pillow`` (PIL) for the
icon image.  If either library is missing the module degrades gracefully —
the ``start()`` method simply returns *False* and all other calls become
no-ops.

Typical usage::

    from gui.system_tray import SystemTrayIcon

    tray = SystemTrayIcon(app)
    tray.start()                       # returns True if running
    tray.update_status("running")      # green circle
    tray.show_notification("Done", "Task completed.")
    tray.stop()                        # clean shutdown
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gui.app import SentinelApp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency detection
# ---------------------------------------------------------------------------

try:
    import pystray  # type: ignore[import-untyped]

    _HAS_PYSTRAY = True
except ImportError:
    _HAS_PYSTRAY = False
    logger.debug("pystray not available — system tray disabled")

try:
    from PIL import Image, ImageDraw  # type: ignore[import-untyped]

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False
    logger.debug("Pillow not available — system tray icon disabled")

_AVAILABLE = _HAS_PYSTRAY and _HAS_PIL


def is_available() -> bool:
    """Return *True* when both ``pystray`` and ``Pillow`` are importable."""
    return _AVAILABLE


# ---------------------------------------------------------------------------
# Icon generation helpers
# ---------------------------------------------------------------------------

# Colour palette for the status circle.
_STATUS_COLOURS = {
    "idle": (136, 136, 136),  # grey
    "running": (46, 204, 113),  # green
    "recording": (231, 76, 60),  # red
    "warning": (241, 196, 15),  # yellow
    "error": (192, 57, 43),  # dark red
    "paused": (52, 152, 219),  # blue
}

_ICON_SIZE = 64


def _create_icon_image(
    status: str = "idle",
) -> Image.Image:
    """Render a 64×64 RGBA image with a coloured status circle.

    Falls back to a tiny 4×4 pixel placeholder if PIL is unavailable.
    """
    if not _HAS_PIL:
        raise RuntimeError("Pillow is required to generate the tray icon")

    size = _ICON_SIZE
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    colour = _STATUS_COLOURS.get(status, _STATUS_COLOURS["idle"])

    # Outer ring (slightly lighter)
    ring_colour = tuple(min(255, c + 40) for c in colour)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=colour,
        outline=ring_colour,
        width=3,
    )

    # Small inner dot for visual depth
    inner_margin = size // 3
    draw.ellipse(
        [inner_margin, inner_margin, size - inner_margin, size - inner_margin],
        fill=ring_colour,
    )

    return img


# ---------------------------------------------------------------------------
# IT Support script paths
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "it_support"

_IT_QUICK_ACTIONS = [
    {
        "label": "💿 Disk Cleanup",
        "script": _SCRIPTS_DIR / "disk_cleanup.json",
        "description": "Run Windows Disk Cleanup utility",
    },
    {
        "label": "🌐 Network Diag",
        "script": _SCRIPTS_DIR / "network_diag.json",
        "description": "Run network diagnostics (ipconfig, ping, nslookup)",
    },
    {
        "label": "📋 Event Log",
        "script": _SCRIPTS_DIR / "event_log_errors.json",
        "description": "Export recent Event Log errors to desktop",
    },
]


# ---------------------------------------------------------------------------
# SystemTrayIcon
# ---------------------------------------------------------------------------


class SystemTrayIcon:
    """System tray icon with context menu for Sentinel Desktop v3.0.

    Parameters
    ----------
    app : SentinelApp
        Reference to the main application instance.
    """

    # Status strings accepted by *update_status*.
    VALID_STATUSES = frozenset(_STATUS_COLOURS.keys())

    def __init__(self, app: SentinelApp) -> None:
        self._app = app
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None
        self._current_status: str = "idle"
        self._running: threading.Event = threading.Event()

    # ── Public API ──────────────────────────────────────────────────────

    def start(self) -> bool:
        """Create and display the tray icon.

        Returns *True* if the icon was started successfully, *False* if
        ``pystray`` / ``Pillow`` are unavailable.
        """
        if not _AVAILABLE:
            logger.info("System tray skipped — pystray and/or Pillow not installed.")
            return False

        if self._icon is not None:
            logger.debug("Tray icon already running.")
            return True

        try:
            icon_image = _create_icon_image(self._current_status)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("Failed to create tray icon image: %s", exc)
            return False

        menu = self._build_menu()

        self._icon = pystray.Icon(
            name="sentinel-desktop",
            icon=icon_image,
            title="Sentinel Desktop v3.0 — Idle",
            menu=menu,
        )

        def _runner() -> None:
            try:
                self._running.set()
                self._icon.run()  # type: ignore[union-attr]
            except (OSError, RuntimeError) as exc:
                logger.warning("pystray event loop exited with error: %s", exc)
            finally:
                self._running.clear()

        self._thread = threading.Thread(target=_runner, daemon=True, name="tray-icon")
        self._thread.start()
        logger.info("System tray icon started.")
        return True

    def stop(self) -> None:
        """Stop the tray icon and clean up.  Safe to call multiple times."""
        if self._icon is None:
            return

        icon = self._icon
        self._icon = None  # prevent re-entrancy

        try:
            icon.stop()
        except (OSError, RuntimeError) as exc:
            logger.debug("Error stopping tray icon: %s", exc)

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            self._thread = None

        self._running.clear()
        logger.info("System tray icon stopped.")

    def update_status(self, status: str) -> None:
        """Change the tray icon colour.  Valid: idle, running, recording, warning, error, paused."""
        if status not in self.VALID_STATUSES:
            logger.warning("Unknown tray status: %r (ignored)", status)
            return

        self._current_status = status

        if self._icon is None or not _AVAILABLE:
            return

        try:
            new_image = _create_icon_image(status)
            # Capitalise for the tooltip.
            label = status.replace("_", " ").title()
            self._icon.icon = new_image
            self._icon.title = f"Sentinel Desktop v3.0 — {label}"
            # Refresh the visible icon on platforms that support it.
            if hasattr(self._icon, "update_menu"):
                self._icon.update_menu()
        except (OSError, ValueError, RuntimeError) as exc:
            logger.debug("Failed to update tray status icon: %s", exc)

    def show_notification(self, title: str, msg: str) -> None:
        """Display a desktop notification balloon from the tray icon."""
        if self._icon is None:
            return

        try:
            self._icon.notify(msg, title=title)
        except (OSError, RuntimeError) as exc:
            logger.debug("Tray notification failed: %s", exc)

    @property
    def is_running(self) -> bool:
        """Return *True* if the tray icon event loop is active."""
        return self._running.is_set()

    # ── Menu construction ───────────────────────────────────────────────

    def _build_it_actions_submenu(self) -> pystray.Menu:
        """Build the IT Quick Actions submenu."""
        it_items = []
        for action_info in _IT_QUICK_ACTIONS:
            script_path = action_info["script"]
            it_items.append(
                pystray.MenuItem(
                    action_info["label"],
                    lambda _icon, _item, sp=script_path: self._run_it_script(sp),
                )
            )
        return pystray.Menu(*it_items)

    def _build_menu(self) -> pystray.Menu:
        """Build the full right-click context menu."""
        return pystray.Menu(
            pystray.MenuItem("▶ New Task", self._on_new_task, default=True),
            pystray.MenuItem("⏺ Record", self._on_record),
            pystray.MenuItem("▶ Run Last Script", self._on_run_last_script),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔧 IT Quick Actions", self._build_it_actions_submenu()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda text: f"Status: {self._current_status.replace('_', ' ').title()}",
                lambda icon, item: None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show Window", lambda _icon, _item: self._show_window()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        )

    # ── Menu callbacks ──────────────────────────────────────────────────

    def _on_new_task(self, icon: Any, item: Any) -> None:
        """Show window and focus the input."""
        self._invoke_on_app("_tray_new_task")

    def _on_record(self, icon: Any, item: Any) -> None:
        """Toggle recording."""
        self._invoke_on_app("_tray_toggle_record")

    def _on_run_last_script(self, icon: Any, item: Any) -> None:
        """Run the most recently used script."""
        self._invoke_on_app("_tray_run_last_script")

    def _run_it_script(self, script_path: Path) -> None:
        """Run an IT support script from the quick-actions menu."""
        if not script_path.is_file():
            logger.warning("IT script not found: %s", script_path)
            self.show_notification(
                "Script Missing",
                f"Could not find: {script_path.name}",
            )
            return
        # Delegate to the app so execution happens on the GUI thread.
        self._invoke_on_app("_tray_run_script", str(script_path))

    def _show_window(self) -> None:
        """Restore the main window from minimized / hidden state."""
        self._invoke_on_app("_tray_show_window")

    def _on_exit(self, icon: Any, item: Any) -> None:
        """Shut down the application."""
        self._invoke_on_app("_tray_quit")

    # ── Thread-safe app invocation ──────────────────────────────────────

    def _invoke_on_app(self, method_name: str, *args: Any) -> None:
        """Safely invoke a method on the app via ``root.after(0, ...)``."""
        app = self._app
        if app is None:
            return

        fn = getattr(app, method_name, None)
        if fn is None:
            logger.debug("App does not implement %s — tray action ignored.", method_name)
            return

        try:
            app.root.after(0, lambda: fn(*args))
        except RuntimeError:
            # Tk root may already be destroyed during shutdown.
            logger.debug("Could not schedule %s — root destroyed?", method_name)
