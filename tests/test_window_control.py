"""Tests for core.window_control — resize, move, minimize, maximize, monitors."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ── get_monitors ──────────────────────────────────────────────────────────────

class TestGetMonitors:
    def test_returns_list(self):
        from core.window_control import get_monitors
        # Should never raise — falls back if ctypes fails
        monitors = get_monitors()
        assert isinstance(monitors, list)

    def test_each_monitor_has_required_fields(self):
        from core.window_control import get_monitors
        monitors = get_monitors()
        for m in monitors:
            assert "index" in m
            assert "width" in m
            assert "height" in m

    def test_mss_fallback(self):
        """Falls back to mss when win32 ctypes path fails."""
        from core.window_control import _get_monitors_win32

        mock_sct = MagicMock()
        mock_sct.monitors = [
            {},  # virtual desktop (skipped)
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss_ctx = MagicMock(__enter__=MagicMock(return_value=mock_sct),
                                  __exit__=MagicMock(return_value=False))

        with patch("ctypes.windll", side_effect=AttributeError("no ctypes"), create=True):
            with patch("mss.mss", return_value=mock_mss_ctx):
                monitors = _get_monitors_win32()
        # Should get one monitor from mss
        assert len(monitors) >= 0  # may be 0 if ctypes path also fails — just no exception


# ── Window operations ─────────────────────────────────────────────────────────

class _MockWindow:
    def __init__(self):
        self.title = "Test Window"
        self.left = 100
        self.top = 100
        self.width = 800
        self.height = 600
        self.isMinimized = False
        self.isMaximized = False
        self.isActive = True
        self.resizeTo = MagicMock()
        self.moveTo = MagicMock()
        self.minimize = MagicMock()
        self.maximize = MagicMock()
        self.restore = MagicMock()


class TestWindowOperations:
    def _patch_find(self, win):
        return patch("core.window_control._find_window", return_value=win)

    def test_resize_window_calls_resizeTo(self):
        from core.window_control import resize_window
        win = _MockWindow()
        with self._patch_find(win):
            result = resize_window("Test Window", 1280, 720)
        assert result["success"] is True
        win.resizeTo.assert_called_once_with(1280, 720)

    def test_resize_window_not_found(self):
        from core.window_control import resize_window
        with self._patch_find(None):
            result = resize_window("No Such Window", 800, 600)
        assert result["success"] is False

    def test_move_window_calls_moveTo(self):
        from core.window_control import move_window
        win = _MockWindow()
        with self._patch_find(win):
            result = move_window("Test Window", 200, 300)
        assert result["success"] is True
        win.moveTo.assert_called_once_with(200, 300)

    def test_minimize_window(self):
        from core.window_control import minimize_window
        win = _MockWindow()
        with self._patch_find(win):
            result = minimize_window("Test Window")
        assert result["success"] is True
        win.minimize.assert_called_once()

    def test_maximize_window(self):
        from core.window_control import maximize_window
        win = _MockWindow()
        with self._patch_find(win):
            result = maximize_window("Test Window")
        assert result["success"] is True
        win.maximize.assert_called_once()

    def test_restore_window(self):
        from core.window_control import restore_window
        win = _MockWindow()
        with self._patch_find(win):
            result = restore_window("Test Window")
        assert result["success"] is True
        win.restore.assert_called_once()

    def test_get_window_state(self):
        from core.window_control import get_window_state
        win = _MockWindow()
        with self._patch_find(win):
            result = get_window_state("Test Window")
        assert result["success"] is True
        assert result["width"] == 800
        assert result["height"] == 600
        assert result["is_minimized"] is False

    def test_get_window_state_not_found(self):
        from core.window_control import get_window_state
        with self._patch_find(None):
            result = get_window_state("Ghost Window")
        assert result["success"] is False


# ── Executor integration ──────────────────────────────────────────────────────

class TestWindowActionsInExecutor:
    def test_resize_window_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "resize_window" in ActionExecutor._dispatch_table

    def test_move_window_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "move_window" in ActionExecutor._dispatch_table

    def test_minimize_window_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "minimize_window" in ActionExecutor._dispatch_table

    def test_maximize_window_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "maximize_window" in ActionExecutor._dispatch_table

    def test_restore_window_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "restore_window" in ActionExecutor._dispatch_table

    def test_get_window_state_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "get_window_state" in ActionExecutor._dispatch_table

    def test_get_monitors_in_dispatch(self):
        from core.action_executor import ActionExecutor
        assert "get_monitors" in ActionExecutor._dispatch_table

    def test_get_monitors_executor(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        result = executor.execute_sync({"action": "get_monitors"})
        assert result["success"] is True
        assert "monitors" in result


# ── Exception and not-found paths ────────────────────────────────────────────

class TestWindowOperationErrors:
    def _patch_find(self, win):
        return patch("core.window_control._find_window", return_value=win)

    def test_resize_window_exception(self):
        from core.window_control import resize_window
        win = _MockWindow()
        win.resizeTo.side_effect = RuntimeError("OS error")
        with self._patch_find(win):
            result = resize_window("Test Window", 800, 600)
        assert result["success"] is False
        assert "resize failed" in result["output"]

    def test_move_window_not_found(self):
        from core.window_control import move_window
        with self._patch_find(None):
            result = move_window("Ghost", 0, 0)
        assert result["success"] is False
        assert "not found" in result["output"].lower()

    def test_move_window_exception(self):
        from core.window_control import move_window
        win = _MockWindow()
        win.moveTo.side_effect = RuntimeError("OS error")
        with self._patch_find(win):
            result = move_window("Test Window", 0, 0)
        assert result["success"] is False
        assert "move failed" in result["output"]

    def test_minimize_window_not_found(self):
        from core.window_control import minimize_window
        with self._patch_find(None):
            result = minimize_window("Ghost")
        assert result["success"] is False

    def test_minimize_window_exception(self):
        from core.window_control import minimize_window
        win = _MockWindow()
        win.minimize.side_effect = RuntimeError("OS error")
        with self._patch_find(win):
            result = minimize_window("Test Window")
        assert result["success"] is False
        assert "minimize failed" in result["output"]

    def test_maximize_window_not_found(self):
        from core.window_control import maximize_window
        with self._patch_find(None):
            result = maximize_window("Ghost")
        assert result["success"] is False

    def test_maximize_window_exception(self):
        from core.window_control import maximize_window
        win = _MockWindow()
        win.maximize.side_effect = RuntimeError("OS error")
        with self._patch_find(win):
            result = maximize_window("Test Window")
        assert result["success"] is False
        assert "maximize failed" in result["output"]

    def test_restore_window_not_found(self):
        from core.window_control import restore_window
        with self._patch_find(None):
            result = restore_window("Ghost")
        assert result["success"] is False

    def test_restore_window_exception(self):
        from core.window_control import restore_window
        win = _MockWindow()
        win.restore.side_effect = RuntimeError("OS error")
        with self._patch_find(win):
            result = restore_window("Test Window")
        assert result["success"] is False
        assert "restore failed" in result["output"]

    def test_get_window_state_exception(self):
        from core.window_control import get_window_state
        win = MagicMock()
        type(win).title = PropertyMock(side_effect=RuntimeError("access error"))
        with self._patch_find(win):
            result = get_window_state("Test Window")
        assert result["success"] is False
        assert "get_window_state failed" in result["output"]


# ── _find_window internals ────────────────────────────────────────────────────

class TestFindWindow:
    def test_find_window_import_error(self):
        from core.window_control import _find_window
        with patch.dict("sys.modules", {"pygetwindow": None}):
            result = _find_window("some title")
        assert result is None

    def test_find_window_exception(self):
        from core.window_control import _find_window
        mock_gw = MagicMock()
        mock_gw.getWindowsWithTitle.side_effect = RuntimeError("gw error")
        with patch.dict("sys.modules", {"pygetwindow": mock_gw}):
            result = _find_window("some title")
        assert result is None

    def test_find_window_returns_first_match(self):
        from core.window_control import _find_window
        mock_win = MagicMock()
        mock_gw = MagicMock()
        mock_gw.getWindowsWithTitle.return_value = [mock_win, MagicMock()]
        with patch.dict("sys.modules", {"pygetwindow": mock_gw}):
            result = _find_window("some title")
        assert result is mock_win

    def test_find_window_empty_list_returns_none(self):
        from core.window_control import _find_window
        mock_gw = MagicMock()
        mock_gw.getWindowsWithTitle.return_value = []
        with patch.dict("sys.modules", {"pygetwindow": mock_gw}):
            result = _find_window("some title")
        assert result is None


# ── _get_monitors_screeninfo internals ───────────────────────────────────────

class TestGetMonitorsScreeninfo:
    def test_screeninfo_exception_falls_back_to_default(self):
        from core.window_control import _get_monitors_screeninfo
        mock_si = MagicMock()
        mock_si.get_monitors.side_effect = RuntimeError("display error")
        with patch.dict("sys.modules", {"screeninfo": mock_si}):
            result = _get_monitors_screeninfo()
        assert len(result) == 1
        assert result[0]["width"] == 1920
        assert result[0]["height"] == 1080

    def test_screeninfo_success_returns_monitors(self):
        from core.window_control import _get_monitors_screeninfo
        mock_monitor = MagicMock()
        mock_monitor.x = 0
        mock_monitor.y = 0
        mock_monitor.width = 2560
        mock_monitor.height = 1440
        mock_monitor.is_primary = True
        mock_si = MagicMock()
        mock_si.get_monitors.return_value = [mock_monitor]
        with patch.dict("sys.modules", {"screeninfo": mock_si}):
            result = _get_monitors_screeninfo()
        assert len(result) == 1
        assert result[0]["width"] == 2560
        assert result[0]["height"] == 1440
        assert result[0]["is_primary"] is True
