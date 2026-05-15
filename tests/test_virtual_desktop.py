"""Tests for core/virtual_desktop.py — constants, stub, and factory."""

from unittest.mock import patch

from core.virtual_desktop import (
    _DESKTOP_FULL_ACCESS,
    DESKTOP_CREATEMENU,
    DESKTOP_CREATEWINDOW,
    DESKTOP_ENUMERATE,
    DESKTOP_HOOKCONTROL,
    DESKTOP_JOURNALPLAYBACK,
    DESKTOP_JOURNALRECORD,
    DESKTOP_READOBJECTS,
    DESKTOP_SWITCHDESKTOP,
    DESKTOP_WRITEOBJECTS,
    _StubVirtualDesktop,
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
        with patch("pyautogui.screenshot", side_effect=RuntimeError("no screen")):
            stub = _StubVirtualDesktop("TestDesktop")
            assert stub.screenshot() is None
