"""Abstract base classes for platform backends.

Every backend (Windows, Linux, macOS, Headless) implements these interfaces.
The active backend is selected at import time by ``core.platform``.
"""

from __future__ import annotations

import enum
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ###########################################################################
# Data classes
# ###########################################################################


@dataclass(frozen=True)
class WindowInfo:
    """Unified window description returned by every backend."""

    title: str
    x: int
    y: int
    width: int
    height: int
    is_focused: bool = False
    is_visible: bool = True
    handle: Any = None  # native handle (HWND, Window XID, NSWindow*)
    pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "is_focused": self.is_focused,
            "is_visible": self.is_visible,
            "pid": self.pid,
        }


@dataclass(frozen=True)
class MonitorInfo:
    """Single monitor description."""

    index: int
    x: int
    y: int
    width: int
    height: int
    is_primary: bool = False
    name: str = ""
    scale: float = 1.0


@dataclass(frozen=True)
class ProcessInfo:
    """Running process description."""

    pid: int
    name: str
    executable: str = ""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0


class MouseButton(enum.Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class KeyAction(enum.Enum):
    PRESS = "press"
    DOWN = "down"
    UP = "up"


# ###########################################################################
# Abstract subsystems (each backend provides one)
# ###########################################################################


class WindowSystem(Protocol):
    """Abstract window management interface."""

    def get_windows(self, visible_only: bool = True) -> list[WindowInfo]: ...
    def get_focused_window(self) -> WindowInfo | None: ...
    def find_window(self, title: str) -> WindowInfo | None: ...
    def focus_window(self, handle: Any) -> bool: ...
    def close_window(self, handle: Any) -> bool: ...
    def move_window(self, handle: Any, x: int, y: int) -> bool: ...
    def resize_window(self, handle: Any, w: int, h: int) -> bool: ...
    def minimize_window(self, handle: Any) -> bool: ...
    def maximize_window(self, handle: Any) -> bool: ...


class InputController(Protocol):
    """Abstract mouse/keyboard input."""

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None: ...
    def double_click(self, x: int, y: int, button: str = "left") -> None: ...
    def move_to(self, x: int, y: int) -> None: ...
    def drag(self, x1: int, y1: int, x2: int, y2: int, button: str = "left") -> None: ...
    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> None: ...
    def key_press(self, key: str) -> None: ...
    def key_down(self, key: str) -> None: ...
    def key_up(self, key: str) -> None: ...
    def type_text(self, text: str, interval: float = 0.02) -> None: ...
    def hotkey(self, *keys: str) -> None: ...


class ScreenCapture(Protocol):
    """Abstract screen capture."""

    def capture(self, region: tuple[int, int, int, int] | None = None) -> Any: ...
    def capture_monitor(self, index: int) -> Any: ...
    def get_monitors(self) -> list[MonitorInfo]: ...
    def get_primary_size(self) -> tuple[int, int]: ...
    def capture_base64(self, region: tuple[int, int, int, int] | None = None, fmt: str = "PNG") -> str: ...


class ApplicationManager(Protocol):
    """Abstract application lifecycle."""

    def launch(self, command: str | list[str], **kwargs: Any) -> int | None: ...
    def terminate(self, pid: int) -> bool: ...
    def find_processes(self, name: str) -> list[ProcessInfo]: ...
    def list_processes(self) -> list[ProcessInfo]: ...
    def is_running(self, name: str) -> bool: ...


class PowerManager(Protocol):
    """Abstract power/system management."""

    def shutdown(self, force: bool = False, delay: int = 0) -> None: ...
    def restart(self, force: bool = False, delay: int = 0) -> None: ...
    def lock(self) -> None: ...
    def sleep(self) -> None: ...
    def hibernate(self) -> None: ...


# ###########################################################################
# Backend
# ###########################################################################


class Backend(ABC):
    """Top-level backend that spawns concrete subsystem instances."""

    name: str = "abstract"

    @abstractmethod
    def create_window_system(self) -> WindowSystem: ...

    @abstractmethod
    def create_input(self) -> InputController: ...

    @abstractmethod
    def create_screen(self) -> ScreenCapture: ...

    @abstractmethod
    def create_application(self) -> ApplicationManager: ...

    @abstractmethod
    def create_power(self) -> PowerManager: ...
