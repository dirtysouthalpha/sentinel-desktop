"""Gap-coverage tests for core/stealth_input.py Win32-specific paths.

Exercises lines 35-38, 111, 252-255, 259, 265-277 by mocking win32api
and ctypes.windll so the tests run cross-platform.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def stealth_module():
    """Reload stealth_input with mocked win32api/win32gui/win32con in sys.modules.

    This causes the import-time try block (lines 33-38) to succeed and
    _HAS_WIN32 to be True, plus the ctypes struct definitions (lines
    265-277) to be executed.
    """
    mock_win32api = MagicMock()
    mock_win32gui = MagicMock()
    mock_win32con = MagicMock()

    # Save state
    saved_modules = {}
    for mod_name in ("win32api", "win32gui", "win32con"):
        saved_modules[mod_name] = sys.modules.get(mod_name)

    # Inject mocks before import
    sys.modules["win32api"] = mock_win32api
    sys.modules["win32gui"] = mock_win32gui
    sys.modules["win32con"] = mock_win32con

    # Force reload so the try/except succeeds
    import core.stealth_input as si

    importlib.reload(si)

    yield si, mock_win32api, mock_win32gui, mock_win32con

    # Restore
    for mod_name, saved in saved_modules.items():
        if saved is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = saved

    # Reload again to restore original state
    importlib.reload(si)


# ---------------------------------------------------------------------------
# post_text delay path (line 111)
# ---------------------------------------------------------------------------


class TestPostTextDelay:
    """Test post_text with delay > 0 to cover the sleep path."""

    def test_post_text_with_delay(self, stealth_module):
        """post_text sleeps between characters when delay > 0."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module

        with (
            patch.object(si, "_get_focus_hwnd", return_value=None),
            patch("time.sleep") as mock_sleep,
        ):
            result = si.post_text("AB", delay=0.05, hwnd=100)

        assert result is True
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.05)

    def test_post_text_no_delay(self, stealth_module):
        """post_text doesn't sleep when delay is 0."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module

        with (
            patch.object(si, "_get_focus_hwnd", return_value=None),
            patch("time.sleep") as mock_sleep,
        ):
            result = si.post_text("A", delay=0, hwnd=100)

        assert result is True
        mock_sleep.assert_not_called()

    def test_post_text_default_delay(self, stealth_module):
        """post_text with default delay=0.005 sleeps between chars."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module

        with (
            patch.object(si, "_get_focus_hwnd", return_value=None),
            patch("time.sleep") as mock_sleep,
        ):
            result = si.post_text("AB", hwnd=100)

        assert result is True
        # Default delay is 0.005, so sleep should be called for each char
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.005)


# ---------------------------------------------------------------------------
# _get_focus_hwnd Win32 path (lines 252-255, 259)
# ---------------------------------------------------------------------------


class TestGetFocusHwndWin32:
    """Test _get_focus_hwnd with mocked Win32 APIs."""

    def test_get_focus_hwnd_success(self, stealth_module):
        """_get_focus_hwnd returns focused hwnd from GetGUIThreadInfo."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module

        mock_win32api.GetWindowThreadProcessId.return_value = (1234,)

        # Create mock ctypes with windll — explicit attr assignment to prevent
        # MagicMock auto-child creation recursion on Python 3.13.
        mock_user32 = MagicMock()
        mock_user32.GetGUIThreadInfo.return_value = True
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        mock_ctypes = MagicMock()
        mock_ctypes.sizeof.return_value = 64
        mock_ctypes.byref.return_value = MagicMock()
        mock_ctypes.windll = mock_windll

        # Mock _GUI_THREAD_INFO instance
        mock_info = MagicMock()
        mock_info.hwndFocus = 500

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            # Replace the class with one that returns our mock
            original_class = si._GUI_THREAD_INFO
            si._GUI_THREAD_INFO = lambda: mock_info
            try:
                result = si._get_focus_hwnd(999)
            finally:
                si._GUI_THREAD_INFO = original_class

        assert result == 500

    def test_get_focus_hwnd_get_gui_thread_info_fails(self, stealth_module):
        """_get_focus_hwnd returns None when GetGUIThreadInfo returns False."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module

        mock_win32api.GetWindowThreadProcessId.return_value = (1234,)

        mock_user32 = MagicMock()
        mock_user32.GetGUIThreadInfo.return_value = False
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        mock_ctypes = MagicMock()
        mock_ctypes.sizeof.return_value = 64
        mock_ctypes.byref.return_value = MagicMock()
        mock_ctypes.windll = mock_windll

        mock_info = MagicMock()
        mock_info.hwndFocus = 0

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            original_class = si._GUI_THREAD_INFO
            si._GUI_THREAD_INFO = lambda: mock_info
            try:
                result = si._get_focus_hwnd(999)
            finally:
                si._GUI_THREAD_INFO = original_class

        assert result is None

    def test_get_focus_hwnd_oserror(self, stealth_module):
        """_get_focus_hwnd returns None on OSError."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module

        mock_win32api.GetWindowThreadProcessId.return_value = (1234,)

        mock_user32 = MagicMock()
        mock_user32.GetGUIThreadInfo.side_effect = OSError("fail")
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        mock_ctypes = MagicMock()
        mock_ctypes.windll = mock_windll

        mock_info = MagicMock()

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            original_class = si._GUI_THREAD_INFO
            si._GUI_THREAD_INFO = lambda: mock_info
            try:
                result = si._get_focus_hwnd(999)
            finally:
                si._GUI_THREAD_INFO = original_class

        assert result is None

    def test_get_focus_hwnd_attribute_error(self, stealth_module):
        """_get_focus_hwnd returns None on AttributeError."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module

        mock_win32api.GetWindowThreadProcessId.return_value = (1234,)

        mock_user32 = MagicMock()
        mock_user32.GetGUIThreadInfo.side_effect = AttributeError("fail")
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        mock_ctypes = MagicMock()
        mock_ctypes.windll = mock_windll

        mock_info = MagicMock()

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            original_class = si._GUI_THREAD_INFO
            si._GUI_THREAD_INFO = lambda: mock_info
            try:
                result = si._get_focus_hwnd(999)
            finally:
                si._GUI_THREAD_INFO = original_class

        assert result is None

    def test_get_focus_hwnd_runtime_error(self, stealth_module):
        """_get_focus_hwnd returns None on RuntimeError."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module

        mock_win32api.GetWindowThreadProcessId.return_value = (1234,)

        mock_user32 = MagicMock()
        mock_user32.GetGUIThreadInfo.side_effect = RuntimeError("fail")
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        mock_ctypes = MagicMock()
        mock_ctypes.windll = mock_windll

        mock_info = MagicMock()

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            original_class = si._GUI_THREAD_INFO
            si._GUI_THREAD_INFO = lambda: mock_info
            try:
                result = si._get_focus_hwnd(999)
            finally:
                si._GUI_THREAD_INFO = original_class

        assert result is None

    def test_get_focus_hwnd_zero_focus_returns_none(self, stealth_module):
        """_get_focus_hwnd returns None when hwndFocus is 0."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module

        mock_win32api.GetWindowThreadProcessId.return_value = (1234,)

        mock_user32 = MagicMock()
        mock_user32.GetGUIThreadInfo.return_value = True
        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32
        mock_ctypes = MagicMock()
        mock_ctypes.sizeof.return_value = 64
        mock_ctypes.byref.return_value = MagicMock()
        mock_ctypes.windll = mock_windll

        mock_info = MagicMock()
        mock_info.hwndFocus = 0

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            original_class = si._GUI_THREAD_INFO
            si._GUI_THREAD_INFO = lambda: mock_info
            try:
                result = si._get_focus_hwnd(999)
            finally:
                si._GUI_THREAD_INFO = original_class

        assert result is None


# ---------------------------------------------------------------------------
# post_text foreground window fallback (line 101)
# ---------------------------------------------------------------------------


class TestPostTextForegroundFallback:
    """Test post_text when hwnd is None — uses GetForegroundWindow."""

    def test_post_text_none_hwnd_uses_foreground(self, stealth_module):
        """post_text falls back to GetForegroundWindow when hwnd is None."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module
        mock_win32gui.GetForegroundWindow.return_value = 888

        with patch.object(si, "_get_focus_hwnd", return_value=None):
            result = si.post_text("hi", hwnd=None)

        assert result is True
        mock_win32gui.GetForegroundWindow.assert_called_once()

    def test_post_text_none_hwnd_no_foreground(self, stealth_module):
        """post_text returns False when GetForegroundWindow returns 0."""
        si, mock_win32api, mock_win32gui, mock_win32con = stealth_module
        mock_win32gui.GetForegroundWindow.return_value = 0

        result = si.post_text("hi", hwnd=None)
        assert result is False


# ---------------------------------------------------------------------------
# Module-level import path behavior
# ---------------------------------------------------------------------------


class TestModuleImportBehavior:
    """Test that the module handles win32 import availability correctly."""

    def test_has_win32_true_after_reload(self, stealth_module):
        """_HAS_WIN32 is True after reload with mocked win32api."""
        si, _, _, _ = stealth_module
        assert si._HAS_WIN32 is True
        assert si.is_available() is True

    def test_gui_thread_info_exists(self, stealth_module):
        """_GUI_THREAD_INFO class was created on the Win32 path."""
        si, _, _, _ = stealth_module
        assert hasattr(si, "_GUI_THREAD_INFO")
        # Should be a real class (not the stub)
        info = si._GUI_THREAD_INFO()
        assert hasattr(info, "cbSize")
        assert hasattr(info, "hwndFocus")
