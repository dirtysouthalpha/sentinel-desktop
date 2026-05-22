"""
Tests for gui/overlay.py — Action overlay utility functions.

Tests the pure helper functions: _coords_from_action, _label_for_action,
_color_for_kind. GUI class tests are not included (require tkinter runtime).
"""

from __future__ import annotations

import pytest

from gui.overlay import _coords_from_action, _label_for_action, _color_for_kind


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
