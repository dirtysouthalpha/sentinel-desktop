"""Tests for core.platform — platform abstraction layer."""

from __future__ import annotations

import os
import sys

import pytest

# Ensure tests can find the core module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_platform_import():
    """platform module imports without errors."""
    from core.platform import platform
    assert platform is not None


def test_platform_lazy_init():
    """Platform doesn't initialize until first attribute access."""
    import core.platform as _pmod
    from core.platform import platform, reset
    reset()
    # Before access, internal instance is None
    assert _pmod._instance is None
    # Access triggers init
    _ = platform.capabilities
    assert _pmod._instance is not None
    reset()


def test_capabilities_dataclass():
    """Capabilities can be created with defaults."""
    from core.platform.capabilities import Capabilities
    c = Capabilities()
    assert c.os == ""
    assert c.headless is False
    assert isinstance(c.warnings, list)


def test_capabilities_to_dict_if_needed():
    """All capability fields are accessible."""
    from core.platform.capabilities import Capabilities
    c = Capabilities(os="Windows", headless=True, has_display=False)
    assert c.os == "Windows"
    assert c.headless is True
    assert c.has_display is False


def test_window_info_dataclass():
    """WindowInfo creates correctly."""
    from core.platform.base import WindowInfo
    w = WindowInfo(title="test", x=10, y=20, width=100, height=200)
    assert w.title == "test"
    assert w.x == 10
    d = w.to_dict()
    assert d["title"] == "test"
    assert d["width"] == 100


def test_monitor_info_dataclass():
    """MonitorInfo creates correctly."""
    from core.platform.base import MonitorInfo
    m = MonitorInfo(index=1, x=0, y=0, width=1920, height=1080, is_primary=True)
    assert m.is_primary
    assert m.width == 1920


def test_backend_abstract_methods():
    """Backend ABC requires all subsystem factory methods."""
    from core.platform.base import Backend
    # Can't instantiate directly
    with pytest.raises(TypeError):
        Backend()


@pytest.mark.skipif(sys.platform != "win32", reason="pygetwindow Windows-only")
def test_windows_backend_creates():
    """WindowsBackend creates all subsystems."""
    from core.platform.windows_backend import WindowsBackend
    be = WindowsBackend()
    assert be.name == "windows"
    assert be.create_window_system() is not None
    assert be.create_input() is not None
    assert be.create_screen() is not None
    assert be.create_application() is not None
    assert be.create_power() is not None


def test_linux_backend_creates():
    """LinuxBackend creates all subsystems."""
    from core.platform.linux_backend import LinuxBackend
    be = LinuxBackend()
    assert be.name == "linux"
    assert be.create_window_system() is not None
    assert be.create_input() is not None
    assert be.create_screen() is not None
    assert be.create_application() is not None
    assert be.create_power() is not None


def test_macos_backend_creates():
    """MacOSBackend creates all subsystems."""
    from core.platform.macos_backend import MacOSBackend
    be = MacOSBackend()
    assert be.name == "macos"
    assert be.create_window_system() is not None
    assert be.create_input() is not None
    assert be.create_screen() is not None
    assert be.create_application() is not None
    assert be.create_power() is not None


def test_headless_backend_creates():
    """HeadlessBackend creates all subsystems."""
    from core.platform.headless_backend import HeadlessBackend
    be = HeadlessBackend()
    assert be.name == "headless"
    assert be.create_window_system() is not None
    assert be.create_input() is not None
    assert be.create_screen() is not None
    assert be.create_application() is not None
    assert be.create_power() is not None


def test_headless_window_system_returns_empty():
    """Headless window system returns empty lists/None."""
    from core.platform.headless_backend import _HeadlessWindowSystem
    ws = _HeadlessWindowSystem()
    assert ws.get_windows() == []
    assert ws.get_focused_window() is None
    assert ws.find_window("anything") is None
    assert ws.focus_window(0) is False
    assert ws.close_window(0) is False


def test_headless_input_does_not_raise():
    """Headless input methods don't raise exceptions."""
    from core.platform.headless_backend import _HeadlessInput
    inp = _HeadlessInput()
    inp.click(0, 0)
    inp.move_to(100, 100)
    inp.key_press("a")
    inp.type_text("hello")
    inp.hotkey("ctrl", "c")
    inp.scroll(3)


def test_headless_screen_returns_placeholder():
    """Headless screen returns a placeholder image, not None."""
    from core.platform.headless_backend import _HeadlessScreen
    sc = _HeadlessScreen()
    img = sc.capture()
    assert img is not None
    assert sc.get_primary_size() == (1920, 1080)
    assert len(sc.get_monitors()) >= 1


def test_capabilities_detect_runs():
    """detect_capabilities returns a populated Capabilities object."""
    from core.platform.capabilities import Capabilities, detect_capabilities
    from core.platform.windows_backend import WindowsBackend
    c = detect_capabilities(WindowsBackend())
    assert isinstance(c, Capabilities)
    assert c.os != ""
    assert c.python_version != ""


def test_platform_singleton_after_init():
    """After init, platform.backend is set."""
    import core.platform as _pmod
    from core.platform import platform, reset
    reset()
    _ = platform.backend  # trigger init
    assert platform.backend.name in ("windows", "linux", "macos", "headless")
    assert _pmod._instance is not None
    reset()


def test_reset_clears_singleton():
    """reset() clears the singleton so re-init works."""
    import core.platform as _pmod
    from core.platform import platform, reset
    reset()
    assert _pmod._instance is None
    _ = platform.backend  # trigger init
    assert _pmod._instance is not None
    reset()
    assert _pmod._instance is None
