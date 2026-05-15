"""Gap tests for action_schemas.py — right_click sets button."""

from core.action_schemas import validate_action


class TestRightClick:
    """right_click action sets button to 'right' via model_validator."""

    def test_right_click_sets_button(self) -> None:
        out, errs = validate_action({"action": "right_click", "x": 10, "y": 20})
        assert errs == []
        assert out["button"] == "right"
        assert out["action"] == "right_click"

    def test_double_click_sets_clicks(self) -> None:
        out, errs = validate_action({"action": "double_click", "x": 5, "y": 5})
        assert errs == []
        assert out["clicks"] == 2
