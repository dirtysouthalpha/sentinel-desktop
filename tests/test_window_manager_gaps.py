"""Gap tests for window_manager.py — restore_window with missing hwnd."""

from unittest.mock import patch

from core.window_manager import restore_window


class TestRestoreWindowNoneHwnd:
    """restore_window skips windows with no hwnd key."""

    @patch("core.window_manager.list_windows")
    def test_window_with_no_hwnd_skipped(self, mock_lw):
        """Windows missing hwnd key should be skipped, not passed to restore_window_hwnd."""
        mock_lw.return_value = [{"title": "Chrome"}]
        with patch("core.window_manager.restore_window_hwnd") as mock_restore:
            result = restore_window("Chrome")
            mock_restore.assert_not_called()
            assert result is False

    @patch("core.window_manager.list_windows")
    def test_window_with_none_hwnd_skipped(self, mock_lw):
        mock_lw.return_value = [{"title": "Chrome", "hwnd": None}]
        with patch("core.window_manager.restore_window_hwnd") as mock_restore:
            result = restore_window("Chrome")
            mock_restore.assert_not_called()
            assert result is False

    @patch("core.window_manager.list_windows")
    def test_window_with_valid_hwnd_passes_through(self, mock_lw):
        mock_lw.return_value = [{"title": "Chrome", "hwnd": 42}]
        with patch("core.window_manager.restore_window_hwnd", return_value=True) as mock_restore:
            result = restore_window("Chrome")
            mock_restore.assert_called_once_with(42)
            assert result is True

    @patch("core.window_manager.list_windows")
    def test_mixed_windows_restores_first_match_only(self, mock_lw):
        mock_lw.return_value = [
            {"title": "Notepad"},
            {"title": "Chrome", "hwnd": 99},
            {"title": "Chrome Backup", "hwnd": 100},
        ]
        with patch("core.window_manager.restore_window_hwnd", return_value=True) as mock_restore:
            result = restore_window("Chrome")
            assert result is True
            # Only called once for the first match
            mock_restore.assert_called_once_with(99)
