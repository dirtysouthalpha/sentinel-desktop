"""Gap tests for core/window_manager.py — branches the platform-skipped Win32
suites leave uncovered on Linux, plus the no-backend fall-throughs, the
minimized-window rect refetch, and the module-level Windows import guards.

The Win32 helpers normally live behind a ``skipif(not win)`` mark because they
patch ``win32gui``/``win32con`` (which don't exist as module attributes on
Linux). Here we create those attributes with ``create=True`` so the
HAS_WIN32 code paths can run on any platform.
"""

from __future__ import annotations

import builtins
import importlib
import types
from unittest.mock import MagicMock, patch

import core.window_manager as wm
from core.window_manager import (
    _is_self_window,
    _looks_minimized,
    close_window,
    focus_window,
    get_focused_window_rect,
    get_target_window_rect,
    get_window_rect,
    list_windows,
)

# ---------------------------------------------------------------------------
# _looks_minimized — pure logic (line 255)
# ---------------------------------------------------------------------------


class TestLooksMinimized:
    def test_none_rect_is_minimized(self):
        assert _looks_minimized(None) is True

    def test_short_tuple_is_minimized(self):
        assert _looks_minimized((1, 2)) is True

    def test_zero_size_is_minimized(self):
        assert _looks_minimized((0, 0, 0, 0)) is True

    def test_parked_offscreen_is_minimized(self):
        assert _looks_minimized((-32000, -32000, 100, 100)) is True

    def test_normal_rect_not_minimized(self):
        assert _looks_minimized((0, 0, 800, 600)) is False


# ---------------------------------------------------------------------------
# No-backend fall-throughs (branches 120->128, 161->168, 320->328)
# ---------------------------------------------------------------------------


class TestNoBackendFallThroughs:
    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", False)
    def test_focus_window_no_backend_returns_false(self):
        assert focus_window("Anything") is False

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", False)
    def test_get_focused_window_rect_no_backend_returns_none(self):
        assert get_focused_window_rect() is None

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", False)
    def test_close_window_no_backend_returns_false(self):
        assert close_window("Anything") is False

    @patch("core.window_manager.HAS_WIN32", False)
    @patch("core.window_manager.HAS_PGW", False)
    def test_list_windows_no_backend_returns_empty(self):
        """Line 79: with no window library, list_windows logs and returns []."""
        assert list_windows() == []

    @patch("core.window_manager.HAS_WIN32", False)
    def test_get_target_window_rect_no_win32_uses_scan(self):
        """Branch 181->191: HAS_WIN32 False skips the foreground block."""
        other = {"title": "Editor", "x": 1, "y": 2, "width": 320, "height": 240}
        with patch("core.window_manager.list_windows", return_value=[other]):
            result = get_target_window_rect()
        assert result == (1, 2, 320, 240, "Editor")


class TestIsSelfWindow:
    def test_empty_title_not_self(self):
        """Line 140: an empty title is never the Sentinel window."""
        assert _is_self_window("") is False


# ---------------------------------------------------------------------------
# get_window_rect minimized-window refetch (branches 236->243, 239->243, 240->239)
# ---------------------------------------------------------------------------


class TestGetWindowRectMinimized:
    def test_skips_non_matching_window(self):
        """Branch 232->230: a listed window whose title doesn't match the needle
        is skipped and iteration continues."""
        windows = [
            {"title": "Calculator", "x": 0, "y": 0, "width": 10, "height": 10},
            {"title": "Notepad", "x": 1, "y": 2, "width": 800, "height": 600},
        ]
        with patch("core.window_manager.list_windows", return_value=windows):
            rect = get_window_rect("notepad")
        assert rect == (1, 2, 800, 600)

    def test_minimized_window_without_hwnd_returns_rect(self):
        """Branch 236->243: a matching minimized window with no 'hwnd' key is
        returned as-is (no restore attempt)."""
        win = {"title": "Notepad", "x": -32000, "y": -32000, "width": 200, "height": 100}
        with patch("core.window_manager.list_windows", return_value=[win]):
            rect = get_window_rect("notepad")
        assert rect == (-32000, -32000, 200, 100)

    def test_minimized_window_with_hwnd_refetch_no_match(self):
        """Branches 239->243 / 240->239: after restoring, the refetch yields no
        window whose title matches, so the original rect is returned."""
        minimized = {
            "title": "Notepad",
            "x": -32000,
            "y": -32000,
            "width": 200,
            "height": 100,
            "hwnd": 4242,
        }
        # First call lists the minimized window; the refetch lists only an
        # unrelated window (240->239 keeps looping, 239->243 ends the loop).
        list_results = [[minimized], [{"title": "Calculator", "x": 0, "y": 0, "width": 10, "height": 10}]]
        with patch("core.window_manager.list_windows", side_effect=list_results), \
             patch("core.window_manager.restore_window_hwnd") as mock_restore:
            rect = get_window_rect("notepad")
        mock_restore.assert_called_once_with(4242)
        assert rect == (-32000, -32000, 200, 100)


# ---------------------------------------------------------------------------
# Win32 inner branches that need create=True mocks (113-114, 184->191, 309->exit)
# ---------------------------------------------------------------------------


class TestWin32InnerBranches:
    def test_focus_window_alt_tap_oserror_is_swallowed(self):
        """Lines 113-114: the Alt-tap keybd_event raising OSError is logged and
        focus still proceeds to SetForegroundWindow."""
        mock_gui = MagicMock()
        mock_con = MagicMock()
        mock_con.SW_RESTORE = 9
        fake_ctypes = types.ModuleType("ctypes")
        fake_ctypes.windll = MagicMock()
        fake_ctypes.windll.user32.keybd_event.side_effect = OSError("no input desktop")

        with patch("core.window_manager.HAS_WIN32", True), \
             patch("core.window_manager.win32gui", mock_gui, create=True), \
             patch("core.window_manager.win32con", mock_con, create=True), \
             patch("core.window_manager.list_windows", return_value=[{"title": "Chrome", "hwnd": 77}]), \
             patch.dict("sys.modules", {"ctypes": fake_ctypes}):
            result = focus_window("chrome")

        assert result is True
        mock_gui.SetForegroundWindow.assert_called_once_with(77)

    def test_get_target_window_rect_no_foreground(self):
        """Branch 184->191: GetForegroundWindow returns 0, so the foreground
        block is skipped and the scan path is used."""
        mock_gui = MagicMock()
        mock_gui.GetForegroundWindow.return_value = 0
        other = {"title": "Editor", "x": 5, "y": 6, "width": 640, "height": 480}
        with patch("core.window_manager.HAS_WIN32", True), \
             patch("core.window_manager.win32gui", mock_gui, create=True), \
             patch("core.window_manager.list_windows", return_value=[other]):
            result = get_target_window_rect()
        assert result == (5, 6, 640, 480, "Editor")

    def test_close_window_skips_invisible_window(self):
        """Branch 309->exit: the EnumWindows callback returns early for a window
        that isn't visible, so nothing is closed."""
        mock_gui = MagicMock()
        mock_con = MagicMock()
        mock_gui.IsWindowVisible.return_value = False

        def fake_enum(callback, _):
            callback(123, None)

        mock_gui.EnumWindows.side_effect = fake_enum
        with patch("core.window_manager.HAS_WIN32", True), \
             patch("core.window_manager.win32gui", mock_gui, create=True), \
             patch("core.window_manager.win32con", mock_con, create=True):
            result = close_window("Anything")
        assert result is False
        mock_gui.PostMessage.assert_not_called()


# ---------------------------------------------------------------------------
# Module-level Windows import guards (lines 15-16, 21-22, 26)
# ---------------------------------------------------------------------------


class TestWindowsImportGuards:
    def test_windows_with_failing_optional_imports(self):
        """On Windows with win32/pygetwindow missing but pywintypes present,
        HAS_WIN32/HAS_PGW fall back to False and _Win32Error binds to
        pywintypes.error. Reloaded under a faked platform and restored after."""
        real_import = builtins.__import__
        fake_pywintypes = types.ModuleType("pywintypes")

        class _PyWinError(Exception):
            pass

        fake_pywintypes.error = _PyWinError
        blocked = {"win32con", "win32gui", "pygetwindow"}

        def fake_import(name, *args, **kwargs):
            if name in blocked:
                raise ImportError(f"blocked {name}")
            if name == "pywintypes":
                return fake_pywintypes
            return real_import(name, *args, **kwargs)

        try:
            with patch("platform.system", return_value="Windows"), \
                 patch("builtins.__import__", side_effect=fake_import):
                reloaded = importlib.reload(wm)
                assert reloaded.HAS_WIN32 is False
                assert reloaded.HAS_PGW is False
                assert reloaded._Win32Error is _PyWinError
        finally:
            importlib.reload(wm)
        # Back to the Linux defaults for the rest of the session.
        assert wm.HAS_WIN32 is False
        assert wm._Win32Error is OSError

    def test_windows_with_all_optional_imports_present(self):
        """On Windows with every optional dependency available, HAS_WIN32 and
        HAS_PGW are True (lines 12-14, 19-20, 24-26)."""
        real_import = builtins.__import__

        class _PyWinError(Exception):
            pass

        fakes = {
            "win32con": types.ModuleType("win32con"),
            "win32gui": types.ModuleType("win32gui"),
            "pygetwindow": types.ModuleType("pygetwindow"),
            "pywintypes": types.ModuleType("pywintypes"),
        }
        fakes["pywintypes"].error = _PyWinError

        def fake_import(name, *args, **kwargs):
            if name in fakes:
                return fakes[name]
            return real_import(name, *args, **kwargs)

        try:
            with patch("platform.system", return_value="Windows"), \
                 patch("builtins.__import__", side_effect=fake_import):
                reloaded = importlib.reload(wm)
                assert reloaded.HAS_WIN32 is True
                assert reloaded.HAS_PGW is True
                assert reloaded._Win32Error is _PyWinError
        finally:
            importlib.reload(wm)
        assert wm.HAS_WIN32 is False
        assert wm._Win32Error is OSError
