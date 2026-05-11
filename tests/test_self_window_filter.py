"""Regression: read_text(focused) must not OCR the Sentinel Desktop GUI itself."""
import pytest

from core import window_manager as wm


def test_is_self_window_recognises_sentinel():
    assert wm._is_self_window("Sentinel Desktop v2")
    assert wm._is_self_window("Sentinel Desktop - 1.0")
    assert not wm._is_self_window("Mail - Brandon Goolsby - Outlook")
    assert not wm._is_self_window("")
    assert not wm._is_self_window("Notepad")


def test_get_target_window_skips_self_via_fallback(monkeypatch):
    """When the focused window is Sentinel's GUI, target picker should fall
    back to the next visible non-self window."""
    fake_windows = [
        {"title": "Sentinel Desktop v2", "x": 0, "y": 0,
         "width": 1200, "height": 800, "is_focused": False},
        {"title": "Mail - Brandon - Outlook", "x": 100, "y": 100,
         "width": 1800, "height": 1000, "is_focused": False},
        {"title": "Chrome - Some Tab", "x": 200, "y": 0,
         "width": 1600, "height": 900, "is_focused": False},
    ]
    monkeypatch.setattr(wm, "list_windows", lambda: fake_windows)
    # Pretend the focused window is Sentinel's own GUI.
    monkeypatch.setattr(wm, "HAS_WIN32", False)
    monkeypatch.setattr(wm, "HAS_PGW", False)

    result = wm.get_target_window_rect()
    assert result is not None
    _, _, _, _, title = result
    assert "Sentinel" not in title, "target picker still returned self"
    # The wider Outlook window should win the tie-break (largest width).
    assert "Outlook" in title


def test_get_target_window_returns_none_when_only_self_visible(monkeypatch):
    monkeypatch.setattr(wm, "list_windows", lambda: [
        {"title": "Sentinel Desktop v2", "x": 0, "y": 0,
         "width": 1200, "height": 800, "is_focused": True},
    ])
    monkeypatch.setattr(wm, "HAS_WIN32", False)
    monkeypatch.setattr(wm, "HAS_PGW", False)
    assert wm.get_target_window_rect() is None
