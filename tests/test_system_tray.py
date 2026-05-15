"""Tests for gui.system_tray — pure function tests (no pystray/PIL required)."""

from gui.system_tray import _STATUS_COLOURS, is_available


def test_is_available_returns_bool():
    assert isinstance(is_available(), bool)


def test_valid_statuses_match_colour_keys():
    from gui.system_tray import SystemTrayIcon

    assert SystemTrayIcon.VALID_STATUSES == frozenset(_STATUS_COLOURS.keys())


def test_expected_statuses_exist():
    from gui.system_tray import SystemTrayIcon

    expected = {"idle", "running", "recording", "warning", "error", "paused"}
    assert expected == SystemTrayIcon.VALID_STATUSES


def test_status_colours_are_rgb_tuples():
    for status, colour in _STATUS_COLOURS.items():
        assert len(colour) == 3, f"{status}: expected 3-tuple, got {colour}"
        assert all(0 <= c <= 255 for c in colour), f"{status}: out of range"


def test_system_tray_icon_noop_without_deps():
    from gui.system_tray import SystemTrayIcon

    if is_available():
        return  # Can't test no-op path when deps are installed

    icon = SystemTrayIcon(app=None)
    assert icon.start() is False
    assert not icon.is_running
    icon.update_status("running")  # should not raise
    icon.show_notification("t", "m")  # should not raise
    icon.stop()  # should not raise
