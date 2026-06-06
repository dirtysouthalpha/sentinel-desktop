"""Tests for gui/cursor_overlay.py — CursorOverlay class and module helpers.

The animation loops call ``time.sleep`` per frame; tests patch it to a no-op
so the loops complete instantly. ``_root`` / ``_canvas`` are replaced with
mocks where the real Tk lifecycle isn't under test.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import gui.cursor_overlay as co


def _fake_tk(**attrs):
    """A throwaway ``tkinter`` module with a *real* TclError exception.

    Used by except-branch tests so they stay correct regardless of test
    ordering — another test module rebinds ``sys.modules['tkinter']`` to a
    MagicMock at import time, whose ``TclError`` is not a real exception.
    """
    mod = types.ModuleType("tkinter")
    mod.TclError = type("TclError", (Exception,), {})
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


from gui.cursor_overlay import (
    CursorOverlay,
    get_overlay,
    show_action,
    start_overlay,
    stop_overlay,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    co._overlay = None
    yield
    co._overlay = None


# ---------------------------------------------------------------------------
# Construction / simple accessors
# ---------------------------------------------------------------------------
class TestBasics:
    def test_init_defaults(self):
        ov = CursorOverlay()
        assert ov._accent == "#00F0FF"
        assert ov._running is False
        assert ov._queue == []

    def test_set_accent(self):
        ov = CursorOverlay()
        ov.set_accent("#FF0000")
        assert ov._accent == "#FF0000"

    def test_show_action_enqueues(self):
        ov = CursorOverlay()
        ov.show_action({"x": 1, "y": 2})
        assert ov._queue == [{"x": 1, "y": 2}]


# ---------------------------------------------------------------------------
# start / stop / run loop
# ---------------------------------------------------------------------------
class TestStartStop:
    def test_start_runs_loop_and_finishes(self):
        ov = CursorOverlay()
        assert ov.start() is True
        if ov._thread is not None:
            ov._thread.join(timeout=2)
        # _run_loop sets _running False in its finally clause once mainloop ends.
        assert ov._running is False
        assert ov._root is not None

    def test_start_is_idempotent_when_running(self):
        ov = CursorOverlay()
        ov._running = True
        assert ov.start() is True  # short-circuits without spawning a thread
        assert ov._thread is None

    def test_start_returns_false_without_tkinter(self):
        ov = CursorOverlay()
        with patch.dict(sys.modules, {"tkinter": None}):
            assert ov.start() is False
        assert ov._running is False

    def test_run_loop_swallows_attr_and_mainloop_errors(self):
        ov = CursorOverlay()
        fake_root = MagicMock()
        fake_root.winfo_id.return_value = 0
        fake = _fake_tk(Tk=lambda *a, **k: fake_root, Canvas=lambda *a, **k: MagicMock())
        fake_root.wm_attributes.side_effect = fake.TclError("no transparentcolor")
        fake_root.mainloop.side_effect = fake.TclError("mainloop boom")
        # _run_loop does a local ``import tkinter`` -> patch sys.modules too.
        with (
            patch.dict(sys.modules, {"tkinter": fake}),
            patch.object(co, "tk", fake),
        ):
            ov._running = True
            ov._run_loop()  # must not raise despite the injected TclErrors
        assert ov._running is False

    def test_stop_schedules_destroy(self):
        ov = CursorOverlay()
        ov._root = MagicMock()
        ov.stop()
        assert ov._running is False
        ov._root.after.assert_called_once()

    def test_stop_without_root_is_noop(self):
        ov = CursorOverlay()
        ov._root = None
        ov.stop()  # must not raise
        assert ov._running is False

    def test_stop_swallows_destroy_errors(self):
        fake = _fake_tk()
        ov = CursorOverlay()
        ov._root = MagicMock()
        ov._root.after.side_effect = fake.TclError("dead")
        with patch.object(co, "tk", fake):  # stop() uses the module-level tk
            ov.stop()  # must not raise


# ---------------------------------------------------------------------------
# _make_click_through
# ---------------------------------------------------------------------------
class TestClickThrough:
    def test_swallows_attribute_error_on_non_windows(self):
        ov = CursorOverlay()
        ov._root = MagicMock()
        ov._root.winfo_id.return_value = 1
        # Real ctypes on Linux has no .windll -> AttributeError -> swallowed.
        ov._make_click_through()  # must not raise

    def test_applies_styles_on_windows(self):
        ov = CursorOverlay()
        ov._root = MagicMock()
        ov._root.winfo_id.return_value = 4321
        fake_user32 = MagicMock()
        fake_user32.GetWindowLongW.return_value = 0
        fake_windll = MagicMock()
        fake_windll.user32 = fake_user32
        fake_ctypes = MagicMock()
        fake_ctypes.windll = fake_windll
        with patch.dict(sys.modules, {"ctypes": fake_ctypes}):
            ov._make_click_through()
        fake_user32.SetWindowLongW.assert_called_once()


# ---------------------------------------------------------------------------
# _process_queue
# ---------------------------------------------------------------------------
class TestProcessQueue:
    def test_returns_early_when_not_running(self):
        ov = CursorOverlay()
        ov._running = False
        ov._root = MagicMock()
        ov._process_queue()
        ov._root.after.assert_not_called()

    def test_animates_queued_action_and_reschedules(self):
        ov = CursorOverlay()
        ov._running = True
        ov._root = MagicMock()
        ov._queue = [{"x": 5, "y": 6, "type": "click"}]
        with patch.object(ov, "_animate_action") as anim:
            ov._process_queue()
        anim.assert_called_once_with({"x": 5, "y": 6, "type": "click"})
        ov._root.after.assert_called_once_with(16, ov._process_queue)

    def test_reschedules_even_with_empty_queue(self):
        ov = CursorOverlay()
        ov._running = True
        ov._root = MagicMock()
        with patch.object(ov, "_animate_action") as anim:
            ov._process_queue()
        anim.assert_not_called()
        ov._root.after.assert_called_once()


# ---------------------------------------------------------------------------
# _animate_action
# ---------------------------------------------------------------------------
class TestAnimateAction:
    def _make_overlay(self):
        ov = CursorOverlay()
        ov._running = True
        ov._root = MagicMock()
        ov._canvas = MagicMock()
        ov._ring_id, ov._inner_id, ov._label_id = 1, 2, 3
        return ov

    @pytest.mark.parametrize(
        "action_type",
        ["click", "type_text", "press_key", "scroll", "unknown_thing"],
    )
    def test_full_animation_per_action_type(self, action_type):
        ov = self._make_overlay()
        with patch("gui.cursor_overlay.time.sleep"):
            ov._animate_action({"x": 100, "y": 200, "type": action_type, "label": "go"})
        # Reached the hide step at the end.
        assert ov._current_x == 100 and ov._current_y == 200
        ov._canvas.coords.assert_called()

    def test_animation_without_label_skips_label_draw(self):
        ov = self._make_overlay()
        with patch("gui.cursor_overlay.time.sleep"):
            ov._animate_action({"x": 10, "y": 20, "type": "click"})
        assert ov._current_x == 10

    def test_glide_aborts_when_stopped(self):
        ov = self._make_overlay()

        # Stop after the first sleep so the glide loop's running-check exits.
        def _stop(_):
            ov._running = False

        with patch("gui.cursor_overlay.time.sleep", side_effect=_stop):
            ov._animate_action({"x": 50, "y": 50, "type": "click", "label": "x"})
        # Aborted before updating _current to the target.
        assert (ov._current_x, ov._current_y) != (50, 50)

    def test_pulse_aborts_when_stopped(self):
        ov = self._make_overlay()
        # Glide is ~21 steps; stop partway through the pulse loop (after ~25).
        counter = {"n": 0}

        def _count(_):
            counter["n"] += 1
            if counter["n"] >= 25:
                ov._running = False

        with patch("gui.cursor_overlay.time.sleep", side_effect=_count):
            ov._animate_action({"x": 5, "y": 5, "type": "click", "label": "x"})
        # Glide completed (current updated) but pulse aborted before hide step.
        assert (ov._current_x, ov._current_y) == (5, 5)

    def test_fade_aborts_when_stopped(self):
        ov = self._make_overlay()
        # Glide ~21 + pulse ~30 = ~51; stop partway into the fade loop.
        counter = {"n": 0}

        def _count(_):
            counter["n"] += 1
            if counter["n"] >= 55:
                ov._running = False

        with patch("gui.cursor_overlay.time.sleep", side_effect=_count):
            ov._animate_action({"x": 7, "y": 7, "type": "click", "label": "x"})
        assert (ov._current_x, ov._current_y) == (7, 7)


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------
class TestSingleton:
    def test_get_overlay_creates_and_caches(self):
        a = get_overlay()
        b = get_overlay()
        assert a is b
        assert isinstance(a, CursorOverlay)

    def test_start_overlay_sets_accent_and_starts(self):
        with patch.object(CursorOverlay, "start", return_value=True) as start:
            result = start_overlay("#123456")
        assert result is True
        assert get_overlay()._accent == "#123456"
        start.assert_called_once()

    def test_show_action_routes_to_singleton(self):
        show_action({"x": 1, "y": 1})
        assert get_overlay()._queue == [{"x": 1, "y": 1}]

    def test_stop_overlay_stops_and_clears(self):
        ov = get_overlay()
        with patch.object(ov, "stop") as stop:
            stop_overlay()
        stop.assert_called_once()
        assert co._overlay is None

    def test_stop_overlay_noop_when_none(self):
        co._overlay = None
        stop_overlay()  # must not raise
        assert co._overlay is None


class TestAnimateActionNoLabel:
    """Branch 268->272: label is empty → skip label-draw block."""

    def _make_overlay(self):
        from gui.cursor_overlay import CursorOverlay

        ov = CursorOverlay()
        ov._root = MagicMock()
        ov._canvas = MagicMock()
        ov._ring_id = "ring"
        ov._inner_id = "inner"
        ov._label_id = "label"
        ov._running = True
        ov._current_x = 0
        ov._current_y = 0
        return ov

    def test_no_label_no_type_skips_label_draw(self):
        """When action has neither 'label' nor 'type', label is '' → skip."""
        ov = self._make_overlay()
        with patch("gui.cursor_overlay.time.sleep"):
            ov._animate_action({"x": 10, "y": 20})  # no label, no type key
        # _canvas.itemconfig should NOT have been called with a text value for the label
        itemconfig_calls = [
            c for c in ov._canvas.itemconfig.call_args_list if c[0] and c[0][0] == "label"
        ]
        assert not itemconfig_calls
