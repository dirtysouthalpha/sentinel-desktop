"""Gap tests for launcher.py — focus failure fallback, _find_existing edge cases."""

from unittest.mock import MagicMock, patch

from core import launcher


class TestFindExistingEdgeCases:
    """_find_existing handles various window list scenarios."""

    def test_empty_needle_returns_none(self):
        result = launcher._find_existing("")
        assert result is None

    @patch("core.window_manager.list_windows", return_value=[])
    def test_no_windows_returns_none(self, mock_lw):
        result = launcher._find_existing("Chrome")
        assert result is None

    @patch("core.window_manager.list_windows")
    def test_prefers_focused_window(self, mock_lw):
        mock_lw.return_value = [
            {"title": "Chrome - Tab1", "is_focused": False},
            {"title": "Chrome - Tab2", "is_focused": True},
        ]
        result = launcher._find_existing("Chrome")
        assert result == "Chrome - Tab2"

    @patch("core.window_manager.list_windows")
    def test_skips_empty_titles(self, mock_lw):
        mock_lw.return_value = [
            {"title": "", "is_focused": False},
            {"title": "Chrome", "is_focused": False},
        ]
        result = launcher._find_existing("Chrome")
        assert result == "Chrome"

    @patch("core.window_manager.list_windows", side_effect=RuntimeError("fail"))
    def test_list_windows_exception_returns_none(self, mock_lw):
        result = launcher._find_existing("Chrome")
        assert result is None


class TestSmartOpenEdgeCases:
    """Additional smart_open edge cases."""

    @patch("core.window_manager.list_windows", return_value=[])
    @patch("core.window_manager.focus_window")
    @patch("core.launcher.subprocess.Popen")
    def test_focus_returns_false_launches(self, mock_popen, mock_focus, mock_lw):
        mock_lw.return_value = [{"title": "Chrome", "is_focused": False}]
        mock_focus.return_value = False
        mock_popen.return_value = MagicMock()
        result = launcher.smart_open("chrome")
        assert result["success"] is True
        assert result.get("focused") is False
        mock_popen.assert_called_once()

    @patch("core.window_manager.list_windows", return_value=[])
    @patch("core.launcher.subprocess.Popen", side_effect=FileNotFoundError("not found"))
    def test_popen_filenotfounderror(self, mock_popen, mock_lw):
        result = launcher.smart_open("some-app")
        assert result["success"] is False
        assert "not found" in result["output"]

    @patch("core.window_manager.list_windows", return_value=[])
    @patch("core.launcher.subprocess.Popen", side_effect=OSError("denied"))
    def test_popen_oserror(self, mock_popen, mock_lw):
        result = launcher.smart_open("some-app")
        assert result["success"] is False
        assert "denied" in result["output"]

    def test_whitespace_only_name_rejected(self):
        result = launcher.smart_open("   ")
        assert result["success"] is False
        assert result["error"] == "empty_name"

    @patch("core.window_manager.list_windows", return_value=[])
    @patch("core.launcher.subprocess.Popen")
    def test_exe_suffix_stripped(self, mock_popen, mock_lw):
        mock_popen.return_value = MagicMock()
        result = launcher.smart_open("chrome.exe")
        assert result["success"] is True
        cmd = mock_popen.call_args[0][0]
        assert "chrome" in cmd

    @patch("core.window_manager.list_windows", return_value=[])
    @patch("core.launcher.subprocess.Popen")
    def test_lnk_suffix_stripped(self, mock_popen, mock_lw):
        mock_popen.return_value = MagicMock()
        result = launcher.smart_open("outlook.lnk")
        assert result["success"] is True
        cmd = mock_popen.call_args[0][0]
        assert "outlook" in cmd


class TestIsSafeLaunchToken:
    """Additional _is_safe_launch_token cases."""

    def test_simple_name(self):
        assert launcher._is_safe_launch_token("notepad")

    def test_dotted_name(self):
        assert launcher._is_safe_launch_token("app.v2")

    def test_hyphenated(self):
        assert launcher._is_safe_launch_token("my-app")

    def test_plus_sign(self):
        assert launcher._is_safe_launch_token("notepad++")

    def test_empty_rejected(self):
        assert not launcher._is_safe_launch_token("")

    def test_space_rejected(self):
        assert not launcher._is_safe_launch_token("foo bar")

    def test_path_separator_rejected(self):
        assert not launcher._is_safe_launch_token("foo/bar")
