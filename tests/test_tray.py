"""Tests for gui.tray — pure function tests (no pystray/Tkinter required)."""

import importlib
from unittest.mock import patch


def test_is_available_returns_bool():
    from gui.tray import is_available

    assert isinstance(is_available(), bool)


def test_module_loads_without_pystray():
    with patch.dict("sys.modules", {"pystray": None}):
        import gui.tray as tray_mod

        importlib.reload(tray_mod)
        assert tray_mod._HAS_TRAY is False
        assert tray_mod.is_available() is False

    # Restore original import state
    importlib.reload(tray_mod)


def test_sentinel_tray_run_returns_false_without_pystray():
    from gui.tray import _HAS_TRAY, SentinelTray

    if _HAS_TRAY:
        return  # Can't test fallback when pystray IS installed

    tray = SentinelTray(
        on_show=lambda: None,
        on_hide=lambda: None,
    )
    assert tray.run() is False


def test_notify_is_noop_without_icon():
    from gui.tray import SentinelTray

    tray = SentinelTray(
        on_show=lambda: None,
        on_hide=lambda: None,
    )
    # Should not raise
    tray.notify("Title", "Message")


def test_stop_is_noop_without_icon():
    from gui.tray import SentinelTray

    tray = SentinelTray(
        on_show=lambda: None,
        on_hide=lambda: None,
    )
    # Should not raise
    tray.stop()
