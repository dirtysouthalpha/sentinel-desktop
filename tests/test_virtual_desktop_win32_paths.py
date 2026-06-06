"""Gap-coverage tests for core/virtual_desktop.py Win32-specific code paths.

Exercises lines 94, 104, 126-141, 225-226, 252, 280, 283, 286, 291-293,
302-303, 307-401, 433-434, 440, 446-448, 451, 475-547, 556, 581-583, 696-699
by mocking ctypes.win32 APIs so the tests run on any platform.
"""

from __future__ import annotations

import ctypes
import threading
from unittest.mock import MagicMock, patch

import pytest

import core.virtual_desktop as vd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_user32():
    """Return a MagicMock that behaves like ctypes.windll.user32."""
    m = MagicMock()
    m.GetThreadDesktop.return_value = 999
    m.SetThreadDesktop.return_value = True
    m.SwitchDesktop.return_value = True
    m.OpenDesktopW.return_value = 888
    m.CloseDesktop.return_value = True
    m.CreateDesktopW.return_value = 777
    m.IsWindowVisible.return_value = True
    m.GetWindowTextLengthW.return_value = 10
    m.GetWindowTextW.return_value = None
    m.GetWindowRect.return_value = None  # writes via byref
    m.GetForegroundWindow.return_value = 100
    m.GetWindowThreadProcessId.return_value = 1
    m.GetUserObjectInformationW.return_value = True
    return m


def _mock_kernel32():
    """Return a MagicMock that behaves like ctypes.windll.kernel32."""
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
    with (
        patch.object(vd, "_get_user32", return_value=u),
        patch.object(vd, "_get_kernel32", return_value=k),
        patch.object(vd, "_get_current_desktop_name", return_value="Default"),
    ):
        return vd._Win32VirtualDesktop(name)


def _mock_process_info(pid=5678, h_process=1000, h_thread=2000):
    """Create a mock PROCESS_INFORMATION-like object."""
    m = MagicMock()
    m.dwProcessId = pid
    m.hProcess = h_process
    m.hThread = h_thread
    return m


# ---------------------------------------------------------------------------
# _get_user32 / _get_kernel32 — caching behavior (lines 94, 104)
# ---------------------------------------------------------------------------


class TestLazyCtypesLoaders:
    """Test _get_user32() and _get_kernel32() caching."""

    def test_get_user32_caches_result(self):
        """Calling _get_user32() twice returns the same cached object."""
        vd._user32 = "cached_user32"
        result = vd._get_user32()
        assert result == "cached_user32"

    def test_get_kernel32_caches_result(self):
        """Calling _get_kernel32() twice returns the same cached object."""
        vd._kernel32 = "cached_kernel32"
        result = vd._get_kernel32()
        assert result == "cached_kernel32"

    def test_get_user32_loads_when_none(self):
        """_get_user32 loads ctypes.windll.user32 when cache is None."""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.user32 = "fresh_user32"
        vd._user32 = None
        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            result = vd._get_user32()
        assert result == "fresh_user32"
        assert vd._user32 == "fresh_user32"

    def test_get_kernel32_loads_when_none(self):
        """_get_kernel32 loads ctypes.windll.kernel32 when cache is None."""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32 = "fresh_kernel32"
        vd._kernel32 = None
        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            result = vd._get_kernel32()
        assert result == "fresh_kernel32"
        assert vd._kernel32 == "fresh_kernel32"


# ---------------------------------------------------------------------------
# _raise_last_error (lines 696-699)
# ---------------------------------------------------------------------------


class TestRaiseLastError:
    """Test _raise_last_error raises OSError with Win32 error code."""

    def test_raises_os_error(self):
        """_raise_last_error raises OSError with GetLastError value."""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.GetLastError.return_value = 42
        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            with pytest.raises(OSError, match=r"SomeAPI failed.*Win32 error 42"):
                vd._raise_last_error("SomeAPI")

    def test_raises_os_error_with_zero(self):
        """_raise_last_error works even when GetLastError returns 0."""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.GetLastError.return_value = 0
        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            with pytest.raises(OSError, match="Win32 error 0"):
                vd._raise_last_error("TestAPI")

    def test_raises_os_error_with_access_denied(self):
        """_raise_last_error includes the API name in the message."""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.GetLastError.return_value = 5
        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            with pytest.raises(OSError, match="CreateDesktopW"):
                vd._raise_last_error("CreateDesktopW")


# ---------------------------------------------------------------------------
# _get_current_desktop_name — Win32 path (lines 126-141)
# ---------------------------------------------------------------------------


class TestGetCurrentDesktopNameWin32:
    """Test _get_current_desktop_name() on the Win32 code path."""

    def test_win32_success_path(self):
        """Returns the desktop name from GetUserObjectInformationW."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()

        # Build a fake ctypes-compatible buffer
        mock_buf = MagicMock()
        mock_buf.value = "MyDesktop"

        # Build a fake wintypes module
        mock_wintypes = MagicMock()
        mock_wintypes.DWORD = MagicMock

        # Build a fake ctypes that has windll
        mock_ctypes = MagicMock()
        mock_ctypes.create_unicode_buffer.return_value = mock_buf
        mock_ctypes.sizeof.return_value = 512
        mock_ctypes.byref.return_value = MagicMock()
        mock_ctypes.windll.kernel32.GetCurrentThreadId.return_value = 42

        with (
            patch.object(vd, "_IS_WINDOWS", True),
            patch.object(vd, "_get_user32", return_value=user32),
            patch.dict(
                "sys.modules",
                {
                    "ctypes": mock_ctypes,
                    "ctypes.wintypes": mock_wintypes,
                },
            ),
        ):
            result = vd._get_current_desktop_name()
        assert result == "MyDesktop"

    def test_win32_no_thread_desktop_handle(self):
        """Returns 'Default' when GetThreadDesktop returns 0."""
        user32 = _mock_user32()
        user32.GetThreadDesktop.return_value = 0
        kernel32 = _mock_kernel32()

        with (
            patch.object(vd, "_IS_WINDOWS", True),
            patch.object(vd, "_get_user32", return_value=user32),
            patch.object(vd, "_get_kernel32", return_value=kernel32),
        ):
            result = vd._get_current_desktop_name()
        assert result == "Default"

    def test_win32_get_user_object_info_fails(self):
        """Returns 'Default' when GetUserObjectInformationW returns False."""
        user32 = _mock_user32()
        user32.GetUserObjectInformationW.return_value = False
        kernel32 = _mock_kernel32()

        mock_buf = MagicMock()
        mock_buf.value = ""

        mock_ctypes = MagicMock()
        mock_ctypes.create_unicode_buffer.return_value = mock_buf
        mock_ctypes.sizeof.return_value = 512
        mock_ctypes.byref.return_value = MagicMock()
        mock_ctypes.windll.kernel32.GetCurrentThreadId.return_value = 42

        mock_wintypes = MagicMock()

        with (
            patch.object(vd, "_IS_WINDOWS", True),
            patch.object(vd, "_get_user32", return_value=user32),
            patch.dict(
                "sys.modules",
                {
                    "ctypes": mock_ctypes,
                    "ctypes.wintypes": mock_wintypes,
                },
            ),
        ):
            result = vd._get_current_desktop_name()
        assert result == "Default"

    def test_win32_empty_name_returns_default(self):
        """Returns 'Default' when buffer value is empty string."""
        user32 = _mock_user32()
        user32.GetUserObjectInformationW.return_value = True
        kernel32 = _mock_kernel32()

        mock_buf = MagicMock()
        mock_buf.value = ""

        mock_ctypes = MagicMock()
        mock_ctypes.create_unicode_buffer.return_value = mock_buf
        mock_ctypes.sizeof.return_value = 512
        mock_ctypes.byref.return_value = MagicMock()
        mock_ctypes.windll.kernel32.GetCurrentThreadId.return_value = 42

        mock_wintypes = MagicMock()

        with (
            patch.object(vd, "_IS_WINDOWS", True),
            patch.object(vd, "_get_user32", return_value=user32),
            patch.dict(
                "sys.modules",
                {
                    "ctypes": mock_ctypes,
                    "ctypes.wintypes": mock_wintypes,
                },
            ),
        ):
            result = vd._get_current_desktop_name()
        assert result == "Default"

    def test_win32_oserror_fallback(self):
        """Returns 'Default' when ctypes raises OSError."""
        user32 = _mock_user32()
        user32.GetThreadDesktop.side_effect = OSError("nope")
        kernel32 = _mock_kernel32()

        with (
            patch.object(vd, "_IS_WINDOWS", True),
            patch.object(vd, "_get_user32", return_value=user32),
            patch.object(vd, "_get_kernel32", return_value=kernel32),
        ):
            result = vd._get_current_desktop_name()
        assert result == "Default"

    def test_win32_attribute_error_fallback(self):
        """Returns 'Default' when ctypes raises AttributeError."""
        user32 = _mock_user32()
        user32.GetThreadDesktop.side_effect = AttributeError("nope")
        kernel32 = _mock_kernel32()

        with (
            patch.object(vd, "_IS_WINDOWS", True),
            patch.object(vd, "_get_user32", return_value=user32),
            patch.object(vd, "_get_kernel32", return_value=kernel32),
        ):
            result = vd._get_current_desktop_name()
        assert result == "Default"


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.close — OSError path (lines 225-226)
# ---------------------------------------------------------------------------


class TestWin32CloseOSError:
    """Test close() handles OSError from CloseDesktop."""

    def test_close_handles_oserror(self):
        """close() logs but doesn't crash when CloseDesktop raises OSError."""
        user32 = _mock_user32()
        user32.CloseDesktop.side_effect = OSError("access denied")
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32):
            win_vd.close()  # should not raise
        assert win_vd._handle is None


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.switch_to — SwitchDesktop False path (line 252)
# ---------------------------------------------------------------------------


class TestWin32SwitchToSwitchDesktopFalse:
    """Test switch_to() when SwitchDesktop returns False (non-fatal)."""

    def test_switch_to_switchdesktop_false_non_fatal(self):
        """switch_to succeeds even when SwitchDesktop returns False."""
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = False  # non-fatal
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd.switch_to()
        assert result is True
        assert win_vd._is_active is True


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.switch_back — various paths (lines 280, 283, 286, 291-293)
# ---------------------------------------------------------------------------


class TestWin32SwitchBackPaths:
    """Test switch_back() failure paths."""

    def test_switch_back_open_desktop_fails(self):
        """switch_back returns False when OpenDesktopW returns 0."""
        user32 = _mock_user32()
        user32.OpenDesktopW.return_value = 0
        kernel32 = _mock_kernel32()
        kernel32.GetLastError.return_value = 5

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with (
            patch.object(vd, "_get_user32", return_value=user32),
            patch.object(vd, "_raise_last_error", side_effect=OSError("fail")),
        ):
            result = win_vd.switch_back()
        assert result is False

    def test_switch_back_set_thread_desktop_fails(self):
        """switch_back returns False when SetThreadDesktop returns 0."""
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = False
        kernel32 = _mock_kernel32()
        kernel32.GetLastError.return_value = 5

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with (
            patch.object(vd, "_get_user32", return_value=user32),
            patch.object(vd, "_raise_last_error", side_effect=OSError("fail")),
        ):
            result = win_vd.switch_back()
        assert result is False

    def test_switch_back_switchdesktop_false_non_fatal(self):
        """switch_back succeeds even when SwitchDesktop(default) returns False."""
        user32 = _mock_user32()
        user32.SwitchDesktop.return_value = False  # non-fatal
        user32.SetThreadDesktop.return_value = True

        win_vd = _make_win32_vd(user32=user32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd.switch_back()
        assert result is True
        assert win_vd._is_active is False

    def test_switch_back_oserror(self):
        """switch_back returns False on OSError."""
        user32 = _mock_user32()
        user32.OpenDesktopW.side_effect = OSError("nope")
        kernel32 = _mock_kernel32()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd.switch_back()
        assert result is False

    def test_switch_back_runtime_error(self):
        """switch_back returns False on RuntimeError."""
        user32 = _mock_user32()
        user32.OpenDesktopW.side_effect = RuntimeError("nope")
        kernel32 = _mock_kernel32()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd.switch_back()
        assert result is False


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.launch_app (lines 302-303, 307-401)
# ---------------------------------------------------------------------------


class TestWin32LaunchApp:
    """Test _Win32VirtualDesktop.launch_app() with mocked Win32 APIs.

    The internal _launch_app_locked creates ctypes.Structure subclasses,
    so we mock at a higher level by replacing the ctypes module inside
    the function body.
    """

    def test_launch_app_success(self):
        """launch_app creates a process and returns success dict."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        # We'll mock the internal _launch_app_locked to test launch_app
        # dispatching (lines 302-303), then test _launch_app_locked separately.
        expected = {
            "success": True,
            "pid": 5678,
            "output": "Launched 'C:\\Windows\\notepad.exe' on TestDesk desktop (pid=5678)",
        }

        with patch.object(win_vd, "_launch_app_locked", return_value=expected) as mock_locked:
            result = win_vd.launch_app(r"C:\Windows\notepad.exe", "test.txt")

        assert result == expected
        mock_locked.assert_called_once_with(r"C:\Windows\notepad.exe", "test.txt")

    def test_launch_app_no_args(self):
        """launch_app passes None args to _launch_app_locked."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        expected = {"success": True, "pid": 1, "output": "ok"}

        with patch.object(win_vd, "_launch_app_locked", return_value=expected) as mock_locked:
            result = win_vd.launch_app(r"C:\app.exe")

        assert result == expected
        mock_locked.assert_called_once_with(r"C:\app.exe", None)

    def test_launch_app_locked_create_process_success(self):
        """_launch_app_locked returns success when CreateProcessW succeeds."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()

        # CreateProcessW needs to fill the PROCESS_INFORMATION struct.
        # We replace ctypes.byref so the mock receives the raw object
        # and can set its fields.
        def fake_create_process(*args):
            # args[9] is ctypes.byref(pi) — with our patched byref
            # it's the actual pi object
            pi_obj = args[9]
            pi_obj.dwProcessId = 5678
            pi_obj.hProcess = 1000
            pi_obj.hThread = 2000
            return 1

        kernel32.CreateProcessW.side_effect = fake_create_process

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with (
            patch.object(vd, "_get_kernel32", return_value=kernel32),
            patch("ctypes.byref", side_effect=lambda obj: obj),
        ):
            result = win_vd._launch_app_locked(r"C:\Windows\notepad.exe", "test.txt")

        assert result["success"] is True
        assert result["pid"] == 5678
        assert "notepad" in result["output"]

    def test_launch_app_locked_create_process_fails(self):
        """_launch_app_locked returns failure when CreateProcessW returns 0."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        kernel32.CreateProcessW.return_value = 0
        kernel32.GetLastError.return_value = 2

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_kernel32", return_value=kernel32):
            result = win_vd._launch_app_locked(r"C:\nonexistent.exe")

        assert result["success"] is False
        assert result["pid"] is None
        assert "CreateProcessW failed" in result["output"]
        assert "GetLastError=2" in result["output"]

    def test_launch_app_locked_no_handle(self):
        """_launch_app_locked uses None for lpDesktop when no handle."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()

        def fake_create_process(*args):
            pi_obj = args[9]
            pi_obj.dwProcessId = 9012
            pi_obj.hProcess = 3000
            pi_obj.hThread = 4000
            return 1

        kernel32.CreateProcessW.side_effect = fake_create_process

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = None

        with (
            patch.object(vd, "_get_kernel32", return_value=kernel32),
            patch("ctypes.byref", side_effect=lambda obj: obj),
        ):
            result = win_vd._launch_app_locked(r"C:\app.exe")

        assert result["success"] is True
        assert result["pid"] == 9012
        assert "current" in result["output"]

    def test_launch_app_locked_tracks_pid(self):
        """_launch_app_locked appends the pid to _launched_pids."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        kernel32.CreateProcessW.return_value = 1

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100
        assert win_vd._launched_pids == []

        with patch.object(vd, "_get_kernel32", return_value=kernel32):
            result = win_vd._launch_app_locked(r"C:\app.exe")

        assert result["success"] is True
        assert result["pid"] in win_vd._launched_pids

    def test_launch_app_locked_closes_handles(self):
        """_launch_app_locked closes process and thread handles after success."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        kernel32.CreateProcessW.return_value = 1

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with patch.object(vd, "_get_kernel32", return_value=kernel32):
            win_vd._launch_app_locked(r"C:\app.exe")

        # CloseHandle should be called for hProcess and hThread
        assert kernel32.CloseHandle.call_count >= 2

    def test_launch_app_locked_with_args(self):
        """_launch_app_locked includes args in the command line."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        kernel32.CreateProcessW.return_value = 1

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        with (
            patch.object(vd, "_get_kernel32", return_value=kernel32),
            patch("ctypes.create_unicode_buffer") as mock_buf_fn,
        ):
            mock_buf = MagicMock()
            mock_buf_fn.return_value = mock_buf

            result = win_vd._launch_app_locked(r"C:\app.exe", "--flag")

        assert result["success"] is True
        # Verify the command line included args
        buf_call_arg = mock_buf_fn.call_args[0][0]
        assert "--flag" in buf_call_arg


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.screenshot — switch paths (lines 433-451)
# ---------------------------------------------------------------------------


class TestWin32ScreenshotPaths:
    """Test screenshot() with various switching scenarios."""

    def test_screenshot_lock_timeout(self):
        """screenshot returns None when lock cannot be acquired."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100

        # Replace the lock with a mock whose acquire returns False immediately,
        # avoiding the real 5-second timeout wait.
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False
        win_vd._lock = mock_lock

        result = win_vd.screenshot()
        assert result is None

    def test_screenshot_switches_to_and_back(self):
        """screenshot switches to VD, captures, then switches back."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        mock_img = MagicMock()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100
        win_vd._is_active = False

        switch_to_called = False
        switch_back_called = False

        def fake_switch_to():
            nonlocal switch_to_called
            switch_to_called = True
            win_vd._is_active = True
            return True

        def fake_switch_back():
            nonlocal switch_back_called
            switch_back_called = True
            win_vd._is_active = False
            return True

        win_vd._switch_to_locked = fake_switch_to
        win_vd._switch_back_locked = fake_switch_back

        mock_pyautogui = MagicMock()
        mock_pyautogui.screenshot.return_value = mock_img

        with patch.dict("sys.modules", {"pyautogui": mock_pyautogui}):
            result = win_vd.screenshot()

        assert result is mock_img
        assert switch_to_called is True
        assert switch_back_called is True

    def test_screenshot_capture_failure_with_switch(self):
        """screenshot returns None when pyautogui fails, still switches back."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100
        win_vd._is_active = False

        switch_back_called = False

        def fake_switch_to():
            win_vd._is_active = True
            return True

        def fake_switch_back():
            nonlocal switch_back_called
            switch_back_called = True
            win_vd._is_active = False
            return True

        win_vd._switch_to_locked = fake_switch_to
        win_vd._switch_back_locked = fake_switch_back

        mock_pyautogui = MagicMock()
        mock_pyautogui.screenshot.side_effect = OSError("capture failed")

        with patch.dict("sys.modules", {"pyautogui": mock_pyautogui}):
            result = win_vd.screenshot()

        assert result is None
        assert switch_back_called is True

    def test_screenshot_no_switch_when_already_active(self):
        """screenshot doesn't switch when already on the virtual desktop."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        mock_img = MagicMock()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100
        win_vd._is_active = True

        switch_called = False

        def fake_switch():
            nonlocal switch_called
            switch_called = True
            return True

        win_vd._switch_to_locked = fake_switch

        mock_pyautogui = MagicMock()
        mock_pyautogui.screenshot.return_value = mock_img

        with patch.dict("sys.modules", {"pyautogui": mock_pyautogui}):
            result = win_vd.screenshot()

        assert result is mock_img
        assert switch_called is False

    def test_screenshot_no_handle_no_switch(self):
        """screenshot doesn't switch when _handle is None."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        mock_img = MagicMock()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = None
        win_vd._is_active = False

        switch_called = False

        def fake_switch():
            nonlocal switch_called
            switch_called = True
            return True

        win_vd._switch_to_locked = fake_switch

        mock_pyautogui = MagicMock()
        mock_pyautogui.screenshot.return_value = mock_img

        with patch.dict("sys.modules", {"pyautogui": mock_pyautogui}):
            result = win_vd.screenshot()

        assert result is mock_img
        assert switch_called is False

    def test_screenshot_runtime_error_capture(self):
        """screenshot returns None on RuntimeError from pyautogui."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()

        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = 100
        win_vd._is_active = True

        mock_pyautogui = MagicMock()
        mock_pyautogui.screenshot.side_effect = RuntimeError("oops")

        with patch.dict("sys.modules", {"pyautogui": mock_pyautogui}):
            result = win_vd.screenshot()

        assert result is None


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.list_windows — Win32 path (lines 475-547)
# ---------------------------------------------------------------------------


class TestWin32ListWindowsWin32:
    """Test list_windows() on the Win32 enumeration path."""

    def _make_vd_for_enum(self, handle=100, is_active=True):
        """Create a _Win32VirtualDesktop ready for EnumWindows testing."""
        user32 = _mock_user32()
        kernel32 = _mock_kernel32()
        win_vd = _make_win32_vd(user32=user32, kernel32=kernel32)
        win_vd._handle = handle
        win_vd._is_active = is_active
        return win_vd, user32

    def test_list_windows_no_handle_fallback(self):
        """list_windows falls back when _handle is None."""
        win_vd = vd._Win32VirtualDesktop.__new__(vd._Win32VirtualDesktop)
        win_vd._name = "TestDesk"
        win_vd._handle = None
        win_vd._lock = threading.Lock()
        win_vd._is_active = False
        win_vd._launched_pids = []

        with patch("core.window_manager.list_windows", return_value=[{"title": "Win1"}]):
            result = win_vd.list_windows()
        assert result == [{"title": "Win1"}]

    def test_list_windows_with_enum_collects_window(self):
        """list_windows enumerates and collects a visible window on our desktop."""
        win_vd, user32 = self._make_vd_for_enum()

        # Set up WINFUNCTYPE mock on ctypes module
        original_wintypes_ctypes = None

        def mock_enum_windows(callback_factory, lparam):
            # The callback is the result of WINFUNCTYPE(func)
            # which in our mock just returns the func itself
            callback = callback_factory
            # Simulate a window: visible, on our desktop, with a title
            callback(50, 0)
            return True

        user32.EnumWindows = mock_enum_windows
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 42
        user32.GetThreadDesktop.return_value = 100  # matches our handle
        user32.GetWindowTextLengthW.return_value = 7
        user32.GetForegroundWindow.return_value = 50

        mock_buf = MagicMock()
        mock_buf.value = "TestWin"

        # Save and restore ctypes.WINFUNCTYPE
        had_winfunctype = hasattr(ctypes, "WINFUNCTYPE")
        if had_winfunctype:
            original_wintypes_ctypes = ctypes.WINFUNCTYPE
        ctypes.WINFUNCTYPE = lambda *a, **kw: lambda cb: cb

        try:
            with (
                patch.object(vd, "_IS_WINDOWS", True),
                patch.object(vd, "_get_user32", return_value=user32),
                patch("ctypes.create_unicode_buffer", return_value=mock_buf),
                patch("ctypes.byref") as mock_byref,
            ):
                # Simulate RECT being filled by GetWindowRect
                def byref_side_effect(obj):
                    if hasattr(obj, "left"):
                        obj.left = 10
                        obj.top = 20
                        obj.right = 810
                        obj.bottom = 620
                    return MagicMock()

                mock_byref.side_effect = byref_side_effect

                result = win_vd.list_windows()
        finally:
            if had_winfunctype:
                ctypes.WINFUNCTYPE = original_wintypes_ctypes
            else:
                delattr(ctypes, "WINFUNCTYPE")

        assert len(result) == 1
        assert result[0]["title"] == "TestWin"
        assert result[0]["is_focused"] is True
        assert result[0]["x"] == 10

    def test_list_windows_skips_invisible(self):
        """list_windows skips windows that aren't visible."""
        win_vd, user32 = self._make_vd_for_enum()

        user32.EnumWindows = lambda cb, lp: cb(50, 0) or True
        user32.IsWindowVisible.return_value = False

        had_winfunctype = hasattr(ctypes, "WINFUNCTYPE")
        orig = getattr(ctypes, "WINFUNCTYPE", None)
        ctypes.WINFUNCTYPE = lambda *a, **kw: lambda cb: cb

        try:
            with (
                patch.object(vd, "_IS_WINDOWS", True),
                patch.object(vd, "_get_user32", return_value=user32),
            ):
                result = win_vd.list_windows()
        finally:
            if had_winfunctype:
                ctypes.WINFUNCTYPE = orig
            else:
                delattr(ctypes, "WINFUNCTYPE")

        assert result == []

    def test_list_windows_skips_wrong_desktop(self):
        """list_windows skips windows on a different desktop."""
        win_vd, user32 = self._make_vd_for_enum()

        user32.EnumWindows = lambda cb, lp: cb(50, 0) or True
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 42
        user32.GetThreadDesktop.return_value = 999  # different desktop

        had_winfunctype = hasattr(ctypes, "WINFUNCTYPE")
        orig = getattr(ctypes, "WINFUNCTYPE", None)
        ctypes.WINFUNCTYPE = lambda *a, **kw: lambda cb: cb

        try:
            with (
                patch.object(vd, "_IS_WINDOWS", True),
                patch.object(vd, "_get_user32", return_value=user32),
            ):
                result = win_vd.list_windows()
        finally:
            if had_winfunctype:
                ctypes.WINFUNCTYPE = orig
            else:
                delattr(ctypes, "WINFUNCTYPE")

        assert result == []

    def test_list_windows_skips_no_title(self):
        """list_windows skips windows with zero-length title."""
        win_vd, user32 = self._make_vd_for_enum()

        user32.EnumWindows = lambda cb, lp: cb(50, 0) or True
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 42
        user32.GetThreadDesktop.return_value = 100
        user32.GetWindowTextLengthW.return_value = 0

        had_winfunctype = hasattr(ctypes, "WINFUNCTYPE")
        orig = getattr(ctypes, "WINFUNCTYPE", None)
        ctypes.WINFUNCTYPE = lambda *a, **kw: lambda cb: cb

        try:
            with (
                patch.object(vd, "_IS_WINDOWS", True),
                patch.object(vd, "_get_user32", return_value=user32),
            ):
                result = win_vd.list_windows()
        finally:
            if had_winfunctype:
                ctypes.WINFUNCTYPE = orig
            else:
                delattr(ctypes, "WINFUNCTYPE")

        assert result == []

    def test_list_windows_skips_empty_title_text(self):
        """list_windows skips windows where GetWindowTextW returns empty."""
        win_vd, user32 = self._make_vd_for_enum()

        user32.EnumWindows = lambda cb, lp: cb(50, 0) or True
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 42
        user32.GetThreadDesktop.return_value = 100
        user32.GetWindowTextLengthW.return_value = 5

        mock_buf = MagicMock()
        mock_buf.value = ""

        had_winfunctype = hasattr(ctypes, "WINFUNCTYPE")
        orig = getattr(ctypes, "WINFUNCTYPE", None)
        ctypes.WINFUNCTYPE = lambda *a, **kw: lambda cb: cb

        try:
            with (
                patch.object(vd, "_IS_WINDOWS", True),
                patch.object(vd, "_get_user32", return_value=user32),
                patch("ctypes.create_unicode_buffer", return_value=mock_buf),
            ):
                result = win_vd.list_windows()
        finally:
            if had_winfunctype:
                ctypes.WINFUNCTYPE = orig
            else:
                delattr(ctypes, "WINFUNCTYPE")

        assert result == []

    def test_list_windows_skips_no_thread(self):
        """list_windows skips windows with no owning thread."""
        win_vd, user32 = self._make_vd_for_enum()

        user32.EnumWindows = lambda cb, lp: cb(50, 0) or True
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 0

        had_winfunctype = hasattr(ctypes, "WINFUNCTYPE")
        orig = getattr(ctypes, "WINFUNCTYPE", None)
        ctypes.WINFUNCTYPE = lambda *a, **kw: lambda cb: cb

        try:
            with (
                patch.object(vd, "_IS_WINDOWS", True),
                patch.object(vd, "_get_user32", return_value=user32),
            ):
                result = win_vd.list_windows()
        finally:
            if had_winfunctype:
                ctypes.WINFUNCTYPE = orig
            else:
                delattr(ctypes, "WINFUNCTYPE")

        assert result == []

    def test_list_windows_lock_timeout(self):
        """list_windows returns empty list when lock can't be acquired."""
        win_vd, user32 = self._make_vd_for_enum(is_active=False)

        # Replace the lock with a mock whose acquire returns False immediately,
        # avoiding the real 5-second timeout wait.
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False
        win_vd._lock = mock_lock

        with (
            patch.object(vd, "_IS_WINDOWS", True),
            patch.object(vd, "_get_user32", return_value=user32),
        ):
            result = win_vd.list_windows()

        assert result == []

    def test_list_windows_oserror(self):
        """list_windows returns empty list on OSError during enumeration."""
        win_vd, user32 = self._make_vd_for_enum()
        user32.EnumWindows.side_effect = OSError("nope")

        had_winfunctype = hasattr(ctypes, "WINFUNCTYPE")
        orig = getattr(ctypes, "WINFUNCTYPE", None)
        ctypes.WINFUNCTYPE = lambda *a, **kw: lambda cb: cb

        try:
            with (
                patch.object(vd, "_IS_WINDOWS", True),
                patch.object(vd, "_get_user32", return_value=user32),
            ):
                result = win_vd.list_windows()
        finally:
            if had_winfunctype:
                ctypes.WINFUNCTYPE = orig
            else:
                delattr(ctypes, "WINFUNCTYPE")

        assert result == []

    def test_list_windows_switches_and_back(self):
        """list_windows switches to VD if not active, then switches back."""
        win_vd, user32 = self._make_vd_for_enum(is_active=False)

        switch_back_called = False

        user32.EnumWindows = lambda cb, lp: True

        def fake_switch_to():
            win_vd._is_active = True
            return True

        def fake_switch_back():
            nonlocal switch_back_called
            switch_back_called = True
            win_vd._is_active = False
            return True

        win_vd._switch_to_locked = fake_switch_to
        win_vd._switch_back_locked = fake_switch_back

        had_winfunctype = hasattr(ctypes, "WINFUNCTYPE")
        orig = getattr(ctypes, "WINFUNCTYPE", None)
        ctypes.WINFUNCTYPE = lambda *a, **kw: lambda cb: cb

        try:
            with (
                patch.object(vd, "_IS_WINDOWS", True),
                patch.object(vd, "_get_user32", return_value=user32),
            ):
                result = win_vd.list_windows()
        finally:
            if had_winfunctype:
                ctypes.WINFUNCTYPE = orig
            else:
                delattr(ctypes, "WINFUNCTYPE")

        assert switch_back_called is True

    def test_list_windows_import_error_fallback(self):
        """list_windows falls back to window_manager when import fails."""
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
# _switch_to_locked / _switch_back_locked — remaining paths (lines 556, 581-583)
# ---------------------------------------------------------------------------


class TestLockedSwitchRemainingPaths:
    """Test remaining uncovered paths in _switch_to_locked and _switch_back_locked."""

    def test_switch_to_locked_set_thread_desktop_false(self):
        """_switch_to_locked returns False when SetThreadDesktop returns False."""
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = False

        win_vd = _make_win32_vd(user32=user32)
        win_vd._handle = 100
        win_vd._lock.acquire()

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd._switch_to_locked()
        assert result is False
        assert win_vd._is_active is False
        win_vd._lock.release()

    def test_switch_back_locked_oserror(self):
        """_switch_back_locked returns False on OSError."""
        user32 = _mock_user32()
        user32.OpenDesktopW.side_effect = OSError("fail")

        win_vd = _make_win32_vd(user32=user32)
        win_vd._handle = 100
        win_vd._lock.acquire()

        with patch.object(vd, "_get_user32", return_value=user32):
            result = win_vd._switch_back_locked()
        assert result is False
        win_vd._lock.release()


# ---------------------------------------------------------------------------
# _cleanup_launched_processes edge cases
# ---------------------------------------------------------------------------


class TestCleanupLaunchedProcesses:
    """Test _cleanup_launched_processes with various signal failures."""

    def test_cleanup_with_process_lookup_error(self):
        """_cleanup_launched_processes handles ProcessLookupError."""
        win_vd = _make_win32_vd()
        win_vd._launched_pids = [999999901]

        with patch("os.kill", side_effect=ProcessLookupError("no such process")):
            win_vd._cleanup_launched_processes()

        assert win_vd._launched_pids == []

    def test_cleanup_with_permission_error(self):
        """_cleanup_launched_processes handles PermissionError."""
        win_vd = _make_win32_vd()
        win_vd._launched_pids = [999999902]

        with patch("os.kill", side_effect=PermissionError("denied")):
            win_vd._cleanup_launched_processes()

        assert win_vd._launched_pids == []

    def test_cleanup_with_os_error(self):
        """_cleanup_launched_processes handles OSError."""
        win_vd = _make_win32_vd()
        win_vd._launched_pids = [999999903]

        with patch("os.kill", side_effect=OSError("fail")):
            win_vd._cleanup_launched_processes()

        assert win_vd._launched_pids == []

    def test_cleanup_multiple_pids(self):
        """_cleanup_launched_processes cleans up multiple PIDs."""
        win_vd = _make_win32_vd()
        win_vd._launched_pids = [999999904, 999999905, 999999906]

        win_vd._cleanup_launched_processes()
        assert win_vd._launched_pids == []
