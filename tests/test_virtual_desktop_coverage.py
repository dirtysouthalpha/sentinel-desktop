"""Coverage tests for virtual_desktop.py — stub and delegation paths testable on Linux.

Targets _StubVirtualDesktop (lines 604-683) and VirtualDesktop wrapper
(lines 704-829) — specifically the delegation methods, context manager,
and repr which are platform-agnostic.
"""

from unittest.mock import MagicMock, patch

import subprocess

import pytest

from core import virtual_desktop


# ---------------------------------------------------------------------------
# _StubVirtualDesktop — directly tested (it's the impl on Linux)
# ---------------------------------------------------------------------------

class TestStubLaunchApp:
    """_StubVirtualDesktop.launch_app — subprocess fallback paths."""

    def test_launch_app_success_with_args(self):
        """launch_app with valid path and args starts a subprocess."""
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        mock_proc = MagicMock()
        mock_proc.pid = 42
        with patch("core.virtual_desktop.subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = stub.launch_app("/usr/bin/echo", args="hello")
        assert result["success"] is True
        assert result["pid"] == 42
        mock_popen.assert_called_once_with(
            ["/usr/bin/echo", "hello"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_launch_app_success_no_args(self):
        """launch_app with path only — no args appended to cmd."""
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        mock_proc = MagicMock()
        mock_proc.pid = 99
        with patch("core.virtual_desktop.subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = stub.launch_app("/usr/bin/ls")
        assert result["success"] is True
        assert result["pid"] == 99
        mock_popen.assert_called_once_with(
            ["/usr/bin/ls"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_launch_app_failure_returns_error(self):
        """launch_app when Popen raises — returns error dict."""
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        with patch("core.virtual_desktop.subprocess.Popen", side_effect=FileNotFoundError("nope")):
            result = stub.launch_app("/nonexistent/binary")
        assert result["success"] is False
        assert result["pid"] is None
        assert "nope" in result["output"]


class TestStubListWindows:
    """_StubVirtualDesktop.list_windows — fallback delegation."""

    def test_list_windows_delegates_to_window_manager(self):
        """When window_manager.list_windows is available, delegates to it."""
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        expected = [{"title": "test", "x": 0, "y": 0, "width": 100, "height": 100}]
        with patch("core.window_manager.list_windows", return_value=expected):
            result = stub.list_windows()
        assert result == expected

    def test_list_windows_import_error_returns_empty(self):
        """When window_manager can't be imported, returns empty list."""
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        with patch.dict("sys.modules", {"core.window_manager": None}):
            # Force re-import to fail
            result = stub.list_windows()
        assert isinstance(result, list)


class TestStubScreenshot:
    """_StubVirtualDesktop.screenshot — pyautogui capture."""

    def test_screenshot_returns_image(self):
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        mock_img = MagicMock()
        with patch("pyautogui.screenshot", return_value=mock_img):
            result = stub.screenshot()
        assert result is mock_img

    def test_screenshot_failure_returns_none(self):
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        with patch("pyautogui.screenshot", side_effect=OSError("no display")):
            result = stub.screenshot()
        assert result is None


class TestStubContextManager:
    """_StubVirtualDesktop context manager and other no-op methods."""

    def test_create_returns_false(self):
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        assert stub.create() is False

    def test_switch_to_returns_false(self):
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        assert stub.switch_to() is False

    def test_switch_back_returns_false(self):
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        assert stub.switch_back() is False

    def test_close_is_noop(self):
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        stub.close()  # should not raise

    def test_context_manager(self):
        stub = virtual_desktop._StubVirtualDesktop("TestDesk")
        with stub as s:
            assert s is stub


# ---------------------------------------------------------------------------
# VirtualDesktop wrapper — delegation tests (works on Linux via stub)
# ---------------------------------------------------------------------------

class TestVirtualDesktopWrapper:
    """VirtualDesktop delegates to _StubVirtualDesktop on Linux."""

    def test_create_delegates(self):
        vd = virtual_desktop.VirtualDesktop("TestVD")
        assert vd.create() is False  # stub always returns False

    def test_switch_to_delegates(self):
        vd = virtual_desktop.VirtualDesktop("TestVD")
        assert vd.switch_to() is False

    def test_switch_back_delegates(self):
        vd = virtual_desktop.VirtualDesktop("TestVD")
        assert vd.switch_back() is False

    def test_close_delegates(self):
        vd = virtual_desktop.VirtualDesktop("TestVD")
        vd.close()  # should not raise

    def test_launch_app_delegates(self):
        vd = virtual_desktop.VirtualDesktop("TestVD")
        mock_proc = MagicMock()
        mock_proc.pid = 55
        with patch("core.virtual_desktop.subprocess.Popen", return_value=mock_proc):
            result = vd.launch_app("/bin/true")
        assert result["success"] is True
        assert result["pid"] == 55

    def test_launch_app_with_args_delegates(self):
        vd = virtual_desktop.VirtualDesktop("TestVD")
        mock_proc = MagicMock()
        mock_proc.pid = 77
        with patch("core.virtual_desktop.subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = vd.launch_app("/bin/echo", args="--help")
        assert result["success"] is True
        mock_popen.assert_called_once_with(
            ["/bin/echo", "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_screenshot_delegates(self):
        vd = virtual_desktop.VirtualDesktop("TestVD")
        mock_img = MagicMock()
        with patch("pyautogui.screenshot", return_value=mock_img):
            result = vd.screenshot()
        assert result is mock_img

    def test_list_windows_delegates(self):
        vd = virtual_desktop.VirtualDesktop("TestVD")
        expected = [{"title": "win1"}]
        with patch("core.window_manager.list_windows", return_value=expected):
            result = vd.list_windows()
        assert result == expected

    def test_context_manager_delegates(self):
        vd = virtual_desktop.VirtualDesktop("TestVD")
        with vd as v:
            assert v is vd

    def test_repr(self):
        vd = virtual_desktop.VirtualDesktop("MyDesktop")
        r = repr(vd)
        assert "MyDesktop" in r
        assert "_StubVirtualDesktop" in r

    def test_default_name(self):
        vd = virtual_desktop.VirtualDesktop()
        assert vd._name == "SentinelDesktop"

    def test_init_uses_stub_on_linux(self):
        """On Linux, impl is always _StubVirtualDesktop."""
        vd = virtual_desktop.VirtualDesktop("TestVD")
        assert isinstance(vd._impl, virtual_desktop._StubVirtualDesktop)


# ---------------------------------------------------------------------------
# _get_user32 / _get_kernel32 — non-Windows paths
# ---------------------------------------------------------------------------

class TestLazyCtypes:
    """Lazy ctypes handles — on Linux, windll doesn't exist."""

    def test_get_user32_raises_on_linux(self):
        """_get_user32 tries ctypes.windll.user32 which fails on Linux."""
        # Reset the global so it re-evaluates
        virtual_desktop._user32 = None
        try:
            with pytest.raises(AttributeError):
                virtual_desktop._get_user32()
        finally:
            virtual_desktop._user32 = None

    def test_get_kernel32_raises_on_linux(self):
        """_get_kernel32 tries ctypes.windll.kernel32 which fails on Linux."""
        virtual_desktop._kernel32 = None
        try:
            with pytest.raises(AttributeError):
                virtual_desktop._get_kernel32()
        finally:
            virtual_desktop._kernel32 = None


# ---------------------------------------------------------------------------
# _get_current_desktop_name — non-Windows path
# ---------------------------------------------------------------------------

class TestGetCurrentDesktopName:
    """_get_current_desktop_name returns 'Default' on non-Windows."""

    def test_returns_default_on_linux(self):
        assert virtual_desktop._get_current_desktop_name() == "Default"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify desktop access right constants are defined."""

    def test_desktop_access_rights(self):
        assert virtual_desktop.DESKTOP_READOBJECTS == 0x0001
        assert virtual_desktop.DESKTOP_CREATEWINDOW == 0x0002
        assert virtual_desktop.DESKTOP_SWITCHDESKTOP == 0x0100

    def test_full_access_mask(self):
        assert virtual_desktop._DESKTOP_FULL_ACCESS == (
            0x0001 | 0x0002 | 0x0004 | 0x0008 |
            0x0010 | 0x0020 | 0x0040 | 0x0080 | 0x0100
        )

    def test_startup_constants(self):
        assert virtual_desktop.STARTF_USESHOWWINDOW == 1
        assert virtual_desktop.SW_SHOWNORMAL == 1
        assert virtual_desktop.UOI_NAME == 2
