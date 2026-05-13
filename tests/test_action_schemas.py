"""Tests for core.action_schemas.validate_action."""

from __future__ import annotations

import pytest

from core.action_schemas import ACTION_MODELS, validate_action

# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_click_valid_coords():
    out, errs = validate_action({"action": "click", "x": 100, "y": 200})
    assert errs == []
    assert out["action"] == "click"
    assert out["x"] == 100
    assert out["y"] == 200
    assert out["button"] == "left"  # default filled in


def test_double_click_uses_click_model():
    out, errs = validate_action({"action": "double_click", "x": 5, "y": 5})
    assert errs == []
    assert out["action"] == "double_click"


def test_wait_default_seconds():
    out, errs = validate_action({"action": "wait"})
    assert errs == []
    assert out["seconds"] == 1.0


def test_hotkey_valid_list():
    out, errs = validate_action({"action": "hotkey", "keys": ["ctrl", "c"]})
    assert errs == []
    assert out["keys"] == ["ctrl", "c"]


def test_unmodeled_action_passes_through():
    """Actions without a model (e.g. screenshot, note) pass through untouched."""
    payload = {"action": "screenshot", "monitor": 0}
    out, errs = validate_action(payload)
    assert errs == []
    assert out == payload


def test_extras_preserved_on_modeled_action():
    """The model has ``extra='allow'`` so extra keys survive."""
    out, errs = validate_action({"action": "click", "x": 1, "y": 2, "comment": "from LLM"})
    assert errs == []
    assert out.get("comment") == "from LLM"


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


def test_click_rejects_negative_coords():
    out, errs = validate_action({"action": "click", "x": -1, "y": 5})
    assert errs
    assert any("x" in err for err in errs)


def test_click_rejects_outrageous_coords():
    out, errs = validate_action({"action": "click", "x": 999999, "y": 5})
    assert errs
    assert any("x" in err for err in errs)


def test_click_rejects_non_numeric_coords():
    out, errs = validate_action({"action": "click", "x": "lots", "y": 5})
    assert errs


def test_wait_caps_at_60_seconds():
    out, errs = validate_action({"action": "wait", "seconds": 3600})
    assert errs
    assert any("seconds" in err for err in errs)


def test_wait_rejects_negative():
    out, errs = validate_action({"action": "wait", "seconds": -1.0})
    assert errs


def test_hotkey_rejects_empty_keys_list():
    out, errs = validate_action({"action": "hotkey", "keys": []})
    assert errs


def test_hotkey_rejects_too_many_keys():
    out, errs = validate_action(
        {"action": "hotkey", "keys": ["a"] * 99},
    )
    assert errs


def test_write_file_requires_path():
    out, errs = validate_action({"action": "write_file", "content": "hi"})
    assert errs


def test_press_key_requires_nonempty():
    out, errs = validate_action({"action": "press_key", "key": ""})
    assert errs


# ---------------------------------------------------------------------------
# Defensive shapes
# ---------------------------------------------------------------------------


def test_non_dict_payload():
    out, errs = validate_action("not a dict")
    assert errs
    assert "dict" in errs[0]


def test_missing_action_key():
    out, errs = validate_action({"x": 1, "y": 2})
    assert errs
    assert "action" in errs[0]


def test_non_string_action_key():
    out, errs = validate_action({"action": 42})
    assert errs


def test_button_enum_constraint():
    out, errs = validate_action({"action": "click", "x": 1, "y": 1, "button": "moose"})
    assert errs


@pytest.mark.parametrize(
    "name",
    ["click", "type_text", "hotkey", "wait", "write_file", "read_file", "kill_process"],
)
def test_high_impact_actions_are_modeled(name):
    """Don't accidentally drop a high-impact action from the registry."""
    assert name in ACTION_MODELS
