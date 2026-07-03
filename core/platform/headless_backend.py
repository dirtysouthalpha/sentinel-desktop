"""Headless/server backend.

Used when no display is available (Docker, SSH-only, Windows Server without GUI).
All methods return safe stubs or raise informative errors. The agent engine
checks capabilities before calling, so these should rarely be invoked.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from .base import (
    ApplicationManager,
    Backend,
    InputController,
    MonitorInfo,
    PowerManager,
    ProcessInfo,
    ScreenCapture,
    WindowInfo,
    WindowSystem,
)

logger = logging.getLogger(__name__)


class _HeadlessError(Exception):
    """Raised when a GUI action is attempted in headless mode."""
    pass


# ---------------------------------------------------------------------------
# Window system
# ---------------------------------------------------------------------------

class _HeadlessWindowSystem:
    def get_windows(self, visible_only: bool = True) -> list[WindowInfo]:
        return []

    def get_focused_window(self) -> WindowInfo | None:
        return None

    def find_window(self, title: str) -> WindowInfo | None:
        return None

    def focus_window(self, handle: Any) -> bool:
        logger.warning("Cannot focus window in headless mode")
        return False

    def close_window(self, handle: Any) -> bool:
        logger.warning("Cannot close window in headless mode")
        return False

    def move_window(self, handle: Any, x: int, y: int) -> bool:
        logger.warning("Cannot move window in headless mode")
        return False

    def resize_window(self, handle: Any, w: int, h: int) -> bool:
        logger.warning("Cannot resize window in headless mode")
        return False

    def minimize_window(self, handle: Any) -> bool:
        return False

    def maximize_window(self, handle: Any) -> bool:
        return False


# ---------------------------------------------------------------------------
# Input controller
# ---------------------------------------------------------------------------

class _HeadlessInput:
    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        logger.warning("Cannot click in headless mode")

    def double_click(self, x: int, y: int, button: str = "left") -> None:
        pass

    def move_to(self, x: int, y: int) -> None:
        pass

    def drag(self, x1: int, y1: int, x2: int, y2: int, button: str = "left") -> None:
        pass

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> None:
        pass

    def key_press(self, key: str) -> None:
        logger.warning("Cannot press key '%s' in headless mode", key)

    def key_down(self, key: str) -> None:
        pass

    def key_up(self, key: str) -> None:
        pass

    def type_text(self, text: str, interval: float = 0.02) -> None:
        logger.warning("Cannot type text in headless mode")

    def hotkey(self, *keys: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Screen capture
# ---------------------------------------------------------------------------

class _HeadlessScreen:
    def capture(self, region: tuple[int, int, int, int] | None = None) -> Any:
        from PIL import Image
        return Image.new("RGB", (1920, 1080), (0, 0, 0))

    def capture_monitor(self, index: int) -> Any:
        return self.capture()

    def get_monitors(self) -> list[MonitorInfo]:
        return [MonitorInfo(index=1, x=0, y=0, width=1920, height=1080, is_primary=True)]

    def get_primary_size(self) -> tuple[int, int]:
        return 1920, 1080

    def capture_base64(self, region: tuple[int, int, int, int] | None = None, fmt: str = "PNG") -> str:
        import base64
        import io
        from PIL import Image
        img = Image.new("RGB", self.get_primary_size(), (30, 30, 30))
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# Application manager
# ---------------------------------------------------------------------------

class _HeadlessApplicationManager:
    def launch(self, command: str | list[str], **kwargs: Any) -> int | None:
        try:
            if isinstance(command, list):
                proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
            else:
                proc = subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
            return proc.pid
        except Exception as exc:
            logger.warning("launch %r failed: %s", command, exc)
            return None

    def terminate(self, pid: int) -> bool:
        try:
            os.kill(pid, 9)
            return True
        except OSError:
            return False

    def find_processes(self, name: str) -> list[ProcessInfo]:
        return [p for p in self.list_processes() if name.lower() in p.name.lower()]

    def list_processes(self) -> list[ProcessInfo]:
        result = []
        try:
            import psutil
            for p in psutil.process_iter(["pid", "name", "exe", "cpu_percent", "memory_info"]):
                try:
                    info = p.info
                    result.append(ProcessInfo(
                        pid=info["pid"] or 0,
                        name=info.get("name", ""),
                        executable=info.get("exe", "") or "",
                        cpu_percent=info.get("cpu_percent", 0.0) or 0.0,
                        memory_mb=(info.get("memory_info").rss / 1024 / 1024) if info.get("memory_info") else 0.0,
                    ))
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except ImportError:
            pass
        return result

    def is_running(self, name: str) -> bool:
        return any(name.lower() in p.name.lower() for p in self.list_processes())


# ---------------------------------------------------------------------------
# Power management
# ---------------------------------------------------------------------------

class _HeadlessPower:
    def shutdown(self, force: bool = False, delay: int = 0) -> None:
        logger.warning("shutdown not available in headless container")

    def restart(self, force: bool = False, delay: int = 0) -> None:
        logger.warning("restart not available in headless container")

    def lock(self) -> None:
        pass

    def sleep(self) -> None:
        pass

    def hibernate(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

class HeadlessBackend(Backend):
    name = "headless"

    def create_window_system(self) -> WindowSystem:
        return _HeadlessWindowSystem()

    def create_input(self) -> InputController:
        return _HeadlessInput()

    def create_screen(self) -> ScreenCapture:
        return _HeadlessScreen()

    def create_application(self) -> ApplicationManager:
        return _HeadlessApplicationManager()

    def create_power(self) -> PowerManager:
        return _HeadlessPower()
