"""Gap tests for window_manager.py — list_windows EnumWindows error, focus Alt-tap error, restore_window enum error, close_window found guard."""

import platform
from unittest.mock import MagicMock, patch

import pytest

from core.window_manager import (
    _Win32Error,
    close_window,
    focus_window,
    list_windows,
    restore_window,
)


class TestListWindowsEnumWindowsError:
    """list_windows EnumWindows exception path (line 59-60)."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="win32gui only available on Windows")
    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    def test_enum_windows_error_returns_empty(self, mock_gui):
        mock_gui.EnumWindows.side_effect = _Win32Error(0, "enum fail")
        result = list_windows()
        assert result == []


class TestFocusWindowAltTapError:
    """focus_window Alt-tap trick error path (lines 112-113)."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="win32gui/win32con only available on Windows")
    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    @patch("core.window_manager.list_windows")
    def test_alt_tap_error_continues_to_set_foreground(self, mock_lw, mock_con, mock_gui):
        mock_con.SW_RESTORE = 9
        hwnd = MagicMock()

        mock_lw.return_value = [
            {"title": "Chrome", "hwnd": hwnd},
        ]

        # Make ctypes.windll.user32.keybd_event raise OSError
        with patch("ctypes.windll") as mock_windll:
            mock_windll.user32.keybd_event.side_effect = OSError("alt tap fail")
            result = focus_window("Chrome")
        assert result is True
        mock_gui.SetForegroundWindow.assert_called_once_with(hwnd)


class TestRestoreWindowEnumError:
    """restore_window enumeration error (lines 287-288)."""

    @patch("core.window_manager.list_windows", side_effect=OSError("enum error"))
    def test_list_windows_oserror_returns_false(self, mock_lw):
        result = restore_window("Chrome")
        assert result is False

    @patch("core.window_manager.list_windows", side_effect=_Win32Error(0, "win32 error"))
    def test_list_windows_win32error_returns_false(self, mock_lw):
        result = restore_window("Chrome")
        assert result is False


class TestCloseWindowFoundGuard:
    """close_window early-return guard when already found (line 305)."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="win32gui/win32con only available on Windows")
    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    def test_skips_after_first_match(self, mock_con, mock_gui):
        mock_con.WM_CLOSE = 0x0010
        call_count = 0

        def fake_enum(callback, _):
            nonlocal call_count
            # First window matches
            hwnd1 = 100
            mock_gui.IsWindowVisible.return_value = True
            mock_gui.GetWindowText.return_value = "Chrome"
            callback(hwnd1, None)
            # Second window would match too but should be skipped
            hwnd2 = 200
            mock_gui.GetWindowText.return_value = "Chrome"
            callback(hwnd2, None)
            call_count = 2

        mock_gui.EnumWindows.side_effect = fake_enum
        result = close_window("Chrome")
        assert result is True
        # Only one PostMessage call despite two matching windows
        assert mock_gui.PostMessage.call_count == 1
