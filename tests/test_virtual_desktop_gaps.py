"""Comprehensive gap-coverage tests for core/virtual_desktop.py.

Targets uncovered lines:
  117       – _get_current_desktop_name non-Windows early return
  128       – hdesk falsy fallback
  136       – GetUserObjectInformationW failure
  140-142    – exception handler in _get_current_desktop_name
  166-167    – __init__ snapshot default handle exception
  173-212    – _Win32VirtualDesktop.create() (all paths)
  216-226    – _Win32VirtualDesktop.close()
  238-255    – switch_to() with lock
  262-291    – switch_back() with lock
  300-301    – launch_app() lock wrapper
  305-399    – _launch_app_locked() (full CreateProcessW path)
  407-414    – _cleanup_launched_processes()
  429-451    – screenshot() with lock/switch/capture
  461-544    – list_windows() with enumeration
  550-559    – _switch_to_locked()
  563-580    – _switch_back_locked()
  585-586    – __enter__ on _Win32VirtualDesktop
  595-596    – __exit__ on _Win32VirtualDesktop
  663-665    – _StubVirtualDesktop.list_windows import failure
"""

from __future__ import annotations

import signal
import threading
from unittest.mock import MagicMock, patch

import pytest

from core.virtual_desktop import (
    VirtualDesktop,
    _get_current_desktop_name,
    _raise_last_error,
    _StubVirtualDesktop,
    _Win32VirtualDesktop,
)

# ---------------------------------------------------------------------------
# Helpers — build a _Win32VirtualDesktop without touching real Win32 APIs
# ---------------------------------------------------------------------------


def _make_win32_vd(name: str = "TestVD", **overrides) -> _Win32VirtualDesktop:
    """Construct a _Win32VirtualDesktop bypassing __init__ Win32 calls."""
    obj = object.__new__(_Win32VirtualDesktop)
    obj._name = name
    obj._handle = overrides.get("handle", 0xDEAD0001)
    obj._default_desktop_name = overrides.get("default_desktop_name", "Default")
    obj._default_handle = overrides.get("default_handle", 0xBEEF0002)
    obj._lock = threading.Lock()
    obj._is_active = overrides.get("is_active", False)
    obj._launched_pids = overrides.get("launched_pids", [])
    return obj


def _mock_user32(**methods):
    """Return a MagicMock user32 with sensible defaults."""
    u = MagicMock()
    for k, v in methods.items():
        setattr(u, k, v)
    return u


# ---------------------------------------------------------------------------
# _get_current_desktop_name (lines 117, 128, 136, 140-142)
# ---------------------------------------------------------------------------


class TestGetCurrentDesktopName:
    """Cover lines 117, 128, 136, 140-142."""

    def test_non_windows_returns_default(self) -> None:
        """Line 117 — early return 'Default' when not on Windows."""
        with patch("core.virtual_desktop._IS_WINDOWS", False):
            assert _get_current_desktop_name() == "Default"

    def test_hdesk_falsy_returns_default(self) -> None:
        """Line 128 — GetThreadDesktop returns 0 / falsy."""
        user32 = _mock_user32(GetThreadDesktop=MagicMock(return_value=0))
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=user32),
        ):
            assert _get_current_desktop_name() == "Default"

    def test_get_user_object_info_fails(self) -> None:
        """Line 136 — GetUserObjectInformationW returns False."""
        user32 = _mock_user32()
        user32.GetThreadDesktop.return_value = 0x100
        user32.GetUserObjectInformationW.return_value = False
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=user32),
        ):
            assert _get_current_desktop_name() == "Default"

    def test_exception_returns_default(self) -> None:
        """Lines 140-142 — OSError / AttributeError caught."""
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", side_effect=OSError("boom")),
        ):
            assert _get_current_desktop_name() == "Default"

    def test_attribute_error_returns_default(self) -> None:
        """Lines 140-142 — AttributeError caught."""
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", side_effect=AttributeError("no windll")),
        ):
            assert _get_current_desktop_name() == "Default"


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.__init__ (lines 166-167)
# ---------------------------------------------------------------------------


class TestWin32Init:
    """Cover lines 166-167 — snapshot default handle exception."""

    def test_init_snapshots_default_handle_exception(self) -> None:
        """If GetThreadDesktop raises during __init__, it logs and continues."""
        user32 = _mock_user32()
        user32.GetThreadDesktop.side_effect = OSError("nope")
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("core.virtual_desktop._get_kernel32"),
        ):
            obj = _Win32VirtualDesktop("TestVD")
            assert obj._default_handle is None
            assert obj._name == "TestVD"


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.create() (lines 173-212)
# ---------------------------------------------------------------------------


class TestWin32Create:
    """Cover lines 173-212."""

    def test_create_non_windows_returns_false(self) -> None:
        """Line 173-174."""
        obj = _make_win32_vd()
        with patch("core.virtual_desktop._IS_WINDOWS", False):
            assert obj.create() is False

    def test_create_opens_existing_desktop(self) -> None:
        """Lines 179-188 — OpenDesktopW succeeds with an existing handle."""
        user32 = _mock_user32()
        existing_handle = 0xAAA
        user32.OpenDesktopW.return_value = existing_handle
        obj = _make_win32_vd()
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=user32),
        ):
            assert obj.create() is True
            assert obj._handle == existing_handle

    def test_create_new_desktop_success(self) -> None:
        """Lines 191-204 — OpenDesktopW returns 0, CreateDesktopW succeeds."""
        user32 = _mock_user32()
        user32.OpenDesktopW.return_value = 0
        new_handle = 0xCCC
        user32.CreateDesktopW.return_value = new_handle
        obj = _make_win32_vd()
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=user32),
        ):
            assert obj.create() is True
            assert obj._handle == new_handle

    def test_create_new_desktop_handle_zero_falls_back(self) -> None:
        """Lines 199-212 — CreateDesktopW returns 0, _raise_last_error raises
        OSError which is caught by the except block, handle=None, returns False."""
        user32 = _mock_user32()
        user32.OpenDesktopW.return_value = 0
        user32.CreateDesktopW.return_value = 0
        obj = _make_win32_vd()
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("ctypes.GetLastError", return_value=99),
        ):
            assert obj.create() is False
            assert obj._handle is None

    def test_create_exception_sets_handle_none(self) -> None:
        """Lines 206-212 — exception caught, handle set to None, returns False."""
        user32 = _mock_user32()
        user32.OpenDesktopW.side_effect = OSError("fail")
        obj = _make_win32_vd()
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=user32),
        ):
            assert obj.create() is False
            assert obj._handle is None


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.close() (lines 216-226)
# ---------------------------------------------------------------------------


class TestWin32Close:
    """Cover lines 216-226."""

    def test_close_with_handle(self) -> None:
        """CloseDesktop called when handle is set."""
        user32 = _mock_user32()
        obj = _make_win32_vd(handle=0x100)
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            obj.close()
        assert obj._handle is None
        assert obj._is_active is False
        user32.CloseDesktop.assert_called_once_with(0x100)

    def test_close_without_handle(self) -> None:
        """CloseDesktop not called when handle is None."""
        obj = _make_win32_vd(handle=None)
        obj.close()
        assert obj._handle is None
        assert obj._is_active is False

    def test_close_handles_close_desktop_oserror(self) -> None:
        """Lines 223-224 — CloseDesktop raises OSError, still completes."""
        user32 = _mock_user32()
        user32.CloseDesktop.side_effect = OSError("boom")
        obj = _make_win32_vd(handle=0x200)
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            obj.close()
        assert obj._handle is None

    def test_close_terminates_launched_pids(self) -> None:
        """Lines 219, 407-414 — _cleanup_launched_processes called."""
        obj = _make_win32_vd(launched_pids=[99999])
        with patch("os.kill"):
            obj.close()
        # PID list should be cleared
        assert obj._launched_pids == []


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.switch_to() (lines 238-255)
# ---------------------------------------------------------------------------


class TestWin32SwitchTo:
    """Cover lines 238-255."""

    def test_switch_to_no_handle(self) -> None:
        """Lines 239-241 — no handle, returns False."""
        obj = _make_win32_vd(handle=None)
        assert obj.switch_to() is False

    def test_switch_to_success(self) -> None:
        """Lines 244-252 — SetThreadDesktop + SwitchDesktop succeed."""
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = True
        obj = _make_win32_vd(handle=0x100)
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj.switch_to() is True
        assert obj._is_active is True

    def test_switch_to_set_thread_desktop_fails_returns_false(self) -> None:
        """Lines 244-245 — SetThreadDesktop returns False → _raise_last_error
        raises OSError, caught by except block, returns False."""
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = False
        obj = _make_win32_vd(handle=0x100)
        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("ctypes.GetLastError", return_value=1),
        ):
            assert obj.switch_to() is False

    def test_switch_to_switch_desktop_false_nonfatal(self) -> None:
        """Lines 247-250 — SwitchDesktop returns False, still succeeds."""
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = False
        obj = _make_win32_vd(handle=0x100)
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj.switch_to() is True
        assert obj._is_active is True

    def test_switch_to_exception_returns_false(self) -> None:
        """Lines 253-255 — OSError caught, returns False."""
        user32 = _mock_user32()
        user32.SetThreadDesktop.side_effect = OSError("nope")
        obj = _make_win32_vd(handle=0x100)
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj.switch_to() is False


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.switch_back() (lines 262-291)
# ---------------------------------------------------------------------------


class TestWin32SwitchBack:
    """Cover lines 262-291."""

    def test_switch_back_no_default_info(self) -> None:
        """Lines 263-265 — no default handle and no default name."""
        obj = _make_win32_vd(default_handle=None, default_desktop_name="")
        assert obj.switch_back() is False

    def test_switch_back_success(self) -> None:
        """Lines 271-288 — full success path."""
        user32 = _mock_user32()
        default_handle = 0x500
        user32.OpenDesktopW.return_value = default_handle
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = True
        obj = _make_win32_vd()
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj.switch_back() is True
        assert obj._is_active is False
        user32.CloseDesktop.assert_called_once_with(default_handle)

    def test_switch_back_open_desktop_fails_returns_false(self) -> None:
        """Lines 277-278 — OpenDesktopW returns 0 → _raise_last_error raises
        OSError, caught by except block, returns False."""
        user32 = _mock_user32()
        user32.OpenDesktopW.return_value = 0
        obj = _make_win32_vd()
        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("ctypes.GetLastError", return_value=2),
        ):
            assert obj.switch_back() is False

    def test_switch_back_set_thread_desktop_fails_returns_false(self) -> None:
        """Lines 280-281 — SetThreadDesktop returns False → _raise_last_error
        raises OSError, caught by except block, returns False."""
        user32 = _mock_user32()
        user32.OpenDesktopW.return_value = 0x500
        user32.SetThreadDesktop.return_value = False
        obj = _make_win32_vd()
        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("ctypes.GetLastError", return_value=3),
        ):
            assert obj.switch_back() is False

    def test_switch_back_switch_desktop_false_nonfatal(self) -> None:
        """Lines 283-284 — SwitchDesktop(default) returns False, still succeeds."""
        user32 = _mock_user32()
        user32.OpenDesktopW.return_value = 0x500
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = False
        obj = _make_win32_vd()
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj.switch_back() is True
        assert obj._is_active is False

    def test_switch_back_exception_returns_false(self) -> None:
        """Lines 289-291 — OSError caught, returns False."""
        user32 = _mock_user32()
        user32.OpenDesktopW.side_effect = OSError("nope")
        obj = _make_win32_vd()
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj.switch_back() is False


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop.launch_app() and _launch_app_locked() (lines 300-399)
# ---------------------------------------------------------------------------


class TestWin32LaunchApp:
    """Cover lines 300-301 (lock wrapper) and 305-399 (_launch_app_locked).

    The _launch_app_locked method defines ctypes.Structure subclasses
    internally.  On Windows, real ctypes types (wintypes.DWORD, etc.) are
    available, so the structures instantiate correctly.  We mock only the
    kernel32.CreateProcessW call, and patch ctypes.byref so the mock can
    capture the PROCESS_INFORMATION struct and write a PID into it.
    """

    @staticmethod
    def _make_fake_kernel32(pid: int = 5555, h_proc: int = 0xAA, h_thread: int = 0xBB, ok: int = 1):
        """Build a mock kernel32 whose CreateProcessW writes pid into pi."""
        kernel32 = MagicMock()
        captured_pi = {}

        import ctypes

        def fake_byref(obj):
            """Replace ctypes.byref with pointer() so we can access .contents."""
            captured_pi["pi"] = obj
            return ctypes.pointer(obj)

        def fake_create_process(*args, **kwargs):
            pi = captured_pi.get("pi")
            if pi is not None:
                pi.dwProcessId = pid
                pi.hProcess = h_proc
                pi.hThread = h_thread
            return ok

        kernel32.CreateProcessW.side_effect = fake_create_process
        kernel32.GetLastError.return_value = 42
        return kernel32, fake_byref

    def test_launch_app_createprocess_success(self) -> None:
        """Lines 367-403 — CreateProcessW returns nonzero (success)."""
        kernel32, fake_byref = self._make_fake_kernel32(pid=5555)

        obj = _make_win32_vd(handle=0x100)
        with (
            patch("core.virtual_desktop._get_kernel32", return_value=kernel32),
            patch("ctypes.byref", side_effect=fake_byref),
        ):
            result = obj.launch_app(r"C:\test\app.exe", args="--flag")

        assert result["success"] is True
        assert result["pid"] == 5555
        kernel32.CloseHandle.assert_any_call(0xAA)
        kernel32.CloseHandle.assert_any_call(0xBB)
        assert 5555 in obj._launched_pids

    def test_launch_app_createprocess_failure(self) -> None:
        """Lines 380-384 — CreateProcessW returns 0 (failure)."""
        kernel32, fake_byref = self._make_fake_kernel32(ok=0)

        obj = _make_win32_vd(handle=0x100)
        with (
            patch("core.virtual_desktop._get_kernel32", return_value=kernel32),
            patch("ctypes.byref", side_effect=fake_byref),
        ):
            result = obj.launch_app(r"C:\nonexistent.exe")

        assert result["success"] is False
        assert result["pid"] is None
        assert "42" in result["output"]

    def test_launch_app_no_handle_sets_lpdesktop_none(self) -> None:
        """Line 351 — when handle is None, desktop_target is None."""
        kernel32, fake_byref = self._make_fake_kernel32(pid=7777)

        obj = _make_win32_vd(handle=None)
        with (
            patch("core.virtual_desktop._get_kernel32", return_value=kernel32),
            patch("ctypes.byref", side_effect=fake_byref),
        ):
            result = obj.launch_app(r"C:\app.exe")

        assert result["success"] is True
        assert "current" in result["output"]

    def test_launch_app_with_args(self) -> None:
        """Lines 309-311 — command line includes args when provided."""
        kernel32, fake_byref = self._make_fake_kernel32(pid=8888)

        obj = _make_win32_vd(handle=0x100)
        with (
            patch("core.virtual_desktop._get_kernel32", return_value=kernel32),
            patch("ctypes.byref", side_effect=fake_byref),
        ):
            result = obj.launch_app(r"C:\app.exe", args="--verbose")

        assert result["success"] is True
        assert 8888 in obj._launched_pids

    def test_launch_app_without_args(self) -> None:
        """Lines 309 — command line is just the path when args is None."""
        kernel32, fake_byref = self._make_fake_kernel32(pid=9999)

        obj = _make_win32_vd(handle=0x100)
        with (
            patch("core.virtual_desktop._get_kernel32", return_value=kernel32),
            patch("ctypes.byref", side_effect=fake_byref),
        ):
            result = obj.launch_app(r"C:\app.exe")

        assert result["success"] is True


# ---------------------------------------------------------------------------
# _cleanup_launched_processes (lines 407-414)
# ---------------------------------------------------------------------------


class TestCleanupLaunchedProcesses:
    """Cover lines 407-414."""

    def test_terminates_all_pids(self) -> None:
        """Normal termination of all PIDs."""
        obj = _make_win32_vd(launched_pids=[100, 200])
        with patch("os.kill") as mock_kill:
            obj._cleanup_launched_processes()
        assert mock_kill.call_count == 2
        mock_kill.assert_any_call(100, signal.SIGTERM)
        mock_kill.assert_any_call(200, signal.SIGTERM)
        assert obj._launched_pids == []

    def test_handles_process_lookup_error(self) -> None:
        """Line 412 — ProcessLookupError caught."""
        obj = _make_win32_vd(launched_pids=[111])
        with patch("os.kill", side_effect=ProcessLookupError("gone")):
            obj._cleanup_launched_processes()
        assert obj._launched_pids == []

    def test_handles_permission_error(self) -> None:
        """Line 412 — PermissionError caught."""
        obj = _make_win32_vd(launched_pids=[222])
        with patch("os.kill", side_effect=PermissionError("denied")):
            obj._cleanup_launched_processes()
        assert obj._launched_pids == []

    def test_handles_os_error(self) -> None:
        """Line 412 — OSError caught."""
        obj = _make_win32_vd(launched_pids=[333])
        with patch("os.kill", side_effect=OSError("err")):
            obj._cleanup_launched_processes()
        assert obj._launched_pids == []

    def test_empty_pids_list(self) -> None:
        """No PIDs — nothing happens."""
        obj = _make_win32_vd(launched_pids=[])
        obj._cleanup_launched_processes()
        assert obj._launched_pids == []


# ---------------------------------------------------------------------------
# _switch_to_locked / _switch_back_locked (lines 550-580)
# ---------------------------------------------------------------------------


class TestSwitchToLocked:
    """Cover lines 550-559."""

    def test_success(self) -> None:
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = True
        obj = _make_win32_vd(handle=0x100)
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj._switch_to_locked() is True
        assert obj._is_active is True

    def test_set_thread_desktop_false(self) -> None:
        """Lines 552-553 — SetThreadDesktop returns False."""
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = False
        obj = _make_win32_vd(handle=0x100)
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj._switch_to_locked() is False

    def test_oserror_returns_false(self) -> None:
        """Lines 557-559 — OSError caught, returns False."""
        user32 = _mock_user32()
        user32.SetThreadDesktop.side_effect = OSError("nope")
        obj = _make_win32_vd(handle=0x100)
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj._switch_to_locked() is False


class TestSwitchBackLocked:
    """Cover lines 563-580."""

    def test_success(self) -> None:
        user32 = _mock_user32()
        user32.OpenDesktopW.return_value = 0x500
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = True
        obj = _make_win32_vd()
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj._switch_back_locked() is True
        assert obj._is_active is False
        user32.CloseDesktop.assert_called_once_with(0x500)

    def test_open_desktop_falsy(self) -> None:
        """Lines 571-572 — OpenDesktopW returns 0."""
        user32 = _mock_user32()
        user32.OpenDesktopW.return_value = 0
        obj = _make_win32_vd()
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj._switch_back_locked() is False

    def test_oserror_returns_false(self) -> None:
        """Lines 578-580 — OSError caught, returns False."""
        user32 = _mock_user32()
        user32.OpenDesktopW.side_effect = OSError("nope")
        obj = _make_win32_vd()
        with patch("core.virtual_desktop._get_user32", return_value=user32):
            assert obj._switch_back_locked() is False


# ---------------------------------------------------------------------------
# screenshot() (lines 429-451)
# ---------------------------------------------------------------------------


class TestWin32Screenshot:
    """Cover lines 429-451."""

    def test_screenshot_cannot_acquire_lock(self) -> None:
        """Lines 429-432 — lock.acquire returns False."""
        obj = _make_win32_vd(handle=0x100)
        fake_lock = MagicMock()
        fake_lock.acquire.return_value = False
        fake_lock.release = MagicMock()
        obj._lock = fake_lock
        assert obj.screenshot() is None

    def test_screenshot_already_active(self) -> None:
        """Lines 434-435 — was_on_vd=True, no switch needed."""
        obj = _make_win32_vd(handle=0x100, is_active=True)
        fake_img = MagicMock()
        with patch("pyautogui.screenshot", return_value=fake_img):
            result = obj.screenshot()
        assert result is fake_img

    def test_screenshot_switch_and_capture(self) -> None:
        """Lines 437-443 — switch to VD, capture, switch back."""
        obj = _make_win32_vd(handle=0x100, is_active=False)
        fake_img = MagicMock()
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = True
        user32.OpenDesktopW.return_value = 0x500
        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("pyautogui.screenshot", return_value=fake_img),
        ):
            result = obj.screenshot()
        assert result is fake_img

    def test_screenshot_no_handle(self) -> None:
        """Lines 437 — handle is None, no switch, capture directly."""
        obj = _make_win32_vd(handle=None, is_active=False)
        fake_img = MagicMock()
        with patch("pyautogui.screenshot", return_value=fake_img):
            result = obj.screenshot()
        assert result is fake_img

    def test_screenshot_capture_failure(self) -> None:
        """Lines 444-446 — pyautogui.screenshot raises."""
        obj = _make_win32_vd(handle=0x100, is_active=True)
        with patch("pyautogui.screenshot", side_effect=OSError("no capture")):
            result = obj.screenshot()
        assert result is None

    def test_screenshot_switches_back_after_capture(self) -> None:
        """Lines 448-449 — switched=True triggers _switch_back_locked."""
        obj = _make_win32_vd(handle=0x100, is_active=False)
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = True
        user32.OpenDesktopW.return_value = 0x500
        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("pyautogui.screenshot", return_value=MagicMock()),
        ):
            obj.screenshot()
        # After screenshot, _is_active should be False (switched back)
        assert obj._is_active is False

    def test_screenshot_switches_back_on_capture_error(self) -> None:
        """Lines 448-449 in finally — switch_back even if capture fails."""
        obj = _make_win32_vd(handle=0x100, is_active=False)
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = True
        user32.OpenDesktopW.return_value = 0x500
        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("pyautogui.screenshot", side_effect=RuntimeError("fail")),
        ):
            obj.screenshot()
        # Should have switched back even after error
        assert obj._is_active is False


# ---------------------------------------------------------------------------
# list_windows() (lines 461-544)
# ---------------------------------------------------------------------------


class TestWin32ListWindows:
    """Cover lines 461-544."""

    def test_list_windows_not_windows_fallback(self) -> None:
        """Lines 463-471 — non-Windows or no handle, uses window_manager."""
        obj = _make_win32_vd(handle=None)
        mock_wm = MagicMock()
        mock_wm.list_windows.return_value = [{"title": "W1"}]
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=_mock_user32()),
        ):
            # handle is None
            with patch.dict("sys.modules", {"core.window_manager": mock_wm}):
                pass

            # Actually, let's use import patch
            pass

        # Simpler approach: mock the import directly
        obj = _make_win32_vd(handle=None)
        with patch("core.virtual_desktop._IS_WINDOWS", False):
            result = obj.list_windows()
        assert isinstance(result, list)

    def test_list_windows_no_handle_window_manager_fallback(self) -> None:
        """Lines 465-468 — fallback to window_manager when handle is None."""
        obj = _make_win32_vd(handle=None)
        mock_wm = MagicMock()
        mock_wm.list_windows.return_value = [{"title": "WM_Window"}]
        with patch("core.virtual_desktop._IS_WINDOWS", True), patch("core.window_manager", mock_wm):
            result = obj.list_windows()
        assert result == [{"title": "WM_Window"}]

    def test_list_windows_window_manager_import_error(self) -> None:
        """Lines 469-471 — window_manager.list_windows raises OSError, returns empty."""
        obj = _make_win32_vd(handle=None)
        mock_wm = MagicMock()
        mock_wm.list_windows.side_effect = OSError("fail")
        with patch("core.virtual_desktop._IS_WINDOWS", True), patch("core.window_manager", mock_wm):
            result = obj.list_windows()
        assert result == []

    def test_list_windows_lock_timeout(self) -> None:
        """Lines 481-482 — lock acquire returns False, returns empty."""
        obj = _make_win32_vd(handle=0x100)
        fake_lock = MagicMock()
        fake_lock.acquire.return_value = False
        obj._lock = fake_lock
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=_mock_user32()),
        ):
            result = obj.list_windows()
        assert result == []

    def test_list_windows_enumeration(self) -> None:
        """Lines 488-534 — full enumeration with callback."""
        obj = _make_win32_vd(handle=0x100, is_active=True)
        user32 = _mock_user32()

        # Simulate EnumWindows calling the callback with hwnd=0x999
        def fake_enum_windows(callback, lparam):
            callback(0x999, 0)
            return True

        user32.EnumWindows = fake_enum_windows
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 100
        user32.GetThreadDesktop.return_value = 0x100  # matches handle
        user32.GetWindowTextLengthW.return_value = 5
        user32.GetForegroundWindow.return_value = 0x999

        # Mock create_unicode_buffer to return a buffer with title "TestW"
        fake_buf = MagicMock()
        fake_buf.value = "TestW"

        # Capture the RECT objects created in the callback so we can
        # set their values after GetWindowRect is "called".
        captured_rects = []

        def fake_byref(obj):
            """Return the object itself instead of a byref wrapper."""
            captured_rects.append(obj)
            return obj

        def fake_get_window_rect(hwnd, rect_ref):
            rect_ref.left = 10
            rect_ref.top = 20
            rect_ref.right = 110
            rect_ref.bottom = 220
            return True

        user32.GetWindowRect = fake_get_window_rect

        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("ctypes.create_unicode_buffer", return_value=fake_buf),
            patch("ctypes.byref", side_effect=fake_byref),
            patch("ctypes.WINFUNCTYPE", side_effect=lambda *args: lambda f: f),
            patch("ctypes.sizeof", return_value=256),
        ):
            result = obj.list_windows()

        assert len(result) == 1
        assert result[0]["title"] == "TestW"
        assert result[0]["x"] == 10
        assert result[0]["y"] == 20
        assert result[0]["width"] == 100
        assert result[0]["height"] == 200
        assert result[0]["is_focused"] is True

    def test_list_windows_invisible_window_skipped(self) -> None:
        """Lines 493-494 — IsWindowVisible returns False, skip."""
        obj = _make_win32_vd(handle=0x100, is_active=True)
        user32 = _mock_user32()

        def fake_enum_windows(callback, lparam):
            callback(0x998, 0)
            return True

        user32.EnumWindows = fake_enum_windows
        user32.IsWindowVisible.return_value = False

        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("ctypes.WINFUNCTYPE", side_effect=lambda *args: lambda f: f),
        ):
            result = obj.list_windows()
        assert result == []

    def test_list_windows_tid_zero_skipped(self) -> None:
        """Lines 500-501 — GetWindowThreadProcessId returns 0."""
        obj = _make_win32_vd(handle=0x100, is_active=True)
        user32 = _mock_user32()

        def fake_enum_windows(callback, lparam):
            callback(0x997, 0)
            return True

        user32.EnumWindows = fake_enum_windows
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 0

        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("ctypes.WINFUNCTYPE", side_effect=lambda *args: lambda f: f),
        ):
            result = obj.list_windows()
        assert result == []

    def test_list_windows_different_desktop_skipped(self) -> None:
        """Lines 504-505 — hdesk != self._handle, skip."""
        obj = _make_win32_vd(handle=0x100, is_active=True)
        user32 = _mock_user32()

        def fake_enum_windows(callback, lparam):
            callback(0x996, 0)
            return True

        user32.EnumWindows = fake_enum_windows
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 100
        user32.GetThreadDesktop.return_value = 0x999  # different from handle

        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("ctypes.WINFUNCTYPE", side_effect=lambda *args: lambda f: f),
        ):
            result = obj.list_windows()
        assert result == []

    def test_list_windows_zero_title_length_skipped(self) -> None:
        """Lines 509-510 — GetWindowTextLengthW returns 0."""
        obj = _make_win32_vd(handle=0x100, is_active=True)
        user32 = _mock_user32()

        def fake_enum_windows(callback, lparam):
            callback(0x995, 0)
            return True

        user32.EnumWindows = fake_enum_windows
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 100
        user32.GetThreadDesktop.return_value = 0x100
        user32.GetWindowTextLengthW.return_value = 0

        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("ctypes.WINFUNCTYPE", side_effect=lambda *args: lambda f: f),
        ):
            result = obj.list_windows()
        assert result == []

    def test_list_windows_empty_title_skipped(self) -> None:
        """Lines 513-515 — title is empty string."""
        obj = _make_win32_vd(handle=0x100, is_active=True)
        user32 = _mock_user32()

        def fake_enum_windows(callback, lparam):
            callback(0x994, 0)
            return True

        user32.EnumWindows = fake_enum_windows
        user32.IsWindowVisible.return_value = True
        user32.GetWindowThreadProcessId.return_value = 100
        user32.GetThreadDesktop.return_value = 0x100
        user32.GetWindowTextLengthW.return_value = 5

        fake_buf = MagicMock()
        fake_buf.value = ""  # empty title

        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("ctypes.create_unicode_buffer", return_value=fake_buf),
            patch("ctypes.WINFUNCTYPE", side_effect=lambda *args: lambda f: f),
        ):
            result = obj.list_windows()
        assert result == []

    def test_list_windows_needs_switch_and_switches_back(self) -> None:
        """Lines 485-486, 536-537 — not active, switches to and back."""
        obj = _make_win32_vd(handle=0x100, is_active=False)
        user32 = _mock_user32()
        user32.SetThreadDesktop.return_value = True
        user32.SwitchDesktop.return_value = True
        user32.OpenDesktopW.return_value = 0x500
        user32.EnumWindows = lambda cb, lp: None  # no windows

        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("ctypes.WINFUNCTYPE", side_effect=lambda *args: lambda f: f),
        ):
            result = obj.list_windows()
        assert result == []
        # Should have switched back
        assert obj._is_active is False

    def test_list_windows_exception_returns_partial(self) -> None:
        """Lines 541-543 — exception during enumeration."""
        obj = _make_win32_vd(handle=0x100, is_active=True)
        user32 = _mock_user32()
        user32.EnumWindows.side_effect = OSError("fail")

        with (
            patch("core.virtual_desktop._get_user32", return_value=user32),
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("ctypes.WINFUNCTYPE", side_effect=lambda *args: lambda f: f),
        ):
            result = obj.list_windows()
        assert result == []


# ---------------------------------------------------------------------------
# _Win32VirtualDesktop context manager (lines 585-596)
# ---------------------------------------------------------------------------


class TestWin32ContextManager:
    """Cover lines 585-596."""

    def test_enter_calls_create(self) -> None:
        """Lines 585-586 — __enter__ calls create() and returns self."""
        obj = _make_win32_vd()
        with patch.object(obj, "create", return_value=True) as mock_create:
            result = obj.__enter__()
        assert result is obj
        mock_create.assert_called_once()

    def test_exit_calls_switch_back_and_close(self) -> None:
        """Lines 595-596 — __exit__ calls switch_back() and close()."""
        obj = _make_win32_vd()
        with (
            patch.object(obj, "switch_back", return_value=True) as mock_sb,
            patch.object(obj, "close") as mock_close,
        ):
            obj.__exit__(None, None, None)
        mock_sb.assert_called_once()
        mock_close.assert_called_once()

    def test_exit_with_exception_info(self) -> None:
        """Lines 588-596 — __exit__ still works with exception info."""
        obj = _make_win32_vd()
        exc_type = RuntimeError
        exc_val = RuntimeError("test")
        exc_tb = MagicMock()
        with patch.object(obj, "switch_back", return_value=True), patch.object(obj, "close"):
            obj.__exit__(exc_type, exc_val, exc_tb)


# ---------------------------------------------------------------------------
# _StubVirtualDesktop edge cases (lines 663-665)
# ---------------------------------------------------------------------------


class TestStubListWindowsFallback:
    """Cover lines 663-665 — list_windows fallback import failure."""

    def test_list_windows_import_error(self) -> None:
        """ImportError from window_manager returns empty list."""
        stub = _StubVirtualDesktop("Test")
        mock_wm = MagicMock()
        mock_wm.list_windows.side_effect = ImportError("nope")
        with patch("core.window_manager", mock_wm):
            result = stub.list_windows()
        assert result == []

    def test_list_windows_os_error(self) -> None:
        """OSError from window_manager returns empty list."""
        stub = _StubVirtualDesktop("Test")
        mock_wm = MagicMock()
        mock_wm.list_windows.side_effect = OSError("fail")
        with patch("core.window_manager", mock_wm):
            result = stub.list_windows()
        assert result == []

    def test_list_windows_success(self) -> None:
        """Successful window_manager delegation."""
        stub = _StubVirtualDesktop("Test")
        mock_wm = MagicMock()
        mock_wm.list_windows.return_value = [{"title": "A"}]
        with patch("core.window_manager", mock_wm):
            result = stub.list_windows()
        assert result == [{"title": "A"}]


# ---------------------------------------------------------------------------
# _StubVirtualDesktop.screenshot fallback
# ---------------------------------------------------------------------------


class TestStubScreenshot:
    """Cover _StubVirtualDesktop.screenshot fallback paths."""

    def test_screenshot_success(self) -> None:
        fake_img = MagicMock()
        with patch("pyautogui.screenshot", return_value=fake_img):
            stub = _StubVirtualDesktop("Test")
            result = stub.screenshot()
        assert result is fake_img

    def test_screenshot_runtime_error(self) -> None:
        with patch("pyautogui.screenshot", side_effect=RuntimeError("no")):
            stub = _StubVirtualDesktop("Test")
            assert stub.screenshot() is None


# ---------------------------------------------------------------------------
# _StubVirtualDesktop.launch_app edge cases
# ---------------------------------------------------------------------------


class TestStubLaunchApp:
    """Cover _StubVirtualDesktop.launch_app error paths."""

    def test_launch_app_with_args(self) -> None:
        """Lines 626-629 — launch with args appends to cmd."""
        import sys

        stub = _StubVirtualDesktop("Test")
        result = stub.launch_app(sys.executable, args="--version")
        assert "success" in result

    def test_launch_app_without_args(self) -> None:
        """Line 626-627 — launch without args."""
        import sys

        stub = _StubVirtualDesktop("Test")
        result = stub.launch_app(sys.executable)
        assert "success" in result

    def test_launch_app_oserror(self) -> None:
        """Lines 640-645 — OSError returns failure dict."""
        stub = _StubVirtualDesktop("Test")
        with patch("subprocess.Popen", side_effect=OSError("nope")):
            result = stub.launch_app("/bad/path")
        assert result["success"] is False
        assert result["pid"] is None
        assert "nope" in result["output"]

    def test_launch_app_file_not_found(self) -> None:
        """Lines 640-645 — FileNotFoundError returns failure dict."""
        stub = _StubVirtualDesktop("Test")
        with patch("subprocess.Popen", side_effect=FileNotFoundError("gone")):
            result = stub.launch_app("/missing")
        assert result["success"] is False
        assert result["pid"] is None

    def test_launch_app_subprocess_error(self) -> None:
        """Lines 640-645 — SubprocessError returns failure dict."""
        import subprocess

        stub = _StubVirtualDesktop("Test")
        with patch("subprocess.Popen", side_effect=subprocess.SubprocessError("err")):
            result = stub.launch_app("/bad")
        assert result["success"] is False
        assert result["pid"] is None


# ---------------------------------------------------------------------------
# _StubVirtualDesktop context manager
# ---------------------------------------------------------------------------


class TestStubContextManager:
    """Cover _StubVirtualDesktop __enter__ / __exit__."""

    def test_enter_returns_self(self) -> None:
        stub = _StubVirtualDesktop("Test")
        result = stub.__enter__()
        assert result is stub

    def test_exit_is_noop(self) -> None:
        stub = _StubVirtualDesktop("Test")
        # Should not raise
        stub.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# _raise_last_error edge cases
# ---------------------------------------------------------------------------


class TestRaiseLastErrorEdge:
    def test_raises_oserror(self) -> None:
        with patch("ctypes.GetLastError", return_value=123):
            with pytest.raises(OSError, match="Win32 error 123"):
                _raise_last_error("TestAPI")

    def test_error_message_format(self) -> None:
        with patch("ctypes.GetLastError", return_value=0):
            with pytest.raises(OSError, match="MyFunc failed"):
                _raise_last_error("MyFunc")


# ---------------------------------------------------------------------------
# _get_user32 / _get_kernel32 lazy initialization
# ---------------------------------------------------------------------------


class TestLazyCaches:
    """Cover lazy global caching for _user32 and _kernel32."""

    def test_get_user32_caches(self) -> None:
        """_get_user32 returns cached value on second call."""
        import core.virtual_desktop as mod

        old = mod._user32
        mod._user32 = None
        mock_windll = MagicMock()
        with patch.dict("sys.modules", {"ctypes": MagicMock(windll=MagicMock(user32=mock_windll))}):
            # First call sets the global
            result1 = mod._get_user32()
            assert result1 is mock_windll
            # Second call returns cached
            result2 = mod._get_user32()
            assert result2 is mock_windll
        mod._user32 = old

    def test_get_kernel32_caches(self) -> None:
        """_get_kernel32 returns cached value on second call."""
        import core.virtual_desktop as mod

        old = mod._kernel32
        mod._kernel32 = None
        mock_kernel = MagicMock()
        with patch.dict(
            "sys.modules", {"ctypes": MagicMock(windll=MagicMock(kernel32=mock_kernel))}
        ):
            result1 = mod._get_kernel32()
            assert result1 is mock_kernel
            result2 = mod._get_kernel32()
            assert result2 is mock_kernel
        mod._kernel32 = old


# ---------------------------------------------------------------------------
# VirtualDesktop factory — additional edge cases
# ---------------------------------------------------------------------------


class TestVirtualDesktopFactoryEdge:
    def test_repr_with_stub(self) -> None:
        """repr shows _StubVirtualDesktop when impl is stub."""
        with patch("core.virtual_desktop._IS_WINDOWS", False):
            vd = VirtualDesktop("TestRepr")
            r = repr(vd)
            assert "_StubVirtualDesktop" in r
            assert "TestRepr" in r

    def test_repr_with_win32(self) -> None:
        """repr shows _Win32VirtualDesktop when impl is win32."""
        with (
            patch("core.virtual_desktop._IS_WINDOWS", True),
            patch("core.virtual_desktop._get_user32", return_value=_mock_user32()),
        ):
            vd = VirtualDesktop("TestRepr")
            r = repr(vd)
            assert "_Win32VirtualDesktop" in r
            assert "TestRepr" in r
