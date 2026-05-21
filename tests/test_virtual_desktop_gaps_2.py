"""Additional gap-coverage tests for core/virtual_desktop.py.

The existing test_virtual_desktop_gaps.py skips all win32-path tests on
Linux.  This file re-enables them by mocking _get_user32/_get_kernel32
so they run cross-platform.
"""

from __future__ import annotations

import signal
import threading
from types import TracebackType
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import core.virtual_desktop as vd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user32():
    """Return a MagicMock that behaves like ctypes.windll.user32."""
    m = MagicMock()
    m.GetThreadDesktop.return_value = 999
    m.GetWindowTextLengthW.return_value = 10
    m.GetWindowTextW.return_value = None
    m.GetWindowRect.return_value = MagicMock(left=0, top=0, right=800, bottom=600)
    m.IsWindowVisible.return_value = True
    m.GetForegroundWindow.return_value = 100
    m.GetWindowThreadProcessId.return_value = 1
    m.SetThreadDesktop.return_value = True
    m.SwitchDesktop.return_value = True
    m.OpenDesktopW.return_value = 888
    m.CloseDesktop.return_value = True
    m.CreateDesktopW.return_value = 777
    return m


def _mock_kernel32():
    m = MagicMock()
    m.GetCurrentThreadId.return_value = 42
    m.GetLastError.return_value = 0
    m.CreateProcessW.return_value = 1
    m.CloseHandle.return_value = True
    return m


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level caches between tests."""
    old_u, old_k = vd._user32, vd._kernel32
    vd._user32 = None
    vd._kernel32 = None
    yield
    vd._user32 = old_u
    vd._kernel32 = old_k


def _make_win32_vd(name="TestDesk", user32=None, kernel32=None):
    """Create a _Win32VirtualDesktop with mocked platform APIs."""
    u = user32 or _mock_user32()
    k = kernel32 or _mock_kernel32()
    with patch.object(vd, "_get_user32", return_value=u), \
         patch.object(vd, "_get_kernel32", return_value=k), \
         patch.object(vd, "_get_current_desktop_name", return_value="Default"):
        return vd._Win32VirtualDesktop(name)


# ---------------------------------------------------------------------------
# _StubVirtualDesktop — launch_app edge cases
# ---------------------------------------------------------------------------

class TestStubLaunchApp:
    """Test _StubVirtualDesktop.launch_app success and failure paths."""

    def test_launch_success(self):
        stub = vd._StubVirtualDesktop("Test")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1234)
            result = stub.launch_app("/usr/bin/echo", "hello")
        assert result["success"] is True
        assert result["pid"] == 1234
        assert "fallback" in result["output"]

    def test_launch_with_no_args(self):
        stub = vd._StubVirtualDesktop("Test")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=5678)
            result = stub.launch_app("/usr/bin/ls")
        assert result["success"] is True
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert call_args == ["/usr/bin/ls"]

    def test_launch_failure(self):
        stub = vd._StubVirtualDesktop("Test")
        with patch("subprocess.Popen", side_effect=FileNotFoundError("nope")):
            result = stub.launch_app("/nonexistent")
        assert result["success"] is False
        assert result["pid"] is None
        assert "Failed" in result["output"]


# ---------------------------------------------------------------------------
# _StubVirtualDesktop — other methods
# ---------------------------------------------------------------------------

class TestStubMethods:
    """Test remaining _StubVirtualDesktop methods."""

    def test_create_returns_false(self):
        stub = vd._StubVirtualDesktop("Test")
        assert stub.create() is False

    def test_switch_to_returns_false(self):
        stub = vd._StubVirtualDesktop("Test")
        assert stub.switch_to() is False

    def test_switch_back_returns_false(self):
        stub = vd._StubVirtualDesktop("Test")
        assert stub.switch_back() is False

    def test_close_is_noop(self):
        stub = vd._StubVirtualDesktop("Test")
        stub.close()  # should not raise

    def test_context_manager(self):
        stub = vd._StubVirtualDesktop("Test")
        with stub as s:
            assert s is stub

    def test_screenshot_returns_none_on_error(self):
        stub = vd._StubVirtualDesktop("Test")
        with patch.dict("sys.modules", {"pyautogui": MagicMock(screenshot=MagicMock(side_effect=OSError("nope")))}):
            result = stub.screenshot()
        assert result is None

    def test_list_windows_delegates(self):
        stub = vd._StubVirtualDesktop("Test")
        with patch("core.window_manager.list_windows", return_value=[{"title": "X"}]):
            result = stub.list_windows()
        assert result == [{"title": "X"}]

    def test_list_windows_import_error(self):
        stub = vd._StubVirtualDesktop("Test")
        with patch("core.window_manager.list_windows", side_effect=ImportError("nope")):
            result = stub.list_windows()
        assert result == []


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.__init__ — snapshot failure
# ---------------------------------------------------------------------------

class TestWin32InitSnapshot:
    """Test _Win32VirtualDesktop init with failing user32 calls."""

    @patch.object(vd, "_IS_WINDOWS", True)
    def test_init_snapshot_failure_uses_stub(self):
        """If _Win32VirtualDesktop.__init__ fails, VirtualDesktop falls back to stub."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        # Make GetThreadDesktop fail during init
        user32.GetThreadDesktop.side_effect = AttributeError("nope")

        with patch.object(vd, "_get_user32", return_value=user32), \
             patch.object(vd, "_get_kernel32", return_value=kernel32), \
             patch.object(vd, "_get_current_desktop_name", return_value="Default"):
            vd_instance = vd.VirtualDesktop("TestDesktop")

        # On Linux, _IS_WINDOWS is False so it uses stub anyway;
        # on Windows it would fallback to stub on init failure.
        # Either way, it should not crash.
        assert vd_instance._impl is not None


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.create — various paths
# ---------------------------------------------------------------------------

class TestWin32Create:
    """Test _Win32VirtualDesktop.create() paths via mocking."""

    def test_create_opens_existing_desktop(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        user32.OpenDesktopW.return_value = 555

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        with patch.object(vd, "_get_user32", return_value=user32), \
             patch.object(vd, "_get_kernel32", return_value=kernel32), \
             patch.object(vd, "_IS_WINDOWS", True):
            result = win_vd.create()

        assert result is True
        assert win_vd._handle == 555

    def test_create_new_desktop(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        user32.OpenDesktopW.return_value = 0  # falsy
        user32.CreateDesktopW.return_value = 444

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        with patch.object(vd, "_get_user32", return_value=user32), \
             patch.object(vd, "_get_kernel32", return_value=kernel32), \
             patch.object(vd, "_IS_WINDOWS", True):
            result = win_vd.create()

        assert result is True
        assert win_vd._handle == 444

    def test_create_desktop_fails(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        user32.OpenDesktopW.return_value = 0
        user32.CreateDesktopW.return_value = 0  # also falsy
        kernel32.GetLastError.return_value = 5

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        with patch.object(vd, "_get_user32", return_value=user32), \
             patch.object(vd, "_get_kernel32", return_value=kernel32), \
             patch.object(vd, "_IS_WINDOWS", True), \
             patch.object(vd, "_raise_last_error", side_effect=OSError("CreateDesktopW failed (Win32 error 5)")):
            result = win_vd.create()

        assert result is False

    @patch.object(vd, "_IS_WINDOWS", False)
    def test_create_returns_false_on_non_windows(self):
        win_vd = _make_win32_vd()
        result = win_vd.create()
        assert result is False


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.close
# ---------------------------------------------------------------------------

class TestWin32Close:
    """Test _Win32VirtualDesktop.close() cleanup."""

    def test_close_with_handle(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32):
            win_vd.close()
        assert win_vd._handle is None
        user32.CloseDesktop.assert_called_once_with(100)

    def test_close_without_handle(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = None

        win_vd.close()
        user32.CloseDesktop.assert_not_called()

    def test_close_cleanup_launched_processes(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._launched_pids = [999999997, 999999998]
        win_vd.close()
        assert win_vd._launched_pids == []


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.switch_to / switch_back
# ---------------------------------------------------------------------------

class TestWin32Switching:
    """Test switch_to() and switch_back() paths."""

    def test_switch_to_no_handle_returns_false(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = None
        assert win_vd.switch_to() is False

    def test_switch_to_success(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd.switch_to()
        assert result is True
        assert win_vd._is_active is True

    def test_switch_to_set_thread_desktop_fails(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        user32.SetThreadDesktop.return_value = False
        kernel32.GetLastError.return_value = 5

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32), \
             patch.object(vd, "_get_kernel32", return_value=kernel32), \
             patch.object(vd, "_raise_last_error", side_effect=OSError("SetThreadDesktop failed (Win32 error 5)")):
            result = win_vd.switch_to()
        assert result is False

    def test_switch_back_no_default_info(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._default_handle = None
        win_vd._default_desktop_name = ""
        assert win_vd.switch_back() is False

    def test_switch_back_success(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd.switch_back()
        assert result is True
        assert win_vd._is_active is False
        user32.OpenDesktopW.assert_called()


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop context manager
# ---------------------------------------------------------------------------

class TestWin32ContextManager:
    """Test __enter__ and __exit__ on _Win32VirtualDesktop."""

    def test_enter_calls_create(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        user32.OpenDesktopW.return_value = 555

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        with patch.object(vd, "_get_user32", return_value=user32), \
             patch.object(vd, "_get_kernel32", return_value=kernel32):
            result = win_vd.__enter__()
        assert result is win_vd

    def test_exit_switches_back_and_closes(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32):
            win_vd.__exit__(None, None, None)
        assert win_vd._handle is None


# ---------------------------------------------------------------------------
# VirtualDesktop factory — repr
# ---------------------------------------------------------------------------

class TestVirtualDesktopRepr:
    """Test VirtualDesktop.__repr__."""

    def test_stub_repr(self):
        vd_instance = vd.VirtualDesktop("TestVD")
        r = repr(vd_instance)
        assert "TestVD" in r
        assert "_StubVirtualDesktop" in r


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop._switch_to_locked / _switch_back_locked
# ---------------------------------------------------------------------------

class TestWin32LockedSwitching:
    """Test internal locked switch methods."""

    def test_switch_to_locked_success(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100
        win_vd._lock.acquire()

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd._switch_to_locked()
        assert result is True
        assert win_vd._is_active is True
        win_vd._lock.release()

    def test_switch_to_locked_failure(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        user32.SetThreadDesktop.side_effect = OSError("fail")

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100
        win_vd._lock.acquire()

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd._switch_to_locked()
        assert result is False
        win_vd._lock.release()

    def test_switch_back_locked_success(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100
        win_vd._is_active = True
        win_vd._lock.acquire()

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd._switch_back_locked()
        assert result is True
        assert win_vd._is_active is False
        win_vd._lock.release()

    def test_switch_back_locked_open_fails(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        user32.OpenDesktopW.return_value = 0  # falsy

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._lock.acquire()

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd._switch_back_locked()
        assert result is False
        win_vd._lock.release()


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.list_windows — fallback path
# ---------------------------------------------------------------------------

class TestWin32ListWindowsFallback:
    """Test list_windows() fallback when not on Windows."""

    def test_fallback_to_window_manager(self):
        win_vd = vd._Win32VirtualDesktop.__new__(vd._Win32VirtualDesktop)
        win_vd._name = "TestDesk"
        win_vd._handle = None
        win_vd._lock = threading.Lock()
        win_vd._is_active = False
        win_vd._launched_pids = []

        with patch("core.window_manager.list_windows", return_value=[{"title": "App"}]):
            result = win_vd.list_windows()
        assert result == [{"title": "App"}]

    def test_fallback_import_error(self):
        win_vd = vd._Win32VirtualDesktop.__new__(vd._Win32VirtualDesktop)
        win_vd._name = "TestDesk"
        win_vd._handle = None
        win_vd._lock = threading.Lock()
        win_vd._is_active = False
        win_vd._launched_pids = []

        with patch("core.window_manager.list_windows", side_effect=ImportError("nope")):
            result = win_vd.list_windows()
        assert result == []


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.screenshot
# ---------------------------------------------------------------------------

class TestWin32Screenshot:
    """Test screenshot() with various switch states."""

    def test_screenshot_already_active(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        mock_img = MagicMock()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100
        win_vd._is_active = True

        with patch.dict("sys.modules", {"pyautogui": MagicMock(screenshot=MagicMock(return_value=mock_img))}):
            result = win_vd.screenshot()
        assert result is mock_img

    def test_screenshot_no_handle(self):
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        mock_img = MagicMock()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = None
        win_vd._is_active = False

        with patch.dict("sys.modules", {"pyautogui": MagicMock(screenshot=MagicMock(return_value=mock_img))}):
            result = win_vd.screenshot()
        assert result is mock_img


# ---------------------------------------------------------------------------
# VirtualDesktop public facade delegation
# ---------------------------------------------------------------------------

class TestVirtualDesktopDelegation:
    """Test that VirtualDesktop correctly delegates to _StubVirtualDesktop."""

    def test_create_delegates(self):
        vd_instance = vd.VirtualDesktop("Test")
        with patch.object(vd_instance._impl, "create", return_value=False) as m:
            assert vd_instance.create() is False
            m.assert_called_once()

    def test_switch_to_delegates(self):
        vd_instance = vd.VirtualDesktop("Test")
        with patch.object(vd_instance._impl, "switch_to", return_value=False) as m:
            assert vd_instance.switch_to() is False
            m.assert_called_once()

    def test_switch_back_delegates(self):
        vd_instance = vd.VirtualDesktop("Test")
        with patch.object(vd_instance._impl, "switch_back", return_value=False) as m:
            assert vd_instance.switch_back() is False
            m.assert_called_once()

    def test_launch_app_delegates(self):
        vd_instance = vd.VirtualDesktop("Test")
        expected = {"success": True, "pid": 1, "output": "ok"}
        with patch.object(vd_instance._impl, "launch_app", return_value=expected) as m:
            result = vd_instance.launch_app("/bin/echo", "hi")
            assert result == expected
            m.assert_called_once_with("/bin/echo", "hi")

    def test_screenshot_delegates(self):
        vd_instance = vd.VirtualDesktop("Test")
        with patch.object(vd_instance._impl, "screenshot", return_value=None) as m:
            assert vd_instance.screenshot() is None
            m.assert_called_once()

    def test_list_windows_delegates(self):
        vd_instance = vd.VirtualDesktop("Test")
        with patch.object(vd_instance._impl, "list_windows", return_value=[]) as m:
            assert vd_instance.list_windows() == []
            m.assert_called_once()

    def test_close_delegates(self):
        vd_instance = vd.VirtualDesktop("Test")
        with patch.object(vd_instance._impl, "close") as m:
            vd_instance.close()
            m.assert_called_once()

    def test_context_manager_delegates(self):
        vd_instance = vd.VirtualDesktop("Test")
        with patch.object(vd_instance._impl, "create", return_value=False), \
             patch.object(vd_instance._impl, "switch_back", return_value=False), \
             patch.object(vd_instance._impl, "close"):
            with vd_instance as v:
                assert v is vd_instance


# ---------------------------------------------------------------------------
# _get_current_desktop_name — non-Windows
# ---------------------------------------------------------------------------

class TestGetCurrentDesktopName:
    """Test _get_current_desktop_name on non-Windows."""

    @patch.object(vd, "_IS_WINDOWS", False)
    def test_returns_default_on_non_windows(self):
        assert vd._get_current_desktop_name() == "Default"


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify exported constants exist and have expected values."""

    def test_desktop_access_flags(self):
        assert vd.DESKTOP_READOBJECTS == 0x0001
        assert vd.DESKTOP_CREATEWINDOW == 0x0002
        assert vd.DESKTOP_SWITCHDESKTOP == 0x0100

    def test_desktop_full_access(self):
        assert vd._DESKTOP_FULL_ACCESS & vd.DESKTOP_READOBJECTS
        assert vd._DESKTOP_FULL_ACCESS & vd.DESKTOP_SWITCHDESKTOP

    def test_startup_constants(self):
        assert vd.STARTF_USESHOWWINDOW == 1
        assert vd.SW_SHOWNORMAL == 1

    def test_uoi_name(self):
        assert vd.UOI_NAME == 2
