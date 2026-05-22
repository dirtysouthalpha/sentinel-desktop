"""Tests for core/virtual_desktop.py — constants, stub, factory, and edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from core.virtual_desktop import (
    _DESKTOP_FULL_ACCESS,
    _IS_WINDOWS,
    _StubVirtualDesktop,
    _get_current_desktop_name,
    DESKTOP_CREATEMENU,
    DESKTOP_CREATEWINDOW,
    DESKTOP_ENUMERATE,
    DESKTOP_HOOKCONTROL,
    DESKTOP_JOURNALPLAYBACK,
    DESKTOP_JOURNALRECORD,
    DESKTOP_READOBJECTS,
    DESKTOP_SWITCHDESKTOP,
    DESKTOP_WRITEOBJECTS,
    VirtualDesktop,
)


class TestConstants:
    def test_desktop_access_rights(self):
        assert DESKTOP_READOBJECTS == 0x0001
        assert DESKTOP_CREATEWINDOW == 0x0002
        assert DESKTOP_CREATEMENU == 0x0004
        assert DESKTOP_HOOKCONTROL == 0x0008
        assert DESKTOP_JOURNALRECORD == 0x0010
        assert DESKTOP_JOURNALPLAYBACK == 0x0020
        assert DESKTOP_ENUMERATE == 0x0040
        assert DESKTOP_WRITEOBJECTS == 0x0080
        assert DESKTOP_SWITCHDESKTOP == 0x0100

    def test_full_access_mask_is_sum(self):
        expected = (
            DESKTOP_READOBJECTS
            | DESKTOP_CREATEWINDOW
            | DESKTOP_CREATEMENU
            | DESKTOP_HOOKCONTROL
            | DESKTOP_JOURNALRECORD
            | DESKTOP_JOURNALPLAYBACK
            | DESKTOP_ENUMERATE
            | DESKTOP_WRITEOBJECTS
            | DESKTOP_SWITCHDESKTOP
        )
        assert _DESKTOP_FULL_ACCESS == expected

    def test_full_access_mask_is_nonzero(self):
        assert _DESKTOP_FULL_ACCESS > 0

    def test_each_flag_is_power_of_two(self):
        """Each individual right should be a distinct power of two."""
        flags = [
            DESKTOP_READOBJECTS,
            DESKTOP_CREATEWINDOW,
            DESKTOP_CREATEMENU,
            DESKTOP_HOOKCONTROL,
            DESKTOP_JOURNALRECORD,
            DESKTOP_JOURNALPLAYBACK,
            DESKTOP_ENUMERATE,
            DESKTOP_WRITEOBJECTS,
            DESKTOP_SWITCHDESKTOP,
        ]
        for flag in flags:
            assert flag != 0 and (flag & (flag - 1)) == 0, f"{flag} is not a power of two"


class TestGetCurrentDesktopName:
    def test_returns_default_on_linux(self):
        """On non-Windows platforms, _get_current_desktop_name returns 'Default'."""
        if _IS_WINDOWS:
            pytest.skip("only runs on non-Windows")
        assert _get_current_desktop_name() == "Default"

    @patch("core.virtual_desktop._IS_WINDOWS", False)
    def test_returns_string(self):
        result = _get_current_desktop_name()
        assert isinstance(result, str)
        assert len(result) > 0


class TestStubVirtualDesktop:
    def test_create_returns_false(self):
        stub = _StubVirtualDesktop("TestDesktop")
        assert stub.create() is False

    def test_switch_to_returns_false(self):
        stub = _StubVirtualDesktop("TestDesktop")
        assert stub.switch_to() is False

    def test_switch_back_returns_false(self):
        stub = _StubVirtualDesktop("TestDesktop")
        assert stub.switch_back() is False

    def test_close_is_noop(self):
        stub = _StubVirtualDesktop("TestDesktop")
        stub.close()  # should not raise

    def test_context_manager(self):
        with _StubVirtualDesktop("TestDesktop") as stub:
            assert stub.create() is False

    def test_launch_app_invalid_path(self):
        stub = _StubVirtualDesktop("TestDesktop")
        result = stub.launch_app("/nonexistent/binary")
        assert result["success"] is False
        assert result["pid"] is None

    def test_list_windows_fallback(self):
        stub = _StubVirtualDesktop("TestDesktop")
        windows = stub.list_windows()
        assert isinstance(windows, list)

    def test_screenshot_returns_none_on_failure(self):
        try:
            import pyautogui  # noqa: F401
        except ImportError:
            pytest.skip("pyautogui not installed")
        with patch("pyautogui.screenshot", side_effect=RuntimeError("no screen")):
            stub = _StubVirtualDesktop("TestDesktop")
            assert stub.screenshot() is None

    def test_launch_app_valid_command(self):
        """Launching a real command should succeed and return a PID."""
        stub = _StubVirtualDesktop("TestDesktop")
        result = stub.launch_app("/bin/true")
        assert result["success"] is True
        assert isinstance(result["pid"], int)
        assert result["pid"] > 0
        assert "fallback" in result["output"]

    def test_launch_app_with_args(self):
        """launch_app should accept and pass through args."""
        stub = _StubVirtualDesktop("TestDesktop")
        result = stub.launch_app("/bin/echo", args="hello world")
        assert result["success"] is True
        assert isinstance(result["pid"], int)

    def test_launch_app_returns_output_with_path(self):
        """Output message should mention the launched path."""
        stub = _StubVirtualDesktop("TestDesktop")
        result = stub.launch_app("/bin/true")
        assert "/bin/true" in result["output"]

    def test_launch_app_subprocess_failure(self):
        """launch_app with a path that raises an OSError should return failure."""
        stub = _StubVirtualDesktop("TestDesktop")
        with patch("subprocess.Popen", side_effect=OSError("permission denied")):
            result = stub.launch_app("/bin/ls")
            assert result["success"] is False
            assert result["pid"] is None
            assert "permission denied" in result["output"]

    def test_exit_returns_none(self):
        """__exit__ should not raise and returns None."""
        stub = _StubVirtualDesktop("TestDesktop")
        result = stub.__exit__(None, None, None)
        assert result is None

    def test_exit_with_exception_info(self):
        """__exit__ should accept exception info without raising."""
        stub = _StubVirtualDesktop("TestDesktop")
        result = stub.__exit__(ValueError, ValueError("test"), None)
        assert result is None

    def test_list_windows_import_error(self):
        """list_windows should return empty list when window_manager can't be imported."""
        stub = _StubVirtualDesktop("TestDesktop")
        with patch.dict("sys.modules", {"core.window_manager": None}):
            windows = stub.list_windows()
            assert isinstance(windows, list)

    def test_screenshot_returns_none_on_runtime_error(self):
        """screenshot returns None when pyautogui raises RuntimeError."""
        stub = _StubVirtualDesktop("TestDesktop")
        with patch("pyautogui.screenshot", side_effect=RuntimeError("no display")):
            result = stub.screenshot()
            assert result is None


class TestVirtualDesktopFactory:
    """Tests for the public VirtualDesktop factory class."""

    def test_default_name_is_sentinel(self):
        vd = VirtualDesktop()
        assert vd._name == "SentinelDesktop"

    def test_custom_name(self):
        vd = VirtualDesktop("CustomName")
        assert vd._name == "CustomName"

    def test_repr(self):
        vd = VirtualDesktop("TestVD")
        r = repr(vd)
        assert "TestVD" in r
        assert "VirtualDesktop" in r
        # On Linux, impl should be _StubVirtualDesktop
        if not _IS_WINDOWS:
            assert "_StubVirtualDesktop" in r

    def test_delegates_create(self):
        vd = VirtualDesktop("TestVD")
        # On non-Windows, create always returns False
        if not _IS_WINDOWS:
            assert vd.create() is False

    def test_delegates_switch_to(self):
        vd = VirtualDesktop("TestVD")
        if not _IS_WINDOWS:
            assert vd.switch_to() is False

    def test_delegates_switch_back(self):
        vd = VirtualDesktop("TestVD")
        if not _IS_WINDOWS:
            assert vd.switch_back() is False

    def test_delegates_close(self):
        vd = VirtualDesktop("TestVD")
        vd.close()  # should not raise

    def test_context_manager_protocol(self):
        with VirtualDesktop("CtxTest") as vd:
            assert vd is not None
            assert vd._name == "CtxTest"

    def test_launch_app_delegates(self):
        vd = VirtualDesktop("TestVD")
        result = vd.launch_app("/bin/true")
        assert result["success"] is True
        assert isinstance(result["pid"], int)

    def test_list_windows_delegates(self):
        vd = VirtualDesktop("TestVD")
        windows = vd.list_windows()
        assert isinstance(windows, list)

    def test_falls_back_to_stub_on_init_error(self):
        """If _Win32VirtualDesktop raises, should fall back to stub."""
        with patch("core.virtual_desktop._IS_WINDOWS", True):
            with patch(
                "core.virtual_desktop._Win32VirtualDesktop",
                side_effect=OSError("nope"),
            ):
                vd = VirtualDesktop("FailTest")
                assert isinstance(vd._impl, _StubVirtualDesktop)

    def test_screenshot_delegates(self):
        """screenshot on VirtualDesktop delegates to impl."""
        vd = VirtualDesktop("TestVD")
        mock_impl = MagicMock()
        mock_impl.screenshot.return_value = None
        vd._impl = mock_impl
        result = vd.screenshot()
        mock_impl.screenshot.assert_called_once()
        assert result is None

    def test_launch_app_with_args_delegates(self):
        """launch_app with args should forward correctly."""
        vd = VirtualDesktop("TestVD")
        mock_impl = MagicMock()
        mock_impl.launch_app.return_value = {"success": True, "pid": 42, "output": "ok"}
        vd._impl = mock_impl
        result = vd.launch_app("/usr/bin/test", args="--flag")
        mock_impl.launch_app.assert_called_once_with("/usr/bin/test", "--flag")
        assert result["success"] is True
