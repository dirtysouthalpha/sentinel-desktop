"""Gap tests for stealth_input.py — direct function coverage for post_click, post_text,
post_key, post_named_key, post_hotkey, _get_focus_hwnd.
"""

import importlib
import sys

import pytest

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="Win32 ctypes tests",
)

from unittest.mock import patch

from core import stealth_input


@pytest.fixture(autouse=True)
def _reload_stealth():
    """Reload stealth_input before each test to avoid state pollution."""
    importlib.reload(stealth_input)
    yield
    importlib.reload(stealth_input)


class TestIsAvailable:
    """is_available probe."""

    @patch.object(stealth_input, "_HAS_WIN32", True)
    def test_available(self):
        assert stealth_input.is_available() is True

    @patch.object(stealth_input, "_HAS_WIN32", False)
    def test_not_available(self):
        assert stealth_input.is_available() is False


class TestPostClick:
    """post_click with win32."""

    @patch.object(stealth_input, "_HAS_WIN32", False)
    def test_no_win32_returns_false(self):
        assert stealth_input.post_click(100, 200) is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_left_click(self, mock_con, mock_api, mock_gui):
        mock_gui.WindowFromPoint.return_value = 123
        mock_gui.ScreenToClient.return_value = (10, 20)
        mock_con.WM_LBUTTONDOWN = 0x0201
        mock_con.WM_LBUTTONUP = 0x0202
        mock_con.MK_LBUTTON = 1
        result = stealth_input.post_click(100, 200)
        assert result is True
        assert mock_api.PostMessage.call_count == 2

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_right_click(self, mock_con, mock_api, mock_gui):
        mock_gui.WindowFromPoint.return_value = 123
        mock_gui.ScreenToClient.return_value = (10, 20)
        mock_con.WM_RBUTTONDOWN = 0x0204
        mock_con.WM_RBUTTONUP = 0x0205
        mock_con.MK_RBUTTON = 2
        result = stealth_input.post_click(100, 200, button="right")
        assert result is True
        assert mock_api.PostMessage.call_count == 2

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_middle_click(self, mock_con, mock_api, mock_gui):
        mock_gui.WindowFromPoint.return_value = 123
        mock_gui.ScreenToClient.return_value = (10, 20)
        mock_con.WM_MBUTTONDOWN = 0x0207
        mock_con.WM_MBUTTONUP = 0x0208
        mock_con.MK_MBUTTON = 16
        result = stealth_input.post_click(100, 200, button="middle")
        assert result is True
        assert mock_api.PostMessage.call_count == 2

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_double_click(self, mock_con, mock_api, mock_gui):
        mock_gui.WindowFromPoint.return_value = 123
        mock_gui.ScreenToClient.return_value = (10, 20)
        mock_con.WM_LBUTTONDOWN = 0x0201
        mock_con.WM_LBUTTONUP = 0x0202
        mock_con.MK_LBUTTON = 1
        result = stealth_input.post_click(100, 200, clicks=2)
        assert result is True
        assert mock_api.PostMessage.call_count == 4

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    def test_no_hwnd_returns_false(self, mock_gui):
        mock_gui.WindowFromPoint.return_value = 0
        result = stealth_input.post_click(100, 200)
        assert result is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    def test_exception_returns_false(self, mock_gui):
        mock_gui.WindowFromPoint.side_effect = RuntimeError("fail")
        result = stealth_input.post_click(100, 200)
        assert result is False


class TestPostText:
    """post_text with win32."""

    @patch.object(stealth_input, "_HAS_WIN32", False)
    def test_no_win32_returns_false(self):
        assert stealth_input.post_text("hello") is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    def test_empty_text_returns_false(self):
        assert stealth_input.post_text("") is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_post_text_to_hwnd(self, mock_con, mock_api, mock_gui):
        mock_con.WM_CHAR = 0x0102
        with patch("core.stealth_input._get_focus_hwnd", return_value=None):
            result = stealth_input.post_text("AB", hwnd=123)
        assert result is True
        assert mock_api.PostMessage.call_count == 2

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_post_text_no_hwnd_uses_foreground(self, mock_con, mock_api, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 456
        mock_con.WM_CHAR = 0x0102
        with patch("core.stealth_input._get_focus_hwnd", return_value=None):
            result = stealth_input.post_text("X", hwnd=None)
        assert result is True

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    def test_no_foreground_returns_false(self, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 0
        result = stealth_input.post_text("hello", hwnd=None)
        assert result is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    def test_exception_returns_false(self, mock_api, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_api.PostMessage.side_effect = RuntimeError("fail")
        with patch("core.stealth_input._get_focus_hwnd", return_value=None):
            with patch("core.stealth_input.win32con") as mock_con:
                mock_con.WM_CHAR = 0x0102
                result = stealth_input.post_text("A", hwnd=None)
        assert result is False


class TestPostKey:
    """post_key with win32."""

    @patch.object(stealth_input, "_HAS_WIN32", False)
    def test_no_win32_returns_false(self):
        assert stealth_input.post_key(0x0D) is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_post_key_to_hwnd(self, mock_con, mock_api, mock_gui):
        mock_con.WM_KEYDOWN = 0x0100
        mock_con.WM_KEYUP = 0x0101
        result = stealth_input.post_key(0x0D, hwnd=123)
        assert result is True
        assert mock_api.PostMessage.call_count == 2

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_post_key_no_hwnd(self, mock_con, mock_api, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 456
        mock_con.WM_KEYDOWN = 0x0100
        mock_con.WM_KEYUP = 0x0101
        result = stealth_input.post_key(0x0D, hwnd=None)
        assert result is True

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    def test_no_foreground_returns_false(self, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 0
        result = stealth_input.post_key(0x0D, hwnd=None)
        assert result is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    def test_exception_returns_false(self, mock_api, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_api.PostMessage.side_effect = RuntimeError("fail")
        result = stealth_input.post_key(0x0D, hwnd=None)
        assert result is False


class TestPostNamedKey:
    """post_named_key lookup and delegation."""

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.post_key", return_value=True)
    def test_known_key(self, mock_pk):
        result = stealth_input.post_named_key("enter")
        assert result is True
        mock_pk.assert_called_once_with(0x0D, hwnd=None)

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.post_key", return_value=True)
    def test_case_insensitive(self, mock_pk):
        result = stealth_input.post_named_key("ENTER")
        assert result is True

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.post_text", return_value=True)
    def test_single_char_falls_back_to_post_text(self, mock_pt):
        result = stealth_input.post_named_key("a")
        assert result is True
        mock_pt.assert_called_once_with("a", hwnd=None)

    def test_unknown_multi_char_returns_false(self):
        result = stealth_input.post_named_key("unknown_key")
        assert result is False

    def test_empty_returns_false(self):
        result = stealth_input.post_named_key("")
        assert result is False

    def test_none_returns_false(self):
        result = stealth_input.post_named_key(None)
        assert result is False


class TestPostHotkey:
    """post_hotkey chorded hotkey."""

    @patch.object(stealth_input, "_HAS_WIN32", False)
    def test_no_win32_returns_false(self):
        assert stealth_input.post_hotkey(["ctrl", "c"]) is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    def test_empty_keys_returns_false(self):
        assert stealth_input.post_hotkey([]) is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_ctrl_c_hotkey(self, mock_con, mock_api, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_con.WM_KEYDOWN = 0x0100
        mock_con.WM_KEYUP = 0x0101
        with patch("core.stealth_input._get_focus_hwnd", return_value=None):
            result = stealth_input.post_hotkey(["ctrl", "c"], hwnd=None)
        assert result is True
        assert mock_api.PostMessage.call_count == 4

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_named_key_in_hotkey(self, mock_con, mock_api, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_con.WM_KEYDOWN = 0x0100
        mock_con.WM_KEYUP = 0x0101
        with patch("core.stealth_input._get_focus_hwnd", return_value=None):
            result = stealth_input.post_hotkey(["alt", "f4"], hwnd=None)
        assert result is True

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_only_modifiers_no_main_key_returns_false(self, mock_con, mock_api, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        with patch("core.stealth_input._get_focus_hwnd", return_value=None):
            result = stealth_input.post_hotkey(["ctrl", "shift"], hwnd=None)
        assert result is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_unknown_key_in_hotkey_returns_false(self, mock_con, mock_api, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        with patch("core.stealth_input._get_focus_hwnd", return_value=None):
            result = stealth_input.post_hotkey(["ctrl", "unknownkey"], hwnd=None)
        assert result is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    def test_no_foreground_returns_false(self, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 0
        result = stealth_input.post_hotkey(["ctrl", "c"], hwnd=None)
        assert result is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    def test_exception_returns_false(self, mock_api, mock_gui):
        mock_gui.GetForegroundWindow.return_value = 123
        mock_api.PostMessage.side_effect = RuntimeError("fail")
        with patch("core.stealth_input._get_focus_hwnd", return_value=None):
            result = stealth_input.post_hotkey(["ctrl", "c"], hwnd=None)
        assert result is False

    @patch.object(stealth_input, "_HAS_WIN32", True)
    @patch("core.stealth_input.win32gui")
    @patch("core.stealth_input.win32api")
    @patch("core.stealth_input.win32con")
    def test_hotkey_with_explicit_hwnd(self, mock_con, mock_api, mock_gui):
        mock_con.WM_KEYDOWN = 0x0100
        mock_con.WM_KEYUP = 0x0101
        with patch("core.stealth_input._get_focus_hwnd", return_value=None):
            result = stealth_input.post_hotkey(["ctrl", "a"], hwnd=999)
        assert result is True
        mock_gui.GetForegroundWindow.assert_not_called()


class TestGetFocusHwnd:
    """_get_focus_hwnd internal."""

    @patch.object(stealth_input, "_HAS_WIN32", True)
    def test_exception_returns_none(self):
        with patch("core.stealth_input.win32api") as mock_api:
            mock_api.GetWindowThreadProcessId.side_effect = RuntimeError("fail")
            result = stealth_input._get_focus_hwnd(123)
        assert result is None

    @patch.object(stealth_input, "_HAS_WIN32", False)
    def test_no_win32_returns_none(self):
        stealth_input._GUI_THREAD_INFO = type("_GUI_THREAD_INFO", (), {})
        result = stealth_input._get_focus_hwnd(123)
        assert result is None
