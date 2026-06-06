"""Gap tests for stealth_input.py — _get_focus_hwnd ctypes paths, _GUI_THREAD_INFO else branch."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from core import stealth_input


class TestGetFocusHwndCtypesPaths:
    """_get_focus_hwnd with ctypes -- success and failure paths (lines 251-258)."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific ctypes.windll test")
    @patch.object(stealth_input, "_HAS_WIN32", True)
    def test_ctypes_success_returns_focus(self):
        """When GetGUIThreadInfo succeeds and hwndFocus is nonzero, returns it."""
        mock_user32 = MagicMock()
        mock_user32.GetGUIThreadInfo.return_value = True
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        with patch("core.stealth_input.win32api") as mock_api:
            mock_api.GetWindowThreadProcessId.return_value = (1234,)
            with patch("ctypes.sizeof", return_value=64):
                with patch("ctypes.byref"):
                    with patch("ctypes.windll", mock_windll):
                        # Create a mock info object that behaves like the real one
                        mock_info = MagicMock()
                        mock_info.hwndFocus = 999
                        mock_info.cbSize = 64
                        # Make _GUI_THREAD_INFO() return our mock
                        original = stealth_input._GUI_THREAD_INFO
                        stealth_input._GUI_THREAD_INFO = MagicMock(return_value=mock_info)
                        try:
                            result = stealth_input._get_focus_hwnd(123)
                        finally:
                            stealth_input._GUI_THREAD_INFO = original
        assert result == 999

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific ctypes.windll test")
    @patch.object(stealth_input, "_HAS_WIN32", True)
    def test_ctypes_returns_zero_focus_returns_none(self):
        """When hwndFocus is 0, returns None (line 254 -- int(0) or None)."""
        mock_user32 = MagicMock()
        mock_user32.GetGUIThreadInfo.return_value = True
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        with patch("core.stealth_input.win32api") as mock_api:
            mock_api.GetWindowThreadProcessId.return_value = (1234,)
            with patch("ctypes.sizeof", return_value=64):
                with patch("ctypes.byref"):
                    with patch("ctypes.windll", mock_windll):
                        mock_info = MagicMock()
                        mock_info.hwndFocus = 0
                        mock_info.cbSize = 64
                        original = stealth_input._GUI_THREAD_INFO
                        stealth_input._GUI_THREAD_INFO = MagicMock(return_value=mock_info)
                        try:
                            result = stealth_input._get_focus_hwnd(123)
                        finally:
                            stealth_input._GUI_THREAD_INFO = original
        assert result is None

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific ctypes.windll test")
    @patch.object(stealth_input, "_HAS_WIN32", True)
    def test_ctypes_get_gui_thread_info_fails_returns_none(self):
        """When GetGUIThreadInfo returns False, falls through to return None (line 258)."""
        mock_user32 = MagicMock()
        mock_user32.GetGUIThreadInfo.return_value = False
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        with patch("core.stealth_input.win32api") as mock_api:
            mock_api.GetWindowThreadProcessId.return_value = (1234,)
            with patch("ctypes.sizeof", return_value=64):
                with patch("ctypes.byref"):
                    with patch("ctypes.windll", mock_windll):
                        mock_info = MagicMock()
                        mock_info.cbSize = 64
                        original = stealth_input._GUI_THREAD_INFO
                        stealth_input._GUI_THREAD_INFO = MagicMock(return_value=mock_info)
                        try:
                            result = stealth_input._get_focus_hwnd(123)
                        finally:
                            stealth_input._GUI_THREAD_INFO = original
        assert result is None


class TestGUIsThreadInfoElseBranch:
    """_GUI_THREAD_INFO else branch (lines 289-290)."""

    def test_else_branch_class_exists(self):
        """When _HAS_WIN32 is False, _GUI_THREAD_INFO is a bare class."""
        original = stealth_input._HAS_WIN32
        stealth_input._HAS_WIN32 = False
        try:
            assert hasattr(stealth_input, "_GUI_THREAD_INFO")
            inst = stealth_input._GUI_THREAD_INFO()
            assert inst is not None
        finally:
            stealth_input._HAS_WIN32 = original
