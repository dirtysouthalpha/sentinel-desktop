"""Gap tests for window_manager.py — win32 focus, rect, target, close paths."""

from unittest.mock import MagicMock, patch

from core.window_manager import (
    close_window,
    focus_window,
    get_focused_window_rect,
    get_target_window_rect,
    get_window_rect,
    restore_window_hwnd,
)


class TestFocusWindowWin32:
    """focus_window with HAS_WIN32=True."""

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    def test_focus_with_win32_success(self, mock_con, mock_gui):
        mock_con.SW_RESTORE = 9
        mock_fg = 999
        mock_gui.GetForegroundWindow.return_value = mock_fg

        def fake_enum(callback, _):
            hwnd = MagicMock()
            mock_gui.IsWindowVisible.return_value = True
            mock_gui.GetWindowText.return_value = "Chrome"
            mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
            mock_gui.GetForegroundWindow.return_value = hwnd
            callback(hwnd, None)

        mock_gui.EnumWindows.side_effect = fake_enum
        result = focus_window("Chrome")
        assert result is True
        mock_gui.SetForegroundWindow.assert_called_once()

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.list_windows", return_value=[])
    def test_focus_no_match_returns_false(self, mock_lw):
        result = focus_window("Nonexistent")
        assert result is False

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    def test_focus_win32_exception_returns_false(self, mock_con, mock_gui):
        mock_con.SW_RESTORE = 9

        def fake_enum(callback, _):
            hwnd = 123
            mock_gui.IsWindowVisible.return_value = True
            mock_gui.GetWindowText.return_value = "Chrome"
            mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
            callback(hwnd, None)

        mock_gui.EnumWindows.side_effect = fake_enum
        mock_gui.SetForegroundWindow.side_effect = RuntimeError("focus fail")
        result = focus_window("Chrome")
        assert result is False

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.list_windows", return_value=[{"title": "Chrome"}])
    def test_focus_no_hwnd_returns_false(self, mock_lw):
        result = focus_window("Chrome")
        assert result is False


class TestFocusWindowPgwExceptions:
    """focus_window pgw exception paths."""

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_activate_exception(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            w1 = MagicMock()
            w1.activate.side_effect = RuntimeError("fail")
            mock_pgw.getWindowsWithTitle.return_value = [w1]
            result = focus_window("Chrome")
        assert result is False


class TestGetFocusedWindowRectWin32:
    """get_focused_window_rect with win32."""

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    def test_win32_returns_rect(self, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_gui.GetWindowRect.return_value = (10, 20, 810, 620)
        result = get_focused_window_rect()
        assert result == (10, 20, 800, 600)

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    def test_win32_no_hwnd(self, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 0
        result = get_focused_window_rect()
        assert result is None

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    def test_win32_zero_size(self, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_gui.GetWindowRect.return_value = (10, 20, 10, 20)
        result = get_focused_window_rect()
        assert result is None

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    def test_win32_exception(self, mock_gui):
        mock_gui.GetForegroundWindow.side_effect = RuntimeError("fail")
        result = get_focused_window_rect()
        assert result is None

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_exception_returns_none(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            mock_pgw.getActiveWindow.side_effect = RuntimeError("fail")
            result = get_focused_window_rect()
        assert result is None


class TestGetTargetWindowRectWin32:
    """get_target_window_rect with win32 foreground paths."""

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.list_windows", return_value=[])
    def test_foreground_is_other_app(self, mock_lw, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_gui.GetWindowText.return_value = "Chrome"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        result = get_target_window_rect()
        assert result is not None
        assert result[4] == "Chrome"

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.list_windows", return_value=[])
    def test_foreground_is_self_window_skipped(self, mock_lw, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_gui.GetWindowText.return_value = "Sentinel Desktop"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        result = get_target_window_rect()
        assert result is None

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.list_windows", return_value=[])
    def test_foreground_zero_size_skipped(self, mock_lw, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_gui.GetWindowText.return_value = "Chrome"
        mock_gui.GetWindowRect.return_value = (0, 0, 0, 0)
        result = get_target_window_rect()
        assert result is None

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch(
        "core.window_manager.list_windows",
        return_value=[
            {"title": "Notepad", "x": 0, "y": 0, "width": 800, "height": 600, "is_focused": True},
        ],
    )
    def test_foreground_self_falls_back_to_candidate(self, mock_lw, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_gui.GetWindowText.return_value = "Sentinel Desktop"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        result = get_target_window_rect()
        assert result is not None
        assert result[4] == "Notepad"

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch(
        "core.window_manager.list_windows",
        return_value=[
            {"title": "Tiny", "x": 0, "y": 0, "width": 100, "height": 100, "is_focused": False},
        ],
    )
    def test_tiny_windows_filtered_out(self, mock_lw, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_gui.GetWindowText.return_value = "Sentinel Desktop"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        result = get_target_window_rect()
        assert result is None

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.list_windows", side_effect=RuntimeError("enum fail"))
    def test_list_windows_exception_handled(self, mock_lw, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_gui.GetWindowText.return_value = "Sentinel Desktop"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        result = get_target_window_rect()
        assert result is None

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.list_windows", return_value=[])
    def test_win32_exception_returns_none(self, mock_lw, mock_gui):
        mock_gui.GetForegroundWindow.side_effect = RuntimeError("COM fail")
        result = get_target_window_rect()
        assert result is None


class TestGetWindowRectEdgeCases:
    """get_window_rect edge cases."""

    @patch("core.window_manager.list_windows", side_effect=RuntimeError("fail"))
    def test_exception_returns_none(self, mock_lw):
        result = get_window_rect("Chrome")
        assert result is None

    @patch("core.window_manager.list_windows")
    def test_minimized_window_restored(self, mock_lw):
        mock_lw.side_effect = [
            [
                {
                    "title": "Chrome",
                    "x": -32000,
                    "y": -32000,
                    "width": 800,
                    "height": 600,
                    "hwnd": 123,
                }
            ],
            [{"title": "Chrome", "x": 100, "y": 100, "width": 800, "height": 600}],
        ]
        with patch("core.window_manager.restore_window_hwnd", return_value=True):
            result = get_window_rect("Chrome")
        assert result == (100, 100, 800, 600)


class TestRestoreWindowHwndExceptions:
    """restore_window_hwnd exception paths."""

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    def test_show_window_exception(self, mock_con, mock_gui):
        mock_con.SW_RESTORE = 9
        mock_gui.ShowWindow.side_effect = RuntimeError("COM fail")
        result = restore_window_hwnd(123)
        assert result is False


class TestCloseWindowWin32:
    """close_window with win32."""

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    def test_close_matching_window(self, mock_con, mock_gui):
        mock_con.WM_CLOSE = 0x0010

        def fake_enum(callback, _):
            hwnd = 123
            mock_gui.IsWindowVisible.return_value = True
            mock_gui.GetWindowText.return_value = "Chrome"
            callback(hwnd, None)

        mock_gui.EnumWindows.side_effect = fake_enum
        result = close_window("Chrome")
        assert result is True
        mock_gui.PostMessage.assert_called_once_with(123, 0x0010, 0, 0)

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    def test_close_no_visible_match(self, mock_con, mock_gui):
        mock_con.WM_CLOSE = 0x0010

        def fake_enum(callback, _):
            hwnd = 123
            mock_gui.IsWindowVisible.return_value = False
            callback(hwnd, None)

        mock_gui.EnumWindows.side_effect = fake_enum
        result = close_window("Nonexistent")
        assert result is False

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    def test_close_enum_exception(self, mock_con, mock_gui):
        mock_gui.EnumWindows.side_effect = RuntimeError("enum fail")
        result = close_window("Chrome")
        assert result is False

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_close_exception(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            mock_pgw.getWindowsWithTitle.side_effect = RuntimeError("fail")
            result = close_window("Chrome")
        assert result is False
