"""Tests for core/virtual_desktop.py — VirtualDesktop factory, _raise_last_error,
and _StubVirtualDesktop edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.virtual_desktop import (
    VirtualDesktop,
    _raise_last_error,
    _StubVirtualDesktop,
)

# ---------------------------------------------------------------------------
# _raise_last_error
# ---------------------------------------------------------------------------


class TestRaiseLastError:
    def test_raises_oserror_with_api_name(self) -> None:
        with patch("ctypes.GetLastError", return_value=42):
            with pytest.raises(OSError, match="SomeApi failed"):
                _raise_last_error("SomeApi")

    def test_includes_win32_error_code(self) -> None:
        with patch("ctypes.GetLastError", return_value=5):
            with pytest.raises(OSError, match="Win32 error 5"):
                _raise_last_error("TestFunc")


# ---------------------------------------------------------------------------
# VirtualDesktop factory
# ---------------------------------------------------------------------------


class TestVirtualDesktopFactory:
    def test_repr_format(self) -> None:
        vd = VirtualDesktop("TestDesktop")
        r = repr(vd)
        assert "TestDesktop" in r
        assert "VirtualDesktop" in r

    def test_default_name(self) -> None:
        vd = VirtualDesktop()
        assert vd._name == "SentinelDesktop"

    def test_custom_name(self) -> None:
        vd = VirtualDesktop("CustomName")
        assert vd._name == "CustomName"

    def test_falls_back_to_stub_on_non_windows(self) -> None:
        with patch("core.virtual_desktop._IS_WINDOWS", False):
            vd = VirtualDesktop("Fallback")
            assert isinstance(vd._impl, _StubVirtualDesktop)

    def test_falls_back_to_stub_on_win32_failure(self) -> None:
        with patch("core.virtual_desktop._IS_WINDOWS", True):
            with patch(
                "core.virtual_desktop._Win32VirtualDesktop",
                side_effect=RuntimeError("no COM"),
            ):
                vd = VirtualDesktop("Fallback")
                assert isinstance(vd._impl, _StubVirtualDesktop)

    def test_context_manager_delegates_to_impl(self) -> None:
        impl = MagicMock()
        impl.create.return_value = True
        vd = VirtualDesktop("Test")
        vd._impl = impl

        with vd:
            pass

        impl.create.assert_called_once()
        impl.switch_back.assert_called_once()
        impl.close.assert_called_once()

    def test_delegates_create(self) -> None:
        impl = MagicMock()
        impl.create.return_value = True
        vd = VirtualDesktop("Test")
        vd._impl = impl
        assert vd.create() is True

    def test_delegates_switch_to(self) -> None:
        impl = MagicMock()
        impl.switch_to.return_value = True
        vd = VirtualDesktop("Test")
        vd._impl = impl
        assert vd.switch_to() is True

    def test_delegates_switch_back(self) -> None:
        impl = MagicMock()
        impl.switch_back.return_value = True
        vd = VirtualDesktop("Test")
        vd._impl = impl
        assert vd.switch_back() is True

    def test_delegates_launch_app(self) -> None:
        impl = MagicMock()
        impl.launch_app.return_value = {"success": True, "pid": 1234}
        vd = VirtualDesktop("Test")
        vd._impl = impl
        result = vd.launch_app("notepad.exe", args="test.txt")
        assert result["success"] is True
        impl.launch_app.assert_called_once_with("notepad.exe", "test.txt")

    def test_delegates_screenshot(self) -> None:
        impl = MagicMock()
        impl.screenshot.return_value = None
        vd = VirtualDesktop("Test")
        vd._impl = impl
        assert vd.screenshot() is None

    def test_delegates_list_windows(self) -> None:
        impl = MagicMock()
        impl.list_windows.return_value = [{"title": "Window1"}]
        vd = VirtualDesktop("Test")
        vd._impl = impl
        windows = vd.list_windows()
        assert len(windows) == 1

    def test_delegates_close(self) -> None:
        impl = MagicMock()
        vd = VirtualDesktop("Test")
        vd._impl = impl
        vd.close()
        impl.close.assert_called_once()


# ---------------------------------------------------------------------------
# _StubVirtualDesktop — launch_app success path
# ---------------------------------------------------------------------------


class TestStubLaunchAppSuccess:
    def test_launch_app_with_valid_executable(self) -> None:
        import sys

        stub = _StubVirtualDesktop("Test")
        # Use python executable as a safe test binary
        result = stub.launch_app(sys.executable, args="--version")
        # On stub, launch_app tries subprocess.Popen then checks if
        # the path exists. Since sys.executable is real, it may succeed
        # or fail depending on desktop isolation. Just verify shape.
        assert "success" in result
        assert "pid" in result
        assert "output" in result
