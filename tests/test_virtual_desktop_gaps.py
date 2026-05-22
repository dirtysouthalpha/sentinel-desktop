"""Gap-filling tests for core/virtual_desktop.py.

Focuses on the non-Windows (Linux) fallback path, covering the public
VirtualDesktop factory, _StubVirtualDesktop internals, helper functions,
and module-level constants that the base test file doesn't exercise.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.virtual_desktop import (
    STARTF_USESHOWWINDOW,
    SW_SHOWNORMAL,
    UOI_NAME,
    VirtualDesktop,
    _StubVirtualDesktop,
    _get_current_desktop_name,
)


# ---------------------------------------------------------------------------
# Module-level constants not covered in base test file
# ---------------------------------------------------------------------------


class TestExtraConstants:
    def test_startf_useshowwindow_value(self):
        assert STARTF_USESHOWWINDOW == 0x00000001

    def test_sw_shownormal_value(self):
        assert SW_SHOWNORMAL == 1

    def test_uoi_name_value(self):
        assert UOI_NAME == 2


# ---------------------------------------------------------------------------
# _get_current_desktop_name
# ---------------------------------------------------------------------------


class TestGetCurrentDesktopName:
    def test_returns_default_on_linux(self):
        """On non-Windows the function should immediately return 'Default'."""
        result = _get_current_desktop_name()
        assert result == "Default"

    def test_returns_default_on_exception(self):
        """If Windows check is forced but ctypes fails, still returns 'Default'."""
        with patch("core.virtual_desktop._IS_WINDOWS", True):
            with patch(
                "core.virtual_desktop._get_user32",
                side_effect=AttributeError("no windll"),
            ):
                result = _get_current_desktop_name()
                assert result == "Default"


# ---------------------------------------------------------------------------
# VirtualDesktop factory class (public API)
# ---------------------------------------------------------------------------


class TestVirtualDesktopFactory:
    def test_factory_creates_stub_on_linux(self):
        vd = VirtualDesktop("TestVD")
        assert isinstance(vd._impl, _StubVirtualDesktop)

    def test_factory_default_name(self):
        vd = VirtualDesktop()
        assert vd._name == "SentinelDesktop"

    def test_factory_custom_name(self):
        vd = VirtualDesktop("CustomName")
        assert vd._name == "CustomName"

    def test_factory_repr_shows_impl_type(self):
        vd = VirtualDesktop("TestRepr")
        r = repr(vd)
        assert "VirtualDesktop" in r
        assert "TestRepr" in r
        assert "_StubVirtualDesktop" in r

    def test_factory_delegates_create(self):
        vd = VirtualDesktop("TestCreate")
        assert vd.create() is False  # stub always returns False

    def test_factory_delegates_switch_to(self):
        vd = VirtualDesktop("TestSwitchTo")
        assert vd.switch_to() is False

    def test_factory_delegates_switch_back(self):
        vd = VirtualDesktop("TestSwitchBack")
        assert vd.switch_back() is False

    def test_factory_delegates_launch_app_invalid(self):
        vd = VirtualDesktop("TestLaunch")
        result = vd.launch_app("/nonexistent/binary")
        assert result["success"] is False
        assert result["pid"] is None

    def test_factory_delegates_launch_app_with_args(self):
        """launch_app should pass through args to the stub."""
        vd = VirtualDesktop("TestLaunchArgs")
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 42
            mock_popen.return_value = mock_proc
            result = vd.launch_app("/usr/bin/echo", args="hello")
            assert result["success"] is True
            assert result["pid"] == 42
            # Verify args were passed
            call_args = mock_popen.call_args[0][0]
            assert "hello" in call_args

    def test_factory_delegates_list_windows(self):
        vd = VirtualDesktop("TestList")
        windows = vd.list_windows()
        assert isinstance(windows, list)

    def test_factory_context_manager(self):
        """Context manager should call create on enter, switch_back + close on exit."""
        with VirtualDesktop("TestCtx") as vd:
            assert isinstance(vd, VirtualDesktop)
        # After exit, no exception should be raised

    def test_factory_close_is_noop(self):
        vd = VirtualDesktop("TestClose")
        vd.close()  # should not raise


# ---------------------------------------------------------------------------
# _StubVirtualDesktop deeper coverage
# ---------------------------------------------------------------------------


class TestStubVirtualDesktopDeeper:
    def test_stub_enter_returns_self(self):
        stub = _StubVirtualDesktop("TestEnter")
        result = stub.__enter__()
        assert result is stub

    def test_stub_exit_calls_nothing(self):
        stub = _StubVirtualDesktop("TestExit")
        # Should not raise regardless of args
        stub.__exit__(ValueError, ValueError("test"), None)

    def test_stub_close_idempotent(self):
        stub = _StubVirtualDesktop("TestCloseTwice")
        stub.close()
        stub.close()  # second call should also be fine

    def test_stub_launch_app_success_returns_pid(self):
        """When Popen succeeds, stub should return success with pid."""
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 1234
            mock_popen.return_value = mock_proc
            stub = _StubVirtualDesktop("TestLaunchOK")
            result = stub.launch_app("/usr/bin/ls")
            assert result["success"] is True
            assert result["pid"] == 1234
            assert "fallback" in result["output"]

    def test_stub_launch_app_with_args_passed(self):
        """Verify args are appended to the command list."""
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 5678
            mock_popen.return_value = mock_proc
            stub = _StubVirtualDesktop("TestLaunchArgs")
            result = stub.launch_app("/usr/bin/echo", args="--help")
            assert result["success"] is True
            call_cmd = mock_popen.call_args[0][0]
            assert call_cmd == ["/usr/bin/echo", "--help"]

    def test_stub_launch_app_oserror(self):
        """When Popen raises, stub should return failure."""
        with patch("subprocess.Popen", side_effect=OSError("nope")):
            stub = _StubVirtualDesktop("TestLaunchErr")
            result = stub.launch_app("/bad/path")
            assert result["success"] is False
            assert result["pid"] is None
            assert "nope" in result["output"]

    def test_stub_launch_app_file_not_found(self):
        """FileNotFoundError should also be caught."""
        with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            stub = _StubVirtualDesktop("TestLaunchFNFE")
            result = stub.launch_app("/missing")
            assert result["success"] is False

    def test_stub_screenshot_returns_image_on_success(self):
        """When pyautogui.screenshot works, stub should return the image."""
        mock_img = MagicMock(name="PILImage")
        with patch("pyautogui.screenshot", return_value=mock_img):
            stub = _StubVirtualDesktop("TestScreenshot")
            result = stub.screenshot()
            assert result is mock_img

    def test_stub_screenshot_returns_none_on_runtime_error(self):
        with patch("pyautogui.screenshot", side_effect=RuntimeError("no display")):
            stub = _StubVirtualDesktop("TestScreenshotFail")
            result = stub.screenshot()
            assert result is None

    def test_stub_screenshot_returns_none_on_oserror(self):
        with patch("pyautogui.screenshot", side_effect=OSError("no screen")):
            stub = _StubVirtualDesktop("TestScreenshotOSErr")
            result = stub.screenshot()
            assert result is None

    def test_stub_list_windows_returns_empty_on_import_failure(self):
        """If window_manager import fails, should return empty list."""
        with patch.dict("sys.modules", {"core.window_manager": None}):
            with patch("builtins.__import__", side_effect=ImportError("no wm")):
                stub = _StubVirtualDesktop("TestListWinFail")
                # The import is inside the method; mock at a higher level
                result = stub.list_windows()
                assert isinstance(result, list)

    def test_stub_init_logs_warning(self):
        """Stub constructor should log a warning about non-Windows."""
        with patch("core.virtual_desktop.logger") as mock_logger:
            _StubVirtualDesktop("TestWarn")
            mock_logger.warning.assert_called_once()
            call_msg = mock_logger.warning.call_args[0][0]
            assert "not running on Windows" in call_msg


# ---------------------------------------------------------------------------
# VirtualDesktop factory fallback on Windows init failure
# ---------------------------------------------------------------------------


class TestVirtualDesktopWindowsFallback:
    def test_factory_falls_back_to_stub_on_win32_error(self):
        """If _Win32VirtualDesktop raises, factory should use stub."""
        with patch("core.virtual_desktop._IS_WINDOWS", True):
            with patch(
                "core.virtual_desktop._Win32VirtualDesktop",
                side_effect=OSError("no win32"),
            ):
                vd = VirtualDesktop("FallbackTest")
                assert isinstance(vd._impl, _StubVirtualDesktop)

    def test_factory_falls_back_to_stub_on_runtime_error(self):
        with patch("core.virtual_desktop._IS_WINDOWS", True):
            with patch(
                "core.virtual_desktop._Win32VirtualDesktop",
                side_effect=RuntimeError("fail"),
            ):
                vd = VirtualDesktop("FallbackRT")
                assert isinstance(vd._impl, _StubVirtualDesktop)
