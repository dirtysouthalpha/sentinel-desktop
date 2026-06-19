"""v20 cross-platform parity tests.

Verifies that window_manager and stealth_input correctly route through the
Linux platform backend when win32 is unavailable.  All backend calls are
mocked so these tests run on any OS without xdotool or a display.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core import stealth_input, window_manager
from core.platform.linux_backend import WindowInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wi(title="App", x=0, y=0, w=800, h=600, focused=False, handle=1):
    return WindowInfo(title=title, x=x, y=y, width=w, height=h, is_focused=focused, handle=handle)


def _make_backend(window_backend=None, input_backend=None):
    """Build a minimal fake backend object."""
    wb = window_backend or MagicMock()
    ib = input_backend or MagicMock()
    backend = SimpleNamespace(window=wb, input=ib)
    return backend


# ---------------------------------------------------------------------------
# window_manager — _window_info_to_dict
# ---------------------------------------------------------------------------


def test_window_info_to_dict_fields():
    wi = _make_wi("Notepad", x=10, y=20, w=640, h=480, focused=True, handle=42)
    d = window_manager._window_info_to_dict(wi)
    assert d["title"] == "Notepad"
    assert d["x"] == 10
    assert d["y"] == 20
    assert d["width"] == 640
    assert d["height"] == 480
    assert d["is_focused"] is True
    assert d["hwnd"] == 42


def test_window_info_to_dict_none_title():
    wi = _make_wi(title=None)
    d = window_manager._window_info_to_dict(wi)
    assert d["title"] == ""


# ---------------------------------------------------------------------------
# window_manager.list_windows — Linux path
# ---------------------------------------------------------------------------


@patch.object(window_manager, "HAS_WIN32", False)
@patch.object(window_manager, "HAS_PGW", False)
@patch("core.window_manager.is_linux", return_value=True)
@patch("core.window_manager.is_macos", return_value=False)
@patch("core.window_manager.get_backend")
def test_list_windows_linux(mock_gb, _ml, _mm):
    wi = _make_wi("Terminal", x=5, y=10, w=1024, h=768, focused=True, handle=99)
    mock_gb.return_value = _make_backend(window_backend=MagicMock(list_windows=lambda: [wi]))
    result = window_manager.list_windows()
    assert len(result) == 1
    assert result[0]["title"] == "Terminal"
    assert result[0]["hwnd"] == 99


@patch.object(window_manager, "HAS_WIN32", False)
@patch.object(window_manager, "HAS_PGW", False)
@patch("core.window_manager.is_linux", return_value=True)
@patch("core.window_manager.is_macos", return_value=False)
@patch("core.window_manager.get_backend")
def test_list_windows_linux_backend_error(mock_gb, _ml, _mm):
    mock_gb.return_value = _make_backend(
        window_backend=MagicMock(list_windows=MagicMock(side_effect=RuntimeError("xdotool gone")))
    )
    result = window_manager.list_windows()
    assert result == []


# ---------------------------------------------------------------------------
# window_manager.focus_window — Linux path
# ---------------------------------------------------------------------------


@patch.object(window_manager, "HAS_WIN32", False)
@patch.object(window_manager, "HAS_PGW", False)
@patch("core.window_manager.is_linux", return_value=True)
@patch("core.window_manager.is_macos", return_value=False)
@patch("core.window_manager.get_backend")
def test_focus_window_linux(mock_gb, _ml, _mm):
    wb = MagicMock()
    wb.focus_window.return_value = True
    mock_gb.return_value = _make_backend(window_backend=wb)
    assert window_manager.focus_window("Terminal") is True
    wb.focus_window.assert_called_once_with("Terminal")


@patch.object(window_manager, "HAS_WIN32", False)
@patch.object(window_manager, "HAS_PGW", False)
@patch("core.window_manager.is_linux", return_value=True)
@patch("core.window_manager.is_macos", return_value=False)
@patch("core.window_manager.get_backend")
def test_focus_window_linux_error(mock_gb, _ml, _mm):
    wb = MagicMock()
    wb.focus_window.side_effect = OSError("no display")
    mock_gb.return_value = _make_backend(window_backend=wb)
    assert window_manager.focus_window("Terminal") is False


# ---------------------------------------------------------------------------
# window_manager.close_window — Linux path
# ---------------------------------------------------------------------------


@patch.object(window_manager, "HAS_WIN32", False)
@patch.object(window_manager, "HAS_PGW", False)
@patch("core.window_manager.is_linux", return_value=True)
@patch("core.window_manager.is_macos", return_value=False)
@patch("core.window_manager.get_backend")
def test_close_window_linux(mock_gb, _ml, _mm):
    wb = MagicMock()
    wb.close_window.return_value = True
    mock_gb.return_value = _make_backend(window_backend=wb)
    assert window_manager.close_window("Editor") is True
    wb.close_window.assert_called_once_with("Editor")


# ---------------------------------------------------------------------------
# window_manager.get_focused_window_rect — Linux path
# ---------------------------------------------------------------------------


@patch.object(window_manager, "HAS_WIN32", False)
@patch.object(window_manager, "HAS_PGW", False)
@patch("core.window_manager.is_linux", return_value=True)
@patch("core.window_manager.is_macos", return_value=False)
@patch("core.window_manager.get_backend")
def test_get_focused_window_rect_linux(mock_gb, _ml, _mm):
    wb = MagicMock()
    wb.get_focused_window_rect.return_value = (10, 20, 800, 600)
    mock_gb.return_value = _make_backend(window_backend=wb)
    assert window_manager.get_focused_window_rect() == (10, 20, 800, 600)


@patch.object(window_manager, "HAS_WIN32", False)
@patch.object(window_manager, "HAS_PGW", False)
@patch("core.window_manager.is_linux", return_value=True)
@patch("core.window_manager.is_macos", return_value=False)
@patch("core.window_manager.get_backend")
def test_get_focused_window_rect_linux_error(mock_gb, _ml, _mm):
    wb = MagicMock()
    wb.get_focused_window_rect.side_effect = RuntimeError("no display")
    mock_gb.return_value = _make_backend(window_backend=wb)
    assert window_manager.get_focused_window_rect() is None


# ---------------------------------------------------------------------------
# stealth_input.is_available — Linux xdotool check
# ---------------------------------------------------------------------------


def test_is_available_linux_with_xdotool(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "is_linux", lambda: True)
    with patch("shutil.which", return_value="/usr/bin/xdotool"):
        assert stealth_input.is_available() is True


def test_is_available_linux_without_xdotool(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "is_linux", lambda: True)
    with patch("shutil.which", return_value=None):
        assert stealth_input.is_available() is False


def test_is_available_win32_takes_priority(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", True)
    assert stealth_input.is_available() is True


# ---------------------------------------------------------------------------
# stealth_input.post_click — Linux path
# ---------------------------------------------------------------------------


def test_post_click_linux_routes_to_backend(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "is_linux", lambda: True)
    monkeypatch.setattr(stealth_input, "is_macos", lambda: False)

    ib = MagicMock()
    ib.click.return_value = True
    backend = SimpleNamespace(input=ib)
    monkeypatch.setattr(stealth_input, "get_backend", lambda: backend)

    assert stealth_input.post_click(100, 200) is True
    ib.click.assert_called_once_with(100, 200, button="left", clicks=1)


def test_post_click_linux_backend_error_returns_false(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "is_linux", lambda: True)
    monkeypatch.setattr(stealth_input, "is_macos", lambda: False)

    ib = MagicMock()
    ib.click.side_effect = OSError("no display")
    backend = SimpleNamespace(input=ib)
    monkeypatch.setattr(stealth_input, "get_backend", lambda: backend)

    assert stealth_input.post_click(100, 200) is False


def test_post_click_not_linux_not_win32_returns_false(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "is_linux", lambda: False)
    monkeypatch.setattr(stealth_input, "is_macos", lambda: False)
    assert stealth_input.post_click(0, 0) is False


# ---------------------------------------------------------------------------
# stealth_input.post_text — Linux path
# ---------------------------------------------------------------------------


def test_post_text_linux_routes_to_backend(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "is_linux", lambda: True)
    monkeypatch.setattr(stealth_input, "is_macos", lambda: False)

    ib = MagicMock()
    ib.type_text.return_value = True
    backend = SimpleNamespace(input=ib)
    monkeypatch.setattr(stealth_input, "get_backend", lambda: backend)

    assert stealth_input.post_text("hello") is True
    ib.type_text.assert_called_once_with("hello")


def test_post_text_linux_empty_string_returns_false(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "is_linux", lambda: True)
    monkeypatch.setattr(stealth_input, "is_macos", lambda: False)
    assert stealth_input.post_text("") is False


def test_post_text_linux_backend_error_returns_false(monkeypatch):
    monkeypatch.setattr(stealth_input, "_HAS_WIN32", False)
    monkeypatch.setattr(stealth_input, "is_linux", lambda: True)
    monkeypatch.setattr(stealth_input, "is_macos", lambda: False)

    ib = MagicMock()
    ib.type_text.side_effect = RuntimeError("xdotool not found")
    backend = SimpleNamespace(input=ib)
    monkeypatch.setattr(stealth_input, "get_backend", lambda: backend)

    assert stealth_input.post_text("hello") is False
