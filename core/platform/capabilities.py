"""Capability detection — what can this machine actually do?

Used by the agent engine to decide which actions are available without
crashing at runtime on headless servers or restricted desktops.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field

from .base import Backend

logger = logging.getLogger(__name__)


@dataclass
class Capabilities:
    """Detected runtime capabilities."""

    os: str = ""
    arch: str = ""
    headless: bool = False
    has_display: bool = False
    has_gpu: bool = False
    has_mouse: bool = False
    has_keyboard: bool = False
    has_clipboard: bool = False
    has_audio: bool = False
    has_webcam: bool = False
    has_ocr: bool = False
    has_vision: bool = False
    has_browser: bool = False
    has_ssh: bool = False
    has_docker: bool = False
    has_tailscale: bool = False
    monitors: int = 1
    screen_width: int = 0
    screen_height: int = 0
    python_version: str = ""
    # Module availability
    has_pyautogui: bool = False
    has_pillow: bool = False
    has_mss: bool = False
    has_pywin32: bool = False
    has_uiautomation: bool = False
    has_xlib: bool = False
    has_wayland: bool = False
    has_quartz: bool = False
    # Warnings collected during detection
    warnings: list[str] = field(default_factory=list)


def detect_capabilities(backend: Backend) -> Capabilities:
    """Run full capability detection for the active backend."""
    caps = Capabilities()
    caps.os = platform.system()
    caps.arch = platform.machine()
    caps.python_version = platform.python_version()

    # Display
    _detect_display(caps)

    # Hardware peripherals
    _detect_hardware(caps)

    # Modules
    _detect_modules(caps)

    # External tools
    _detect_tools(caps)

    # Screen resolution
    _detect_resolution(backend, caps)

    # Log summary
    enabled = [k for k, v in caps.__dict__.items() if v is True and not k.startswith("_")]
    logger.info("Capabilities: %s", ", ".join(enabled))

    if caps.warnings:
        for w in caps.warnings:
            logger.warning("Capability warning: %s", w)

    return caps


def _detect_display(c: Capabilities) -> None:
    """Detect display availability."""
    if c.os == "Windows":
        c.has_display = True  # Windows always has a display handle in GUI sessions
        # On Windows Server / headless, check for GetSystemMetrics
        try:
            import ctypes

            user32 = ctypes.windll.user32
            if user32.GetSystemMetrics(0) == 0 or user32.GetSystemMetrics(1) == 0:
                c.has_display = False
        except Exception:
            pass
    elif c.os == "Darwin":
        c.has_display = True  # macOS always has display
    elif c.os == "Linux":
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            c.has_display = True
        elif os.environ.get("XDG_SESSION_TYPE") in ("x11", "wayland"):
            c.has_display = True
        else:
            c.has_display = False

    c.headless = not c.has_display or os.environ.get("SENTINEL_HEADLESS", "").lower() in ("1", "true")


def _detect_hardware(c: Capabilities) -> None:
    """Detect peripherals (conservative — assume present unless proven absent)."""
    c.has_mouse = c.has_display
    c.has_keyboard = c.has_display
    c.has_clipboard = c.has_display

    # Audio
    if shutil.which("pactl") or shutil.which("pactl") or shutil.which("osascript") or c.os == "Windows":
        c.has_audio = True

    # Webcam
    if c.os == "Linux":
        c.has_webcam = os.path.exists("/dev/video0")
    elif c.os == "Windows":
        c.has_webcam = True  # most Windows machines have one
    elif c.os == "Darwin":
        c.has_webcam = True


def _detect_modules(c: Capabilities) -> None:
    """Detect optional Python modules."""
    try:
        import pyautogui  # noqa: F401

        c.has_pyautogui = True
    except ImportError:
        c.warnings.append("pyautogui not installed — input simulation unavailable")

    try:
        from PIL import Image  # noqa: F401

        c.has_pillow = True
    except ImportError:
        c.warnings.append("Pillow not installed — image processing limited")

    try:
        import mss  # noqa: F401

        c.has_mss = True
    except ImportError:
        pass

    try:
        import pytesseract  # noqa: F401

        c.has_ocr = True
    except ImportError:
        pass

    # Platform-specific modules
    if c.os == "Windows":
        try:
            import win32gui  # noqa: F401

            c.has_pywin32 = True
        except ImportError:
            pass
        try:
            import uiautomation  # noqa: F401

            c.has_uiautomation = True
        except ImportError:
            pass
    elif c.os == "Linux":
        try:
            import Xlib  # noqa: F401

            c.has_xlib = True
        except ImportError:
            pass
        if os.environ.get("WAYLAND_DISPLAY"):
            c.has_wayland = True
            c.warnings.append("Wayland detected — window manipulation may be limited due to security restrictions")
    elif c.os == "Darwin":
        try:
            import Quartz  # noqa: F401

            c.has_quartz = True
        except ImportError:
            pass
        try:
            import AppKit  # noqa: F401
        except ImportError:
            pass


def _detect_tools(c: Capabilities) -> None:
    """Detect external tools."""
    c.has_ssh = shutil.which("ssh") is not None

    if shutil.which("docker"):
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
            c.has_docker = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            c.has_docker = False

    c.has_tailscale = shutil.which("tailscale") is not None

    # Browser
    for browser in ("chromium", "chromium-browser", "google-chrome", "firefox", "playwright"):
        if shutil.which(browser):
            c.has_browser = True
            break


def _detect_resolution(backend: Backend, c: Capabilities) -> None:
    """Get screen resolution from the backend."""
    try:
        screen = backend.create_screen()
        c.screen_width, c.screen_height = screen.get_primary_size()
        c.monitors = len(screen.get_monitors())
        if c.screen_width > 0 and c.screen_height > 0:
            c.has_display = True
    except Exception as exc:
        logger.debug("Resolution detection failed: %s", exc)


__all__ = ["Capabilities", "detect_capabilities"]
