"""Tests for gui.tray — pure function tests (no pystray/Tkinter required)."""

import importlib
import types
from unittest.mock import MagicMock, patch


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


# ---------------------------------------------------------------------------
# Icon generation + active-icon code paths (require _HAS_TRAY + a fake pystray)
# ---------------------------------------------------------------------------
def test_make_icon_image_returns_64px_rgba():
    import gui.tray as tray_mod

    if not tray_mod._HAS_TRAY:
        return  # PIL/pystray unavailable — nothing to test
    img = tray_mod._make_icon_image()
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def _fake_pystray():
    """Build a fake pystray module with Menu/MenuItem/Icon stand-ins."""
    fake = types.ModuleType("pystray")
    fake.MenuItem = MagicMock(name="MenuItem")
    fake.Menu = MagicMock(name="Menu")
    fake.Menu.SEPARATOR = object()
    fake.Icon = MagicMock(name="Icon")
    return fake


def test_run_starts_thread_and_returns_true():
    import gui.tray as tray_mod
    from gui.tray import SentinelTray

    fake = _fake_pystray()
    icon_instance = MagicMock()
    fake.Icon.return_value = icon_instance

    on_quit = MagicMock()
    on_stop = MagicMock()
    tray = SentinelTray(
        on_show=MagicMock(),
        on_hide=MagicMock(),
        on_stop_agent=on_stop,
        on_quit=on_quit,
    )
    with (
        patch.object(tray_mod, "_HAS_TRAY", True),
        patch.object(tray_mod, "pystray", fake, create=True),
    ):
        assert tray.run() is True
        if tray._thread is not None:
            tray._thread.join(timeout=2)

    # The background runner invoked the icon's blocking run()
    icon_instance.run.assert_called_once()

    # Exercise the menu-item callbacks captured by the fake MenuItem.
    callbacks = [call.args[1] for call in fake.MenuItem.call_args_list if len(call.args) > 1]
    for cb in callbacks:
        cb(icon_instance, None)
    tray._on_show.assert_called()
    tray._on_hide.assert_called()
    on_stop.assert_called()
    on_quit.assert_called()
    # _quit() also stops the icon
    assert icon_instance.stop.called


def test_run_returns_false_when_tray_unavailable():
    import gui.tray as tray_mod
    from gui.tray import SentinelTray

    tray = SentinelTray(on_show=lambda: None, on_hide=lambda: None)
    with patch.object(tray_mod, "_HAS_TRAY", False):
        assert tray.run() is False


def test_runner_swallows_run_errors():
    import gui.tray as tray_mod
    from gui.tray import SentinelTray

    fake = _fake_pystray()
    icon_instance = MagicMock()
    icon_instance.run.side_effect = RuntimeError("boom")
    fake.Icon.return_value = icon_instance

    tray = SentinelTray(on_show=MagicMock(), on_hide=MagicMock())
    with (
        patch.object(tray_mod, "_HAS_TRAY", True),
        patch.object(tray_mod, "pystray", fake, create=True),
    ):
        assert tray.run() is True
        if tray._thread is not None:
            tray._thread.join(timeout=2)  # should not raise despite run() error


def test_notify_with_icon_calls_through():
    from gui.tray import SentinelTray

    tray = SentinelTray(on_show=lambda: None, on_hide=lambda: None)
    tray._icon = MagicMock()
    tray.notify("Title", "Message")
    tray._icon.notify.assert_called_once_with("Message", title="Title")


def test_notify_swallows_errors():
    from gui.tray import SentinelTray

    tray = SentinelTray(on_show=lambda: None, on_hide=lambda: None)
    tray._icon = MagicMock()
    tray._icon.notify.side_effect = OSError("nope")
    tray.notify("T", "M")  # should not raise


def test_stop_with_icon_clears_reference():
    from gui.tray import SentinelTray

    tray = SentinelTray(on_show=lambda: None, on_hide=lambda: None)
    icon = MagicMock()
    tray._icon = icon
    tray.stop()
    icon.stop.assert_called_once()
    assert tray._icon is None


def test_stop_swallows_errors():
    from gui.tray import SentinelTray

    tray = SentinelTray(on_show=lambda: None, on_hide=lambda: None)
    icon = MagicMock()
    icon.stop.side_effect = RuntimeError("fail")
    tray._icon = icon
    tray.stop()  # should not raise
    assert tray._icon is None


def test_quit_callback_without_on_quit_still_stops_icon():
    """_quit with on_quit=None skips the callback but still calls icon.stop (line 89 False branch)."""
    import gui.tray as tray_mod
    from gui.tray import SentinelTray

    fake = _fake_pystray()
    icon_instance = MagicMock()
    fake.Icon.return_value = icon_instance

    # SentinelTray with no on_quit — _quit should still call icon.stop()
    tray = SentinelTray(on_show=MagicMock(), on_hide=MagicMock(), on_quit=None)
    with (
        patch.object(tray_mod, "_HAS_TRAY", True),
        patch.object(tray_mod, "pystray", fake, create=True),
    ):
        assert tray.run() is True
        if tray._thread is not None:
            tray._thread.join(timeout=2)

    # Find the _quit MenuItem callback (4th item, index 3 in the menu)
    quit_callbacks = [
        call.args[1]
        for call in fake.MenuItem.call_args_list
        if len(call.args) > 1 and callable(call.args[1])
    ]
    # Exercise all menu callbacks to hit _quit with on_quit=None
    for cb in quit_callbacks:
        cb(icon_instance, None)
    # icon.stop must have been called (from the finally: block in _quit)
    assert icon_instance.stop.called
