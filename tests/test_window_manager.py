"""Tests for core/window_manager.py — window listing, focusing, and management."""

from unittest.mock import MagicMock, patch

from core.window_manager import (
    _is_self_window,
    _looks_minimized,
    close_window,
    focus_window,
    get_focused_window_rect,
    get_target_window_rect,
    get_window_rect,
    list_windows,
    restore_window,
    restore_window_hwnd,
)


class TestLooksMinimized:
    def test_normal_rect_is_not_minimized(self):
        assert _looks_minimized((100, 100, 800, 600)) is False

    def test_negative_32000_is_minimized(self):
        assert _looks_minimized((-32000, -32000, 800, 600)) is True

    def test_x_below_threshold(self):
        assert _looks_minimized((-32001, 100, 800, 600)) is True

    def test_y_below_threshold(self):
        assert _looks_minimized((100, -32001, 800, 600)) is True

    def test_zero_width(self):
        assert _looks_minimized((100, 100, 0, 600)) is True

    def test_zero_height(self):
        assert _looks_minimized((100, 100, 800, 0)) is True

    def test_negative_width(self):
        assert _looks_minimized((100, 100, -1, 600)) is True

    def test_none_rect(self):
        assert _looks_minimized(None) is True

    def test_short_tuple(self):
        assert _looks_minimized((100, 100)) is True

    def test_empty_tuple(self):
        assert _looks_minimized(()) is True


class TestIsSelfWindow:
    def test_sentinel_desktop_title(self):
        assert _is_self_window("Sentinel Desktop") is True

    def test_sentinel_desktop_lower(self):
        assert _is_self_window("sentinel desktop - chat") is True

    def test_other_window(self):
        assert _is_self_window("Chrome") is False

    def test_empty_string(self):
        assert _is_self_window("") is False

    def test_none(self):
        assert _is_self_window(None) is False


class TestListWindows:
    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    def test_win32_enumerates(self, mock_con, mock_gui):
        mock_fg = MagicMock()
        mock_gui.GetForegroundWindow.return_value = mock_fg

        def fake_enum(callback, _):
            hwnd1 = MagicMock()
            mock_gui.IsWindowVisible.side_effect = [True, False, True]
            mock_gui.GetWindowText.side_effect = ["Chrome", "", "Notepad"]
            mock_gui.GetWindowRect.side_effect = [(0, 0, 800, 600), (100, 100, 500, 400)]
            mock_gui.IsWindowVisible(hwnd1)
            callback(hwnd1, None)
            mock_gui.IsWindowVisible.assert_called()

        mock_gui.EnumWindows.side_effect = fake_enum
        list_windows()  # just ensure no crash

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", False)
    def test_no_libraries_returns_empty(self):
        windows = list_windows()
        assert windows == []

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_lists_windows(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            w1 = MagicMock()
            w1.title = "Chrome"
            w1.left = 0
            w1.top = 0
            w1.width = 800
            w1.height = 600
            w1.isActive = True
            mock_pgw.getAllWindows.return_value = [w1]

            windows = list_windows()
            assert len(windows) == 1
            assert windows[0]["title"] == "Chrome"
            assert windows[0]["width"] == 800

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_skips_empty_titles(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            w1 = MagicMock()
            w1.title = ""
            mock_pgw.getAllWindows.return_value = [w1]

            windows = list_windows()
            assert len(windows) == 0

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_exception_returns_empty(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            mock_pgw.getAllWindows.side_effect = RuntimeError("fail")
            windows = list_windows()
            assert windows == []


class TestFocusWindow:
    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", False)
    def test_no_libraries_returns_false(self):
        assert focus_window("Chrome") is False

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_focus_success(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            w1 = MagicMock()
            mock_pgw.getWindowsWithTitle.return_value = [w1]
            assert focus_window("Chrome") is True
            w1.activate.assert_called_once()

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_no_match_returns_false(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = []
            assert focus_window("Nonexistent") is False


class TestGetFocusedWindowRect:
    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", False)
    def test_no_libraries_returns_none(self):
        assert get_focused_window_rect() is None

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_returns_rect(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            w = MagicMock()
            w.width = 800
            w.height = 600
            w.left = 100
            w.top = 50
            mock_pgw.getActiveWindow.return_value = w
            result = get_focused_window_rect()
            assert result == (100, 50, 800, 600)

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_no_active_window(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            mock_pgw.getActiveWindow.return_value = None
            assert get_focused_window_rect() is None


class TestGetTargetWindowRect:
    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", False)
    @patch("core.window_manager.list_windows", return_value=[])
    def test_no_libraries_no_candidates(self, mock_lw):
        assert get_target_window_rect() is None


class TestGetWindowRect:
    @patch("core.window_manager.list_windows")
    def test_finds_matching_window(self, mock_lw):
        mock_lw.return_value = [
            {"title": "Chrome", "x": 0, "y": 0, "width": 800, "height": 600},
        ]
        result = get_window_rect("Chrome")
        assert result == (0, 0, 800, 600)

    @patch("core.window_manager.list_windows")
    def test_partial_title_match(self, mock_lw):
        mock_lw.return_value = [
            {"title": "Google Chrome - Homepage", "x": 10, "y": 20, "width": 900, "height": 700},
        ]
        result = get_window_rect("chrome")
        assert result == (10, 20, 900, 700)

    @patch("core.window_manager.list_windows")
    def test_no_match_returns_none(self, mock_lw):
        mock_lw.return_value = [
            {"title": "Notepad", "x": 0, "y": 0, "width": 400, "height": 300},
        ]
        assert get_window_rect("Chrome") is None

    def test_empty_title_returns_none(self):
        assert get_window_rect("") is None


class TestRestoreWindowHwnd:
    @patch("core.window_manager.HAS_WIN32", False)
    def test_no_win32_returns_false(self):
        assert restore_window_hwnd(12345) is False

    @patch("core.window_manager.HAS_WIN32", True)
    def test_none_hwnd_returns_false(self):
        assert restore_window_hwnd(None) is False

    @patch("core.window_manager.HAS_WIN32", True)
    @patch("core.window_manager.win32gui")
    @patch("core.window_manager.win32con")
    def test_restore_success(self, mock_con, mock_gui):
        mock_con.SW_RESTORE = 9
        assert restore_window_hwnd(12345) is True
        mock_gui.ShowWindow.assert_called_once_with(12345, 9)


class TestRestoreWindow:
    @patch("core.window_manager.list_windows")
    def test_restores_matching_window(self, mock_lw):
        with patch("core.window_manager.restore_window_hwnd", return_value=True) as mock_restore:
            mock_lw.return_value = [
                {"title": "Chrome", "hwnd": 123},
            ]
            assert restore_window("Chrome") is True
            mock_restore.assert_called_once_with(123)

    @patch("core.window_manager.list_windows")
    def test_no_match_returns_false(self, mock_lw):
        mock_lw.return_value = []
        assert restore_window("Nonexistent") is False

    def test_empty_title_returns_false(self):
        assert restore_window("") is False


class TestCloseWindow:
    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", False)
    def test_no_libraries_returns_false(self):
        assert close_window("Chrome") is False

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_close_success(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            w1 = MagicMock()
            mock_pgw.getWindowsWithTitle.return_value = [w1]
            assert close_window("Chrome") is True
            w1.close.assert_called_once()

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", True)
    def test_pgw_no_match_returns_false(self):
        with patch("core.window_manager.pgw") as mock_pgw:
            mock_pgw.getWindowsWithTitle.return_value = []
            assert close_window("Nonexistent") is False
