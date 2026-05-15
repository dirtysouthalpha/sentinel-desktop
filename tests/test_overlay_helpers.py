"""Tests for gui/overlay.py pure helper functions."""

from gui.overlay import _color_for_kind, _coords_from_action, _label_for_action


class TestCoordsFromAction:
    def test_x_y_keys(self):
        assert _coords_from_action({"x": 100, "y": 200}) == (100, 200)

    def test_x_y_floats(self):
        assert _coords_from_action({"x": 10.5, "y": 20.7}) == (10, 20)

    def test_x_y_strings(self):
        assert _coords_from_action({"x": "50", "y": "75"}) == (50, 75)

    def test_position_list(self):
        assert _coords_from_action({"position": [300, 400]}) == (300, 400)

    def test_position_tuple(self):
        assert _coords_from_action({"position": (300, 400)}) == (300, 400)

    def test_no_coords(self):
        assert _coords_from_action({}) is None

    def test_only_x(self):
        assert _coords_from_action({"x": 10}) is None

    def test_invalid_x(self):
        assert _coords_from_action({"x": "abc", "y": 10}) is None

    def test_position_too_short(self):
        assert _coords_from_action({"position": [10]}) is None

    def test_position_invalid(self):
        assert _coords_from_action({"position": ["a", "b"]}) is None


class TestLabelForAction:
    def test_click(self):
        assert _label_for_action({"action": "click", "x": 5, "y": 10}) == "click (5, 10)"

    def test_click_text(self):
        result = _label_for_action({"action": "click_text", "text": "Submit"})
        assert result == "click text: Submit"

    def test_click_text_truncated(self):
        result = _label_for_action({"action": "click_text", "text": "A" * 50})
        assert len(result) < 60
        assert result.startswith("click text:")

    def test_click_control(self):
        result = _label_for_action({"action": "click_control", "name": "btnOK"})
        assert result == "click control: btnOK"

    def test_type_text(self):
        result = _label_for_action({"action": "type_text", "text": "hello"})
        assert result == "type: hello"

    def test_set_text(self):
        result = _label_for_action({"action": "set_text", "name": "field1"})
        assert result == "set text: field1"

    def test_hotkey(self):
        result = _label_for_action({"action": "hotkey", "keys": ["ctrl", "c"]})
        assert result == "hotkey: ctrl+c"

    def test_press_key(self):
        result = _label_for_action({"action": "press_key", "key": "Enter"})
        assert result == "press: Enter"

    def test_scroll(self):
        result = _label_for_action({"action": "scroll", "amount": 3})
        assert result == "scroll: 3"

    def test_unknown_action(self):
        assert _label_for_action({"action": "custom"}) == "custom"

    def test_empty_action(self):
        assert _label_for_action({}) == "action"


class TestColorForKind:
    def test_click_text(self):
        assert _color_for_kind("click_text") == "#95E400"

    def test_click_control(self):
        assert _color_for_kind("click_control") == "#95E400"

    def test_type_text(self):
        assert _color_for_kind("type_text") == "#00F0FF"

    def test_set_text(self):
        assert _color_for_kind("set_text") == "#00F0FF"

    def test_hotkey(self):
        assert _color_for_kind("hotkey") == "#FBBC00"

    def test_press_key(self):
        assert _color_for_kind("press_key") == "#FBBC00"

    def test_default(self):
        assert _color_for_kind("click") == "#e8793a"

    def test_unknown(self):
        assert _color_for_kind("anything") == "#e8793a"
