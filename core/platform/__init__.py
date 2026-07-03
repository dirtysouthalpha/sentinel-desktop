"""Platform abstraction layer.

Detects the current OS and desktop environment, then provides a unified
interface for window management, input control, screen capture, and
application lifecycle. Backends: Windows, Linux (X11/Wayland), macOS,
and Headless (server/no-display).

Usage:
    from core.platform import platform
    windows = platform.window_system.get_windows()
    platform.input.click(100, 200)
    screenshot = platform.screen.capture()
"""

from __future__ import annotations

import logging
import os
import platform as _std_platform
from typing import Any

from .base import Backend
from .capabilities import Capabilities, detect_capabilities

logger = logging.getLogger(__name__)

# Singleton _Platform instance
_instance: _Platform | None = None


class _Platform:
    """Holds the active backend and exposes subsystem facades."""

    def __init__(self, backend: Backend, capabilities: Capabilities) -> None:
        self.backend = backend
        self.capabilities = capabilities
        self._window_system = backend.create_window_system()
        self._input = backend.create_input()
        self._screen = backend.create_screen()
        self._application = backend.create_application()
        self._power = backend.create_power()

    @property
    def window_system(self):
        return self._window_system

    @property
    def input(self):
        return self._input

    @property
    def screen(self):
        return self._screen

    @property
    def application(self):
        return self._application

    @property
    def power(self):
        return self._power


def _create_backend() -> Backend:
    """Select the best backend for this machine."""
    system = _std_platform.system()
    display = os.environ.get("DISPLAY")
    wayland = os.environ.get("WAYLAND_DISPLAY")
    session_type = os.environ.get("XDG_SESSION_TYPE", "")

    # Headless detection: no DISPLAY on Linux/BSD, or explicit HEADLESS flag
    headless_env = os.environ.get("SENTINEL_HEADLESS", "").lower() in ("1", "true", "yes")

    if system == "Windows":
        from .windows_backend import WindowsBackend

        return WindowsBackend()
    elif system == "Darwin":
        from .macos_backend import MacOSBackend

        return MacOSBackend()
    elif system == "Linux":
        if headless_env or (not display and not wayland and session_type != "x11"):
            from .headless_backend import HeadlessBackend

            logger.info("Linux headless environment detected, using HeadlessBackend")
            return HeadlessBackend()
        from .linux_backend import LinuxBackend

        return LinuxBackend()
    else:
        # Unknown OS — fall back to headless
        logger.warning("Unknown platform '%s', using HeadlessBackend", system)
        from .headless_backend import HeadlessBackend

        return HeadlessBackend()


def _initialize() -> _Platform:
    global _instance
    if _instance is None:
        backend = _create_backend()
        caps = detect_capabilities(backend)
        _instance = _Platform(backend, caps)
        logger.info(
            "Platform initialized: os=%s, backend=%s, headless=%s, display=%s",
            _std_platform.system(),
            backend.name,
            caps.headless,
            caps.has_display,
        )
    return _instance


def reset() -> None:
    """Force re-initialisation (used by tests)."""
    global _instance
    _instance = None


# Lazily-initialised public singleton.
# Import-time side effects are avoided — first access triggers detection.
class _LazyPlatform:
    """Proxy that initialises the real _Platform on first attribute access."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_initialize(), name)

    def __repr__(self) -> Any:
        if _instance is None:
            return "<Platform (uninitialised)>"
        return f"<Platform backend={_instance.backend.name} caps={_instance.capabilities}>"


# Module-level singleton: `from core.platform import platform`
platform = _LazyPlatform()

# Convenience re-exports for type hints.
__all__ = [
    "platform",
    "reset",
    "Backend",
    "Capabilities",
]
