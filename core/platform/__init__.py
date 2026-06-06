"""Sentinel Desktop v4.0 — Platform Abstraction Layer.

Provides a unified interface for desktop automation across Windows, Linux,
and macOS. Each OS gets a backend that implements the same abstract
interfaces, so the rest of the codebase never needs to know what OS it's on.

Usage::

    from core.platform import get_backend

    backend = get_backend()
    tree = backend.accessibility.get_tree()
    backend.stealth.click(500, 300)
"""

from __future__ import annotations

import logging
import platform as _platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.platform.base import (
        AccessibilityBackend,
        CredentialBackend,
        OverlayBackend,
        ShellBackend,
        StealthInputBackend,
        WindowBackend,
    )

logger = logging.getLogger(__name__)

# ── Platform detection ───────────────────────────────────────────────────

_SYSTEM = _platform.system()  # "Windows", "Linux", "Darwin"


def current_platform() -> str:
    """Return the normalized platform name: ``'windows'``, ``'linux'``, or ``'macos'``."""
    return {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(
        _SYSTEM,
        "unknown",
    )


def is_windows() -> bool:
    """Return ``True`` on Windows."""
    return _SYSTEM == "Windows"


def is_linux() -> bool:
    """Return ``True`` on Linux."""
    return _SYSTEM == "Linux"


def is_macos() -> bool:
    """Return ``True`` on macOS."""
    return _SYSTEM == "Darwin"


# ── Lazy singleton backend ──────────────────────────────────────────────

_backend: PlatformBackend | None = None


def get_backend() -> PlatformBackend:
    """Return the platform-specific backend (lazy-loaded singleton).

    Creates the backend on first call and caches it. Subsequent calls return
    the same instance.
    """
    global _backend
    if _backend is None:
        _backend = _create_backend()
    return _backend


def _create_backend() -> PlatformBackend:
    """Instantiate the correct backend for the current OS."""
    plat = current_platform()
    if plat == "windows":
        from core.platform.windows_backend import WindowsBackend

        return WindowsBackend()
    if plat == "linux":
        from core.platform.linux_backend import LinuxBackend

        return LinuxBackend()
    if plat == "macos":
        from core.platform.macos_backend import MacOSBackend

        return MacOSBackend()
    # Unknown — return a no-op backend so nothing crashes
    logger.warning("Unsupported platform '%s' — using no-op backend", _SYSTEM)
    from core.platform.base import NoOpBackend

    return NoOpBackend()


def reset_backend() -> None:
    """Reset the cached backend (useful for testing)."""
    global _backend
    _backend = None


# ── Aggregated backend class ────────────────────────────────────────────


class PlatformBackend:
    """Aggregated backend that holds all platform-specific subsystems.

    Each subsystem (accessibility, stealth input, credentials, etc.) is
    accessed as a property that returns the OS-specific implementation.
    """

    def __init__(self) -> None:
        self._accessibility: AccessibilityBackend | None = None
        self._stealth: StealthInputBackend | None = None
        self._credentials: CredentialBackend | None = None
        self._shell: ShellBackend | None = None
        self._window: WindowBackend | None = None
        self._overlay: OverlayBackend | None = None

    @property
    def accessibility(self) -> AccessibilityBackend:
        """Return the accessibility tree backend."""
        raise NotImplementedError

    @property
    def stealth(self) -> StealthInputBackend:
        """Return the stealth input backend."""
        raise NotImplementedError

    @property
    def credentials(self) -> CredentialBackend:
        """Return the credential storage backend."""
        raise NotImplementedError

    @property
    def shell(self) -> ShellBackend:
        """Return the shell/scripting backend."""
        raise NotImplementedError

    @property
    def window(self) -> WindowBackend:
        """Return the window management backend."""
        raise NotImplementedError

    @property
    def overlay(self) -> OverlayBackend:
        """Return the overlay backend for visual feedback."""
        raise NotImplementedError

    @property
    def default_shell(self) -> str:
        """Return the default shell executable for this platform."""
        raise NotImplementedError
