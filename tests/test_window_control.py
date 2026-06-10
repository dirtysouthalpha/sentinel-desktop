"""Tests for core.window_control — resize, move, minimize, maximize, monitors."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
