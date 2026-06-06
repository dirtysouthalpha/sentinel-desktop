"""
Tests for gui/overlay.py — Action overlay utility functions.

Tests the pure helper functions: _coords_from_action, _label_for_action,
_color_for_kind. GUI class tests are not included (require tkinter runtime).
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import gui.overlay as overlay_mod
from gui.overlay import (
    ActionOverlay,
    _color_for_kind,
    _coords_from_action,
    _Indicator,
    _label_for_action,
    _make_clickthrough,
)


def _patched_tk():
    """A throwaway ``tkinter`` module exposing a *real* TclError.

    Except-branch tests patch ``overlay_mod.tk`` with this so they remain
    correct regardless of test ordering — another test module rebinds
    ``sys.modules['tkinter']`` to a MagicMock at import time, whose
    ``TclError`` is not a real exception and so is never caught.
    """
    mod = types.ModuleType("tkinter")
    mod.TclError = type("TclError", (Exception,), {})
    return mod


# ── Tests: _coords_from_action ────────────────────────────────────────────


class TestCoordsFromAction:
    """Tests for gui.overlay._coords_from_action."""

    def test_extracts_x_y(self):
        result = _coords_from_action({"x": 100, "y": 200})
        assert result == (100, 200)

    def test_extracts_float_x_y_converts_to_int(self):
        result = _coords_from_action({"x": 10.5, "y": 20.7})
        assert result == (10, 20)

    def test_extracts_from_position_list(self):
        result = _coords_from_action({"position": [300, 400]})
        assert result == (300, 400)

    def test_extracts_from_position_tuple(self):
        result = _coords_from_action({"position": (500, 600)})
        assert result == (500, 600)

    def test_returns_none_when_no_coords(self):
        result = _coords_from_action({"action": "scroll"})
        assert result is None

    def test_returns_none_on_empty_dict(self):
        result = _coords_from_action({})
        assert result is None

    def test_returns_none_on_non_numeric_x(self):
        result = _coords_from_action({"x": "abc", "y": 100})
        assert result is None

    def test_returns_none_on_non_numeric_y(self):
        result = _coords_from_action({"x": 100, "y": None})
        assert result is None

    def test_returns_none_on_position_too_short(self):
        result = _coords_from_action({"position": [100]})
        assert result is None

    def test_returns_none_on_position_non_numeric(self):
        result = _coords_from_action({"position": ["a", "b"]})
        assert result is None

    def test_prefers_x_y_over_position(self):
        result = _coords_from_action({"x": 10, "y": 20, "position": [30, 40]})
        assert result == (10, 20)

    def test_position_with_extra_elements(self):
        result = _coords_from_action({"position": [100, 200, 300]})
        assert result == (100, 200)

    def test_zero_coords_valid(self):
        result = _coords_from_action({"x": 0, "y": 0})
        assert result == (0, 0)

    def test_negative_coords_valid(self):
        result = _coords_from_action({"x": -10, "y": -20})
        assert result == (-10, -20)


# ── Tests: _label_for_action ──────────────────────────────────────────────


class TestLabelForAction:
    """Tests for gui.overlay._label_for_action."""

    def test_click_action(self):
        label = _label_for_action({"action": "click", "x": 50, "y": 100})
        assert label == "click (50, 100)"

    def test_click_text_action(self):
        label = _label_for_action({"action": "click_text", "text": "Submit"})
        assert "Submit" in label

    def test_click_text_truncated(self):
        long_text = "A" * 100
        label = _label_for_action({"action": "click_text", "text": long_text})
        # Should be truncated to 40 chars
        assert len(label.split(": ", 1)[1]) <= 40

    def test_click_control_action(self):
        label = _label_for_action({"action": "click_control", "name": "OK Button"})
        assert "OK Button" in label

    def test_type_text_action(self):
        label = _label_for_action({"action": "type_text", "text": "hello world"})
        assert "hello world" in label

    def test_set_text_action(self):
        label = _label_for_action({"action": "set_text", "name": "username"})
        assert "username" in label

    def test_hotkey_action(self):
        label = _label_for_action({"action": "hotkey", "keys": ["ctrl", "c"]})
        assert "ctrl+c" in label

    def test_press_key_action(self):
        label = _label_for_action({"action": "press_key", "key": "Enter"})
        assert "Enter" in label

    def test_scroll_action(self):
        label = _label_for_action({"action": "scroll", "amount": 3})
        assert "3" in label

    def test_unknown_action_name(self):
        label = _label_for_action({"action": "custom_action"})
        assert label == "custom_action"

    def test_empty_action_key(self):
        label = _label_for_action({})
        assert label == "action"

    def test_hotkey_no_keys(self):
        label = _label_for_action({"action": "hotkey"})
        assert "hotkey" in label

    def test_click_text_missing_text(self):
        label = _label_for_action({"action": "click_text"})
        assert "click text" in label


# ── Tests: _color_for_kind ────────────────────────────────────────────────


class TestColorForKind:
    """Tests for gui.overlay._color_for_kind."""

    def test_click_text_is_green(self):
        assert _color_for_kind("click_text") == "#95E400"

    def test_click_control_is_green(self):
        assert _color_for_kind("click_control") == "#95E400"

    def test_type_text_is_cyan(self):
        assert _color_for_kind("type_text") == "#00F0FF"

    def test_set_text_is_cyan(self):
        assert _color_for_kind("set_text") == "#00F0FF"

    def test_hotkey_is_amber(self):
        assert _color_for_kind("hotkey") == "#FBBC00"

    def test_press_key_is_amber(self):
        assert _color_for_kind("press_key") == "#FBBC00"

    def test_default_is_orange(self):
        assert _color_for_kind("click") == "#e8793a"

    def test_unknown_is_orange(self):
        assert _color_for_kind("something_else") == "#e8793a"

    def test_empty_string_is_orange(self):
        assert _color_for_kind("") == "#e8793a"


# ── Tests: ActionOverlay (class) ──────────────────────────────────────────


class TestActionOverlay:
    def test_show_action_schedules_on_main_thread(self):
        master = MagicMock()
        ov = ActionOverlay(master)
        ov.show_action({"action": "click", "x": 10, "y": 20})
        master.after.assert_called_once()
        # First positional arg is delay (0), second is the bound _show_main.
        assert master.after.call_args.args[0] == 0

    def test_show_action_ignores_actions_without_coords(self):
        master = MagicMock()
        ov = ActionOverlay(master)
        ov.show_action({"action": "scroll"})
        master.after.assert_not_called()

    def test_show_action_swallows_schedule_errors(self):
        fake = _patched_tk()
        master = MagicMock()
        master.after.side_effect = fake.TclError("dead")
        ov = ActionOverlay(master)
        with patch.object(overlay_mod, "tk", fake):
            ov.show_action({"action": "click", "x": 1, "y": 2})  # must not raise

    def test_show_main_creates_indicator_and_schedules_dismiss(self):
        master = MagicMock()
        ov = ActionOverlay(master)
        with patch.object(overlay_mod, "_Indicator") as FakeInd:
            ov._show_main((5, 6), "click", "click")
        FakeInd.assert_called_once()
        assert ov._current is FakeInd.return_value
        # Schedules the auto-dismiss with _SHOW_MS.
        master.after.assert_called_once_with(overlay_mod._SHOW_MS, ov._dismiss)

    def test_show_main_destroys_previous_indicator(self):
        master = MagicMock()
        ov = ActionOverlay(master)
        previous = MagicMock()
        ov._current = previous
        with patch.object(overlay_mod, "_Indicator"):
            ov._show_main((5, 6), "label", "click")
        previous.destroy.assert_called_once()

    def test_show_main_swallows_draw_errors(self):
        fake = _patched_tk()
        master = MagicMock()
        ov = ActionOverlay(master)
        with (
            patch.object(overlay_mod, "tk", fake),
            patch.object(overlay_mod, "_Indicator", side_effect=fake.TclError("x")),
        ):
            ov._show_main((5, 6), "label", "click")  # must not raise

    def test_dismiss_destroys_and_clears_current(self):
        ov = ActionOverlay(MagicMock())
        ind = MagicMock()
        ov._current = ind
        ov._dismiss()
        ind.destroy.assert_called_once()
        assert ov._current is None

    def test_dismiss_swallows_destroy_errors(self):
        fake = _patched_tk()
        ov = ActionOverlay(MagicMock())
        ind = MagicMock()
        ind.destroy.side_effect = fake.TclError("boom")
        ov._current = ind
        with patch.object(overlay_mod, "tk", fake):
            ov._dismiss()  # must not raise
        assert ov._current is None

    def test_dismiss_noop_when_no_current(self):
        ov = ActionOverlay(MagicMock())
        ov._dismiss()  # nothing to destroy, must not raise
        assert ov._current is None


# ── Tests: _Indicator (class) ─────────────────────────────────────────────


class TestIndicator:
    def test_construct_with_label_draws_canvas(self):
        # Patch _make_clickthrough to avoid ctypes.windll recursion on Windows
        with patch.object(overlay_mod, "_make_clickthrough"):
            ind = _Indicator(MagicMock(), x=100, y=200, label="click (1, 2)", kind="click")
        assert ind.win is not None
        assert ind.canvas is not None
        ind.destroy()

    def test_construct_without_label(self):
        with patch.object(overlay_mod, "_make_clickthrough"):
            ind = _Indicator(MagicMock(), x=0, y=0, label="", kind="type_text")
        ind.destroy()

    def test_destroy_swallows_errors(self):
        fake = _patched_tk()
        with patch.object(overlay_mod, "_make_clickthrough"):
            ind = _Indicator(MagicMock(), x=10, y=10, label="x", kind="hotkey")
        ind.win = MagicMock()
        ind.win.destroy.side_effect = fake.TclError("gone")
        with patch.object(overlay_mod, "tk", fake):
            ind.destroy()  # must not raise

    def test_construct_when_transparency_unsupported(self):
        # Build a self-consistent fake tkinter with a real TclError. _Indicator
        # does a local ``import tkinter`` and its except uses the module-level
        # tk, so patch both sys.modules and overlay_mod.tk — this keeps the
        # test correct regardless of test ordering (another module rebinds
        # sys.modules['tkinter'] to a MagicMock at import time).
        fake = types.ModuleType("tkinter")
        fake.TclError = type("TclError", (Exception,), {})

        class _NoAlphaWin:
            def __init__(self, *a, **kw):
                pass

            def overrideredirect(self, *a, **kw):
                pass

            def attributes(self, *a, **kw):
                # -topmost succeeds; -alpha / -transparentcolor are unsupported.
                if a and a[0] in ("-alpha", "-transparentcolor"):
                    raise fake.TclError("unsupported")

            def geometry(self, *a, **kw):
                pass

            def winfo_id(self):
                return 0

            def destroy(self):
                pass

        class _Canvas:
            def __init__(self, *a, **kw):
                pass

            def pack(self, *a, **kw):
                pass

            def create_oval(self, *a, **kw):
                return 1

            def create_text(self, *a, **kw):
                return 2

            def create_rectangle(self, *a, **kw):
                return 3

        fake.Toplevel = _NoAlphaWin
        fake.Canvas = _Canvas

        with (
            patch.dict(sys.modules, {"tkinter": fake}),
            patch.object(overlay_mod, "tk", fake),
            patch.object(overlay_mod, "_make_clickthrough"),
        ):
            ind = _Indicator(MagicMock(), x=5, y=5, label="x", kind="click")
            ind.destroy()


# ── Tests: _make_clickthrough ─────────────────────────────────────────────


class TestMakeClickthrough:
    def test_noop_on_non_windows(self):
        with patch.object(sys, "platform", "linux"):
            _make_clickthrough(MagicMock())  # returns early, no raise

    def test_applies_extended_style_on_windows(self):
        fake_user32 = MagicMock()
        fake_user32.GetParent.return_value = 1234
        fake_user32.GetWindowLongW.return_value = 0
        fake_windll = MagicMock()
        fake_windll.user32 = fake_user32
        fake_ctypes = MagicMock()
        fake_ctypes.windll = fake_windll
        with (
            patch.object(sys, "platform", "win32"),
            patch.dict(sys.modules, {"ctypes": fake_ctypes}),
        ):
            _make_clickthrough(MagicMock())
        fake_user32.SetWindowLongW.assert_called_once()

    def test_returns_when_no_hwnd(self):
        fake_user32 = MagicMock()
        fake_user32.GetParent.return_value = 0  # falsy hwnd → early return
        fake_windll = MagicMock()
        fake_windll.user32 = fake_user32
        fake_ctypes = MagicMock()
        fake_ctypes.windll = fake_windll
        with (
            patch.object(sys, "platform", "win32"),
            patch.dict(sys.modules, {"ctypes": fake_ctypes}),
        ):
            _make_clickthrough(MagicMock())
        fake_user32.SetWindowLongW.assert_not_called()

    def test_swallows_oserror(self):
        fake_user32 = MagicMock()
        fake_user32.GetParent.side_effect = OSError("nope")
        fake_windll = MagicMock()
        fake_windll.user32 = fake_user32
        fake_ctypes = MagicMock()
        fake_ctypes.windll = fake_windll
        with (
            patch.object(sys, "platform", "win32"),
            patch.dict(sys.modules, {"ctypes": fake_ctypes}),
        ):
            _make_clickthrough(MagicMock())  # must not raise
