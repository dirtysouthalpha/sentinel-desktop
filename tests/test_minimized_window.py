"""Regression: minimized-window detection + restore-before-capture path."""

from core import window_manager as wm


def test_looks_minimized_detects_off_screen_rect():
    # Windows parks minimized windows at (-32000, -32000).
    assert wm._looks_minimized((-32000, -32000, 100, 100))
    assert wm._looks_minimized((-32001, 0, 100, 100))
    assert wm._looks_minimized((0, -32000, 100, 100))


def test_looks_minimized_detects_zero_size():
    assert wm._looks_minimized((100, 100, 0, 100))
    assert wm._looks_minimized((100, 100, 100, 0))
    assert wm._looks_minimized((100, 100, -5, 100))


def test_looks_minimized_accepts_normal_rect():
    assert not wm._looks_minimized((0, 0, 1920, 1080))
    assert not wm._looks_minimized((100, 50, 800, 600))


def test_get_window_rect_uses_list_windows(monkeypatch):
    """get_window_rect must reuse the same enumeration list_windows uses."""
    fake = [
        {
            "title": "OpenSwarm - Google Chrome",
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "is_focused": False,
            "hwnd": 1,
        },
        {
            "title": "Mail - Jane Doe - Outlook",
            "x": 100,
            "y": 100,
            "width": 1800,
            "height": 1000,
            "is_focused": False,
            "hwnd": 2,
        },
    ]
    monkeypatch.setattr(wm, "list_windows", lambda: fake)
    # Partial match should win.
    r = wm.get_window_rect("Outlook")
    assert r == (100, 100, 1800, 1000)


def test_get_window_rect_triggers_restore_for_minimized(monkeypatch):
    restored = []

    fake = [
        {
            "title": "Outlook - Inbox",
            "x": -32000,
            "y": -32000,
            "width": 160,
            "height": 28,
            "is_focused": False,
            "hwnd": 42,
        },
    ]
    # After restore, the window comes back to a real rect.
    state = {"first": True}

    def fake_list():
        if state["first"]:
            state["first"] = False
            return fake
        return [
            {
                "title": "Outlook - Inbox",
                "x": 100,
                "y": 100,
                "width": 1800,
                "height": 1000,
                "is_focused": True,
                "hwnd": 42,
            }
        ]

    def fake_restore(hwnd):
        restored.append(hwnd)
        return True

    monkeypatch.setattr(wm, "list_windows", fake_list)
    monkeypatch.setattr(wm, "restore_window_hwnd", fake_restore)

    r = wm.get_window_rect("Outlook")
    assert restored == [42], "minimized window should have been restored"
    # And the returned rect is the post-restore one.
    assert r == (100, 100, 1800, 1000)
