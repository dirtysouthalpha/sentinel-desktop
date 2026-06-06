"""Gap tests for window_manager.py — exercise win32/pgw code paths via mocking.

On Linux the module-level HAS_WIN32/HAS_PGW flags are False, so most
function bodies are skipped.  We mock those flags (and the underlying
libraries) to reach the uncovered branches.
"""

from unittest.mock import MagicMock, patch

import core.window_manager as wm

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_win32gui():
    """Return a fresh MagicMock stand-in for win32gui."""
    m = MagicMock()
    m.GetForegroundWindow.return_value = 100
    m.GetWindowText.return_value = "Test Window"
    m.GetWindowRect.return_value = (10, 20, 810, 620)
    m.IsWindowVisible.return_value = True
    m.EnumWindows.side_effect = None  # caller sets per-test
    return m


def _mock_win32con():
    m = MagicMock()
    m.SW_RESTORE = 9
    m.WM_CLOSE = 0x0010
    return m


def _mock_pgw():
    """Return a fresh MagicMock stand-in for pygetwindow."""
    m = MagicMock()
    win = MagicMock()
    win.title = "PGW Window"
    win.left, win.top, win.width, win.height = 5, 10, 800, 600
    win.isActive = True
    m.getAllWindows.return_value = [win]
    m.getWindowsWithTitle.return_value = [win]
    m.getActiveWindow.return_value = win
    return m


# ---------------------------------------------------------------------------
# list_windows — win32 path
# ---------------------------------------------------------------------------

class TestListWindowsWin32:
    """Test list_windows when HAS_WIN32 is True."""

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_enum_visible_windows(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()

        def fake_enum(callback, extra):
            # Simulate two visible windows
            callback(101, None)
            callback(102, None)

        mock_gui.EnumWindows.side_effect = fake_enum
        mock_gui.IsWindowVisible.return_value = True
        mock_gui.GetWindowText.side_effect = ["Notepad", "Chrome"]
        mock_gui.GetWindowRect.side_effect = [(0, 0, 800, 600), (100, 100, 500, 400)]
        mock_gui.GetForegroundWindow.return_value = 101

        with patch.dict("sys.modules", {"win32gui": mock_gui, "win32con": mock_con}):
            with patch.object(wm, "win32gui", mock_gui, create=True), \
                 patch.object(wm, "win32con", mock_con, create=True):
                # Patch the module-level refs used inside list_windows
                wm.win32gui = mock_gui
                wm.win32con = mock_con
                result = wm.list_windows()
                wm.HAS_WIN32 = True

        assert len(result) == 2
        assert result[0]["title"] == "Notepad"
        assert result[0]["width"] == 800
        assert result[0]["height"] == 600
        assert result[0]["is_focused"] is True
        assert result[1]["is_focused"] is False

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_skips_empty_title(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()

        def fake_enum(callback, extra):
            callback(101, None)  # has title
            callback(102, None)  # empty title — should be skipped

        mock_gui.EnumWindows.side_effect = fake_enum
        mock_gui.IsWindowVisible.return_value = True
        mock_gui.GetWindowText.side_effect = ["Notepad", ""]
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        mock_gui.GetForegroundWindow.return_value = 101

        wm.win32gui = mock_gui
        wm.win32con = mock_con
        result = wm.list_windows()
        assert len(result) == 1

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_enum_error_returns_empty(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()
        mock_gui.EnumWindows.side_effect = OSError("enum fail")

        wm.win32gui = mock_gui
        wm.win32con = mock_con
        wm._Win32Error = OSError
        result = wm.list_windows()
        assert result == []

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_skips_invisible_windows(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()

        def fake_enum(callback, extra):
            callback(101, None)

        mock_gui.EnumWindows.side_effect = fake_enum
        mock_gui.IsWindowVisible.return_value = False

        wm.win32gui = mock_gui
        wm.win32con = mock_con
        result = wm.list_windows()
        assert result == []


# ---------------------------------------------------------------------------
# list_windows — pygetwindow path
# ---------------------------------------------------------------------------

class TestListWindowsPGW:
    """Test list_windows when HAS_PGW is True but HAS_WIN32 is False."""

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_lists_pgw_windows(self):
        mock_pgw = _mock_pgw()
        wm.pgw = mock_pgw
        result = wm.list_windows()
        assert len(result) == 1
        assert result[0]["title"] == "PGW Window"
        assert result[0]["is_focused"] is True

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_skips_empty_title_pgw(self):
        mock_pgw = _mock_pgw()
        win = MagicMock()
        win.title = ""
        mock_pgw.getAllWindows.return_value = [win]
        wm.pgw = mock_pgw
        result = wm.list_windows()
        assert result == []

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_error_returns_empty(self):
        mock_pgw = _mock_pgw()
        mock_pgw.getAllWindows.side_effect = OSError("pgw fail")
        wm.pgw = mock_pgw
        result = wm.list_windows()
        assert result == []


# ---------------------------------------------------------------------------
# focus_window — win32 path
# ---------------------------------------------------------------------------

class TestFocusWindowWin32:
    """Test focus_window when HAS_WIN32 is True."""

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_focus_finds_and_activates(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()

        with patch.object(wm, "list_windows", return_value=[
            {"title": "Notepad", "hwnd": 42, "x": 0, "y": 0, "width": 800, "height": 600, "is_focused": False},
        ]):
            wm.win32gui = mock_gui
            wm.win32con = mock_con
            wm._Win32Error = OSError
            # Explicit mock_user32 to prevent MagicMock auto-child recursion
            mock_user32 = MagicMock()
            mock_windll = MagicMock()
            mock_windll.user32 = mock_user32
            with patch("ctypes.windll", mock_windll, create=True):
                result = wm.focus_window("Notepad")
            assert result is True
            mock_gui.ShowWindow.assert_called_once_with(42, 9)  # SW_RESTORE=9
            mock_gui.SetForegroundWindow.assert_called_once_with(42)

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_focus_no_match_returns_false(self):
        with patch.object(wm, "list_windows", return_value=[
            {"title": "Chrome", "hwnd": 1},
        ]):
            wm.win32gui = _mock_win32gui()
            wm.win32con = _mock_win32con()
            wm._Win32Error = OSError
            result = wm.focus_window("Notepad")
            assert result is False

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_focus_no_hwnd_returns_false(self):
        with patch.object(wm, "list_windows", return_value=[
            {"title": "Notepad"},  # no hwnd key
        ]):
            wm.win32gui = _mock_win32gui()
            wm.win32con = _mock_win32con()
            result = wm.focus_window("Notepad")
            assert result is False

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_focus_win32error_returns_false(self):
        mock_gui = _mock_win32gui()
        mock_gui.ShowWindow.side_effect = OSError("fail")

        with patch.object(wm, "list_windows", return_value=[
            {"title": "Notepad", "hwnd": 42},
        ]):
            wm.win32gui = mock_gui
            wm.win32con = _mock_win32con()
            wm._Win32Error = OSError
            result = wm.focus_window("Notepad")
            assert result is False


# ---------------------------------------------------------------------------
# focus_window — pgw path
# ---------------------------------------------------------------------------

class TestFocusWindowPGW:
    """Test focus_window when HAS_PGW is True but HAS_WIN32 is False."""

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_focus_success(self):
        mock_pgw = _mock_pgw()
        wm.pgw = mock_pgw
        result = wm.focus_window("PGW Window")
        assert result is True
        mock_pgw.getWindowsWithTitle.return_value[0].activate.assert_called_once()

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_no_matching_windows(self):
        mock_pgw = _mock_pgw()
        mock_pgw.getWindowsWithTitle.return_value = []
        wm.pgw = mock_pgw
        result = wm.focus_window("Nonexistent")
        assert result is False

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_focus_error_returns_false(self):
        mock_pgw = _mock_pgw()
        mock_pgw.getWindowsWithTitle.side_effect = OSError("fail")
        wm.pgw = mock_pgw
        result = wm.focus_window("PGW Window")
        assert result is False


# ---------------------------------------------------------------------------
# get_focused_window_rect — win32 path
# ---------------------------------------------------------------------------

class TestGetFocusedWindowRectWin32:
    """Test get_focused_window_rect with HAS_WIN32=True."""

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_returns_rect_for_focused_window(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowRect.return_value = (10, 20, 810, 620)
        wm.win32gui = mock_gui
        wm._Win32Error = OSError
        result = wm.get_focused_window_rect()
        assert result == (10, 20, 800, 600)

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_returns_none_for_zero_hwnd(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.return_value = 0
        wm.win32gui = mock_gui
        result = wm.get_focused_window_rect()
        assert result is None

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_returns_none_for_zero_size(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetWindowRect.return_value = (10, 20, 10, 20)  # width=0
        wm.win32gui = mock_gui
        wm._Win32Error = OSError
        result = wm.get_focused_window_rect()
        assert result is None

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_returns_none_on_win32error(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.side_effect = OSError("fail")
        wm.win32gui = mock_gui
        wm._Win32Error = OSError
        result = wm.get_focused_window_rect()
        assert result is None


# ---------------------------------------------------------------------------
# get_focused_window_rect — pgw path
# ---------------------------------------------------------------------------

class TestGetFocusedWindowRectPGW:
    """Test get_focused_window_rect with HAS_PGW=True."""

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_returns_rect(self):
        mock_pgw = _mock_pgw()
        wm.pgw = mock_pgw
        result = wm.get_focused_window_rect()
        assert result == (5, 10, 800, 600)

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_none_active(self):
        mock_pgw = _mock_pgw()
        mock_pgw.getActiveWindow.return_value = None
        wm.pgw = mock_pgw
        result = wm.get_focused_window_rect()
        assert result is None

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_zero_size(self):
        mock_pgw = _mock_pgw()
        win = MagicMock()
        win.width, win.height = 0, 600
        mock_pgw.getActiveWindow.return_value = win
        wm.pgw = mock_pgw
        result = wm.get_focused_window_rect()
        assert result is None

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_error(self):
        mock_pgw = _mock_pgw()
        mock_pgw.getActiveWindow.side_effect = OSError("fail")
        wm.pgw = mock_pgw
        result = wm.get_focused_window_rect()
        assert result is None


# ---------------------------------------------------------------------------
# get_target_window_rect — win32 path
# ---------------------------------------------------------------------------

class TestGetTargetWindowRectWin32:
    """Test get_target_window_rect with HAS_WIN32=True."""

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_foreground_not_self_returns_rect(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowText.return_value = "Chrome"
        mock_gui.GetWindowRect.return_value = (10, 20, 810, 620)
        wm.win32gui = mock_gui
        wm._Win32Error = OSError
        result = wm.get_target_window_rect()
        assert result is not None
        assert result == (10, 20, 800, 600, "Chrome")

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_foreground_is_self_falls_back(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowText.return_value = "Sentinel Desktop"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        wm.win32gui = mock_gui
        wm._Win32Error = OSError

        with patch.object(wm, "list_windows", return_value=[
            {"title": "Chrome", "x": 10, "y": 20, "width": 800, "height": 600, "is_focused": False},
        ]):
            result = wm.get_target_window_rect()
        assert result is not None
        assert result[4] == "Chrome"

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_foreground_zero_size_skipped(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowText.return_value = "Chrome"
        mock_gui.GetWindowRect.return_value = (10, 20, 10, 20)  # w=0, h=0
        wm.win32gui = mock_gui
        wm._Win32Error = OSError

        with patch.object(wm, "list_windows", return_value=[]):
            result = wm.get_target_window_rect()
        assert result is None

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_error_in_enum_returns_none(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.side_effect = OSError("fail")
        wm.win32gui = mock_gui
        wm._Win32Error = OSError
        with patch.object(wm, "list_windows", return_value=[]):
            result = wm.get_target_window_rect()
        assert result is None

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_tiny_candidate_windows_skipped(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowText.return_value = "Sentinel Desktop"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        wm.win32gui = mock_gui
        wm._Win32Error = OSError

        # Candidate has width=100 (<= 200) so should be skipped
        with patch.object(wm, "list_windows", return_value=[
            {"title": "Tiny", "x": 0, "y": 0, "width": 100, "height": 600, "is_focused": False},
        ]):
            result = wm.get_target_window_rect()
        assert result is None


# ---------------------------------------------------------------------------
# get_window_rect — edge cases
# ---------------------------------------------------------------------------

class TestGetWindowRectEdgeCases:
    """Additional get_window_rect tests."""

    def test_empty_title_returns_none(self):
        result = wm.get_window_rect("")
        assert result is None

    @patch.object(wm, "list_windows", return_value=[])
    def test_no_matching_window_returns_none(self, mock_lw):
        result = wm.get_window_rect("Nonexistent")
        assert result is None

    @patch.object(wm, "list_windows", return_value=[
        {"title": "Chrome", "x": 10, "y": 20, "width": 800, "height": 600},
    ])
    def test_matching_window_returns_rect(self, mock_lw):
        result = wm.get_window_rect("Chrome")
        assert result == (10, 20, 800, 600)

    @patch.object(wm, "list_windows", return_value=[
        {"title": "Chrome", "x": 10, "y": 20, "width": 800, "height": 600, "hwnd": 42},
    ])
    def test_minimized_window_restores(self, mock_lw):
        """If the window rect looks minimized, restore is attempted."""
        # First call: minimized rect. Second call: restored.
        mock_lw.side_effect = [
            [{"title": "Chrome", "x": -32000, "y": -32000, "width": 800, "height": 600, "hwnd": 42}],
            [{"title": "Chrome", "x": 100, "y": 100, "width": 800, "height": 600, "hwnd": 42}],
        ]
        with patch.object(wm, "restore_window_hwnd", return_value=True) as mock_restore:
            result = wm.get_window_rect("Chrome")
            mock_restore.assert_called_once_with(42)
            assert result == (100, 100, 800, 600)

    @patch.object(wm, "list_windows", side_effect=OSError("boom"))
    def test_list_windows_error_returns_none(self, mock_lw):
        wm._Win32Error = OSError
        result = wm.get_window_rect("Chrome")
        assert result is None


# ---------------------------------------------------------------------------
# restore_window_hwnd — win32 path
# ---------------------------------------------------------------------------

class TestRestoreWindowHwnd:
    """Test restore_window_hwnd with HAS_WIN32 toggled."""

    @patch.object(wm, "HAS_WIN32", True)
    def test_win32_restore_success(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()
        wm.win32gui = mock_gui
        wm.win32con = mock_con
        wm._Win32Error = OSError
        result = wm.restore_window_hwnd(42)
        assert result is True
        mock_gui.ShowWindow.assert_called_once_with(42, 9)

    @patch.object(wm, "HAS_WIN32", True)
    def test_win32_restore_error(self):
        mock_gui = _mock_win32gui()
        mock_gui.ShowWindow.side_effect = OSError("fail")
        wm.win32gui = mock_gui
        wm._Win32Error = OSError
        result = wm.restore_window_hwnd(42)
        assert result is False

    @patch.object(wm, "HAS_WIN32", False)
    def test_no_win32_returns_false(self):
        result = wm.restore_window_hwnd(42)
        assert result is False

    @patch.object(wm, "HAS_WIN32", True)
    def test_zero_hwnd_returns_false(self):
        result = wm.restore_window_hwnd(0)
        assert result is False


# ---------------------------------------------------------------------------
# restore_window — edge cases
# ---------------------------------------------------------------------------

class TestRestoreWindowEdgeCases:
    """Test restore_window with empty title and error paths."""

    def test_empty_title_returns_false(self):
        result = wm.restore_window("")
        assert result is False

    @patch.object(wm, "list_windows", side_effect=OSError("boom"))
    def test_list_windows_error_returns_false(self, mock_lw):
        wm._Win32Error = OSError
        result = wm.restore_window("Chrome")
        assert result is False


# ---------------------------------------------------------------------------
# close_window — win32 path
# ---------------------------------------------------------------------------

class TestCloseWindowWin32:
    """Test close_window with HAS_WIN32=True."""

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_closes_matching_window(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()

        def fake_enum(callback, extra):
            callback(101, None)

        mock_gui.EnumWindows.side_effect = fake_enum
        mock_gui.IsWindowVisible.return_value = True
        mock_gui.GetWindowText.return_value = "Notepad"

        wm.win32gui = mock_gui
        wm.win32con = mock_con
        wm._Win32Error = OSError
        result = wm.close_window("Notepad")
        assert result is True
        mock_gui.PostMessage.assert_called_once_with(101, 0x0010, 0, 0)

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_no_match_returns_false(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()

        def fake_enum(callback, extra):
            callback(101, None)

        mock_gui.EnumWindows.side_effect = fake_enum
        mock_gui.IsWindowVisible.return_value = True
        mock_gui.GetWindowText.return_value = "Chrome"

        wm.win32gui = mock_gui
        wm.win32con = mock_con
        result = wm.close_window("Notepad")
        assert result is False

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_enum_error_returns_false(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()
        mock_gui.EnumWindows.side_effect = OSError("fail")

        wm.win32gui = mock_gui
        wm.win32con = mock_con
        wm._Win32Error = OSError
        result = wm.close_window("Notepad")
        assert result is False

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_closes_only_first_match(self):
        mock_gui = _mock_win32gui()
        mock_con = _mock_win32con()

        def fake_enum(callback, extra):
            callback(101, None)
            callback(102, None)  # second should be ignored after first match

        mock_gui.EnumWindows.side_effect = fake_enum
        mock_gui.IsWindowVisible.return_value = True
        mock_gui.GetWindowText.return_value = "Notepad"

        wm.win32gui = mock_gui
        wm.win32con = mock_con
        wm._Win32Error = OSError
        result = wm.close_window("Notepad")
        assert result is True
        # Only called once — second window skipped
        assert mock_gui.PostMessage.call_count == 1


# ---------------------------------------------------------------------------
# close_window — pgw path
# ---------------------------------------------------------------------------

class TestCloseWindowPGW:
    """Test close_window with HAS_PGW=True."""

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_close_success(self):
        mock_pgw = _mock_pgw()
        wm.pgw = mock_pgw
        result = wm.close_window("PGW Window")
        assert result is True
        mock_pgw.getWindowsWithTitle.return_value[0].close.assert_called_once()

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_no_match(self):
        mock_pgw = _mock_pgw()
        mock_pgw.getWindowsWithTitle.return_value = []
        wm.pgw = mock_pgw
        result = wm.close_window("Nonexistent")
        assert result is False

    @patch.object(wm, "HAS_WIN32", False)
    @patch.object(wm, "HAS_PGW", True)
    def test_pgw_error(self):
        mock_pgw = _mock_pgw()
        mock_pgw.getWindowsWithTitle.side_effect = OSError("fail")
        wm.pgw = mock_pgw
        result = wm.close_window("PGW Window")
        assert result is False


# ---------------------------------------------------------------------------
# get_target_window_rect — candidate scanning edge cases
# ---------------------------------------------------------------------------

class TestGetTargetWindowRectCandidates:
    """Test candidate sorting and filtering in get_target_window_rect."""

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_prefers_focused_candidate(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowText.return_value = "Sentinel Desktop"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        wm.win32gui = mock_gui
        wm._Win32Error = OSError

        with patch.object(wm, "list_windows", return_value=[
            {"title": "Chrome", "x": 10, "y": 20, "width": 800, "height": 600, "is_focused": False},
            {"title": "Notepad", "x": 5, "y": 5, "width": 900, "height": 700, "is_focused": True},
        ]):
            result = wm.get_target_window_rect()
        assert result is not None
        assert result[4] == "Notepad"  # focused one wins

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_candidate_scan_error_falls_through(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowText.return_value = "Sentinel Desktop"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        wm.win32gui = mock_gui
        wm._Win32Error = OSError

        with patch.object(wm, "list_windows", side_effect=OSError("scan fail")):
            result = wm.get_target_window_rect()
        assert result is None

    @patch.object(wm, "HAS_WIN32", True)
    @patch.object(wm, "HAS_PGW", False)
    def test_self_window_candidate_skipped(self):
        mock_gui = _mock_win32gui()
        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowText.return_value = "Sentinel Desktop"
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)
        wm.win32gui = mock_gui
        wm._Win32Error = OSError

        with patch.object(wm, "list_windows", return_value=[
            {"title": "Sentinel Desktop v3", "x": 0, "y": 0, "width": 800, "height": 600, "is_focused": False},
        ]):
            result = wm.get_target_window_rect()
        assert result is None
