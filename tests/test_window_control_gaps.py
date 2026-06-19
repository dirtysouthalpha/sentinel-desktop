"""Gap tests for core.window_control — covers lines 35, 59-68, 88-89."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestGetMonitorsWindowsBranch:
    """Line 35 — get_monitors() returns _get_monitors_win32() on Windows."""

    def test_get_monitors_calls_win32_on_windows(self, monkeypatch):
        from core import window_control

        expected = [{"index": 0, "x": 0, "y": 0, "width": 1920, "height": 1080, "is_primary": True}]
        monkeypatch.setattr(window_control, "_IS_WINDOWS", True)

        with patch.object(window_control, "_get_monitors_win32", return_value=expected) as mock_fn:
            result = window_control.get_monitors()

        mock_fn.assert_called_once()
        assert result == expected


class TestWin32CallbackBody:
    """Lines 59-68 — _callback inside _get_monitors_win32 is actually invoked."""

    def test_win32_callback_appends_rect(self):
        from core.window_control import _get_monitors_win32

        # We need:
        # 1. ctypes.WINFUNCTYPE to exist (may not on Linux) → create=True
        # 2. ctypes.windll.user32.EnumDisplayMonitors to call our callback
        # 3. Callback receives a mock lprcMonitor with .contents having left/top/right/bottom

        stored = {}

        # When MONITORENUMPROC = ctypes.WINFUNCTYPE(...) is called, return a class.
        # When MONITORENUMPROC(_callback) is called, store _callback and return a wrapper.
        class _FakeMonitorEnumProcType:
            def __init__(self_inner, fn):
                stored["fn"] = fn

        def fake_WINFUNCTYPE(*type_args):
            return _FakeMonitorEnumProcType

        class _FakeRect:
            left = 10
            top = 20
            right = 1930
            bottom = 1100

        class _FakeLprc:
            contents = _FakeRect()

        def fake_enum(none1, none2, proc, data):
            # proc is a _FakeMonitorEnumProcType instance
            if "fn" in stored:
                stored["fn"](None, None, _FakeLprc(), 0)

        mock_user32 = MagicMock()
        mock_user32.EnumDisplayMonitors.side_effect = fake_enum

        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32

        with (
            patch("ctypes.windll", mock_windll, create=True),
            patch("ctypes.WINFUNCTYPE", fake_WINFUNCTYPE, create=True),
        ):
            monitors = _get_monitors_win32()

        assert len(monitors) == 1
        assert monitors[0]["x"] == 10
        assert monitors[0]["y"] == 20
        assert monitors[0]["width"] == 1920  # 1930 - 10
        assert monitors[0]["height"] == 1080  # 1100 - 20

    def test_win32_callback_multiple_monitors(self):
        from core.window_control import _get_monitors_win32

        stored = {}

        class _FakeMonitorEnumProcType:
            def __init__(self_inner, fn):
                stored["fn"] = fn

        def fake_WINFUNCTYPE(*type_args):
            return _FakeMonitorEnumProcType

        rects_data = [
            (0, 0, 1920, 1080),
            (1920, 0, 3840, 1080),
        ]

        def fake_enum(none1, none2, proc, data):
            if "fn" in stored:
                for rect in rects_data:

                    class FakeRect:
                        left, top, right, bottom = rect

                    class FakeLprc:
                        contents = FakeRect()

                    stored["fn"](None, None, FakeLprc(), 0)

        mock_user32 = MagicMock()
        mock_user32.EnumDisplayMonitors.side_effect = fake_enum

        mock_windll = MagicMock()
        mock_windll.user32 = mock_user32

        with (
            patch("ctypes.windll", mock_windll, create=True),
            patch("ctypes.WINFUNCTYPE", fake_WINFUNCTYPE, create=True),
        ):
            monitors = _get_monitors_win32()

        assert len(monitors) == 2
        assert monitors[1]["x"] == 1920
        assert monitors[1]["is_primary"] is False


class TestWin32BothFallbacksFail:
    """Lines 88-89 — logger.warning when ctypes AND mss both fail."""

    def test_all_fallbacks_fail_returns_empty_list(self):
        from core.window_control import _get_monitors_win32

        with (
            patch("ctypes.windll", side_effect=AttributeError("no windll"), create=True),
            patch("mss.mss", side_effect=Exception("mss broken"), create=True),
        ):
            monitors = _get_monitors_win32()

        assert monitors == []

    def test_all_fallbacks_fail_logs_warning(self, caplog):
        import logging

        from core.window_control import _get_monitors_win32

        with (
            patch("ctypes.windll", side_effect=AttributeError("no windll"), create=True),
            patch("mss.mss", side_effect=Exception("mss totally broken"), create=True),
        ):
            with caplog.at_level(logging.WARNING, logger="core.window_control"):
                _get_monitors_win32()

        assert any("get_monitors failed" in r.message for r in caplog.records)
