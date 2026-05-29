"""Tests for gui.system_tray.SystemTrayIcon and icon-generation helpers.

`pystray` is stubbed as an empty module by conftest, so tests that exercise
start()/_build_menu() inject a fake pystray providing Icon/Menu/MenuItem.
PIL is real, so _create_icon_image runs for real.
"""

from __future__ import annotations

import importlib
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import gui.system_tray as st
from gui.system_tray import SystemTrayIcon, _create_icon_image


def _fake_pystray():
    fake = types.ModuleType("pystray")
    fake.MenuItem = MagicMock(name="MenuItem")
    fake.Menu = MagicMock(name="Menu")
    fake.Menu.SEPARATOR = object()
    fake.Icon = MagicMock(name="Icon")
    return fake


# ---------------------------------------------------------------------------
# Optional-dependency import guards (module-level fallback branches)
# ---------------------------------------------------------------------------
def test_module_degrades_without_optional_deps():
    """Reloading with pystray/PIL absent exercises the ImportError fallbacks."""
    try:
        with patch.dict("sys.modules", {"pystray": None, "PIL": None}):
            reloaded = importlib.reload(st)
            assert reloaded._HAS_PYSTRAY is False
            assert reloaded._HAS_PIL is False
            assert reloaded.is_available() is False
    finally:
        # Restore real module state OUTSIDE the patch so deps import normally.
        importlib.reload(st)


# ---------------------------------------------------------------------------
# _create_icon_image
# ---------------------------------------------------------------------------
class TestCreateIconImage:
    @pytest.mark.parametrize("status", list(st._STATUS_COLOURS) + ["unknown_status"])
    def test_returns_64px_rgba(self, status):
        if not st._HAS_PIL:
            pytest.skip("PIL not installed")
        img = _create_icon_image(status)
        assert img.size == (st._ICON_SIZE, st._ICON_SIZE)
        assert img.mode == "RGBA"

    def test_raises_without_pil(self):
        with patch.object(st, "_HAS_PIL", False):
            with pytest.raises(RuntimeError):
                _create_icon_image("idle")


# ---------------------------------------------------------------------------
# Construction + simple accessors
# ---------------------------------------------------------------------------
class TestBasics:
    def test_init(self):
        app = MagicMock()
        tray = SystemTrayIcon(app)
        assert tray._app is app
        assert tray._icon is None
        assert tray._current_status == "idle"
        assert tray.is_running is False

    def test_is_running_reflects_event(self):
        tray = SystemTrayIcon(MagicMock())
        tray._running.set()
        assert tray.is_running is True
        tray._running.clear()
        assert tray.is_running is False


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------
class TestStart:
    def test_returns_false_when_unavailable(self):
        tray = SystemTrayIcon(MagicMock())
        with patch.object(st, "_AVAILABLE", False):
            assert tray.start() is False

    def test_returns_true_when_already_running(self):
        tray = SystemTrayIcon(MagicMock())
        tray._icon = MagicMock()
        with patch.object(st, "_AVAILABLE", True):
            assert tray.start() is True

    def test_returns_false_when_icon_image_fails(self):
        tray = SystemTrayIcon(MagicMock())
        with (
            patch.object(st, "_AVAILABLE", True),
            patch.object(st, "_create_icon_image", side_effect=OSError("boom")),
        ):
            assert tray.start() is False

    def test_happy_path_starts_thread(self):
        tray = SystemTrayIcon(MagicMock())
        fake = _fake_pystray()
        icon_instance = MagicMock()
        fake.Icon.return_value = icon_instance
        with (
            patch.object(st, "_AVAILABLE", True),
            patch.object(st, "pystray", fake, create=True),
        ):
            assert tray.start() is True
            if tray._thread is not None:
                tray._thread.join(timeout=2)
        icon_instance.run.assert_called_once()

    def test_runner_swallows_loop_errors(self):
        tray = SystemTrayIcon(MagicMock())
        fake = _fake_pystray()
        icon_instance = MagicMock()
        icon_instance.run.side_effect = RuntimeError("loop dead")
        fake.Icon.return_value = icon_instance
        with (
            patch.object(st, "_AVAILABLE", True),
            patch.object(st, "pystray", fake, create=True),
        ):
            assert tray.start() is True
            if tray._thread is not None:
                tray._thread.join(timeout=2)
        assert tray.is_running is False


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------
class TestStop:
    def test_noop_when_no_icon(self):
        tray = SystemTrayIcon(MagicMock())
        tray.stop()  # must not raise

    def test_stops_icon_and_joins_thread(self):
        tray = SystemTrayIcon(MagicMock())
        icon = MagicMock()
        tray._icon = icon
        thread = MagicMock()
        thread.is_alive.return_value = True
        tray._thread = thread
        tray.stop()
        icon.stop.assert_called_once()
        thread.join.assert_called_once()
        assert tray._icon is None

    def test_swallows_stop_errors(self):
        tray = SystemTrayIcon(MagicMock())
        icon = MagicMock()
        icon.stop.side_effect = RuntimeError("nope")
        tray._icon = icon
        tray.stop()  # must not raise
        assert tray._icon is None


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------
class TestUpdateStatus:
    def test_ignores_invalid_status(self):
        tray = SystemTrayIcon(MagicMock())
        tray.update_status("bogus")
        assert tray._current_status == "idle"

    def test_sets_status_without_icon(self):
        tray = SystemTrayIcon(MagicMock())
        with patch.object(st, "_AVAILABLE", True):
            tray.update_status("running")
        assert tray._current_status == "running"

    def test_updates_icon_image_and_title(self):
        tray = SystemTrayIcon(MagicMock())
        icon = MagicMock()
        tray._icon = icon
        with patch.object(st, "_AVAILABLE", True):
            tray.update_status("recording")
        assert tray._current_status == "recording"
        assert icon.icon is not None
        assert "Recording" in icon.title
        icon.update_menu.assert_called_once()

    def test_swallows_update_errors(self):
        tray = SystemTrayIcon(MagicMock())
        tray._icon = MagicMock()
        with (
            patch.object(st, "_AVAILABLE", True),
            patch.object(st, "_create_icon_image", side_effect=ValueError("bad")),
        ):
            tray.update_status("error")  # must not raise

    def test_updates_icon_without_update_menu(self):
        """Icon without update_menu attribute takes the hasattr False branch (line 250)."""
        tray = SystemTrayIcon(MagicMock())
        # Create a mock icon that does NOT have update_menu
        icon = MagicMock(spec=["icon", "title"])
        tray._icon = icon
        with patch.object(st, "_AVAILABLE", True):
            tray.update_status("running")
        assert tray._current_status == "running"
        assert icon.icon is not None
        # update_menu was not called (it doesn't exist on the spec)
        assert not hasattr(icon, "update_menu")


# ---------------------------------------------------------------------------
# show_notification
# ---------------------------------------------------------------------------
class TestNotification:
    def test_noop_without_icon(self):
        tray = SystemTrayIcon(MagicMock())
        tray.show_notification("t", "m")  # must not raise

    def test_calls_notify(self):
        tray = SystemTrayIcon(MagicMock())
        tray._icon = MagicMock()
        tray.show_notification("Title", "Body")
        tray._icon.notify.assert_called_once_with("Body", title="Title")

    def test_swallows_notify_errors(self):
        tray = SystemTrayIcon(MagicMock())
        tray._icon = MagicMock()
        tray._icon.notify.side_effect = OSError("fail")
        tray.show_notification("t", "m")  # must not raise


# ---------------------------------------------------------------------------
# _build_menu
# ---------------------------------------------------------------------------
class TestBuildMenu:
    def test_build_menu_and_invoke_callbacks(self):
        tray = SystemTrayIcon(MagicMock())
        fake = _fake_pystray()
        with patch.object(st, "pystray", fake, create=True):
            menu = tray._build_menu()
            assert menu is fake.Menu.return_value
            # Invoke every callable passed to MenuItem to cover the lambdas.
            for call in fake.MenuItem.call_args_list:
                for arg in call.args:
                    if callable(arg):
                        for attempt in ((None, None), (None,), ()):
                            try:
                                arg(*attempt)
                                break
                            except TypeError:
                                continue


# ---------------------------------------------------------------------------
# Menu callbacks
# ---------------------------------------------------------------------------
class TestCallbacks:
    def test_on_new_task(self):
        tray = SystemTrayIcon(MagicMock())
        with patch.object(tray, "_invoke_on_app") as inv:
            tray._on_new_task(None, None)
        inv.assert_called_once_with("_tray_new_task")

    def test_on_record(self):
        tray = SystemTrayIcon(MagicMock())
        with patch.object(tray, "_invoke_on_app") as inv:
            tray._on_record(None, None)
        inv.assert_called_once_with("_tray_toggle_record")

    def test_on_run_last_script(self):
        tray = SystemTrayIcon(MagicMock())
        with patch.object(tray, "_invoke_on_app") as inv:
            tray._on_run_last_script(None, None)
        inv.assert_called_once_with("_tray_run_last_script")

    def test_show_window(self):
        tray = SystemTrayIcon(MagicMock())
        with patch.object(tray, "_invoke_on_app") as inv:
            tray._show_window()
        inv.assert_called_once_with("_tray_show_window")

    def test_on_exit(self):
        tray = SystemTrayIcon(MagicMock())
        with patch.object(tray, "_invoke_on_app") as inv:
            tray._on_exit(None, None)
        inv.assert_called_once_with("_tray_quit")

    def test_run_it_script_missing_file(self):
        tray = SystemTrayIcon(MagicMock())
        with (
            patch.object(tray, "_invoke_on_app") as inv,
            patch.object(tray, "show_notification") as notify,
        ):
            tray._run_it_script(Path("/no/such/script_xyz.json"))
        inv.assert_not_called()
        notify.assert_called_once()

    def test_run_it_script_existing_file(self, tmp_path):
        script = tmp_path / "real_script.json"
        script.write_text("{}")
        tray = SystemTrayIcon(MagicMock())
        with patch.object(tray, "_invoke_on_app") as inv:
            tray._run_it_script(script)
        inv.assert_called_once_with("_tray_run_script", str(script))


# ---------------------------------------------------------------------------
# _invoke_on_app
# ---------------------------------------------------------------------------
class TestInvokeOnApp:
    def test_noop_when_app_none(self):
        tray = SystemTrayIcon(None)
        tray._invoke_on_app("anything")  # must not raise

    def test_noop_when_method_missing(self):
        app = MagicMock(spec=[])  # no attributes at all
        app.root = MagicMock()
        tray = SystemTrayIcon(app)
        tray._invoke_on_app("_tray_nonexistent")
        app.root.after.assert_not_called()

    def test_schedules_and_runs_method(self):
        app = MagicMock()
        # after() runs the scheduled callback immediately.
        app.root.after.side_effect = lambda delay, cb: cb()
        tray = SystemTrayIcon(app)
        tray._invoke_on_app("_tray_run_script", "arg1")
        app._tray_run_script.assert_called_once_with("arg1")

    def test_swallows_runtime_error_from_after(self):
        app = MagicMock()
        app.root.after.side_effect = RuntimeError("root destroyed")
        tray = SystemTrayIcon(app)
        tray._invoke_on_app("_tray_show_window")  # must not raise
