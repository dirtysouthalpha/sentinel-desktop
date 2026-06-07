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


# ---------------------------------------------------------------------------
# Web / Browser action schemas (v8.0)
# ---------------------------------------------------------------------------


class TestWebOpenSchema:
    def test_valid(self):
        out, errs = validate_action({"action": "web_open", "url": "https://example.com"})
        assert errs == []
        assert out["url"] == "https://example.com"
        assert out["wait_until"] == "load"  # default

    def test_missing_url(self):
        _, errs = validate_action({"action": "web_open"})
        assert errs

    def test_invalid_wait_until(self):
        _, errs = validate_action({"action": "web_open", "url": "https://x.com", "wait_until": "bad"})
        assert errs


class TestWebClickSchema:
    def test_by_selector(self):
        out, errs = validate_action({"action": "web_click", "selector": "#btn"})
        assert errs == []
        assert out["button"] == "left"  # default
        assert out["click_count"] == 1

    def test_by_role_and_name(self):
        out, errs = validate_action({"action": "web_click", "role": "button", "name": "Go"})
        assert errs == []

    def test_invalid_button(self):
        _, errs = validate_action({"action": "web_click", "selector": "#x", "button": "toe"})
        assert errs

    def test_click_count_too_high(self):
        _, errs = validate_action({"action": "web_click", "selector": "#x", "click_count": 10})
        assert errs


class TestWebTypeSchema:
    def test_valid(self):
        out, errs = validate_action({"action": "web_type", "text": "hello", "selector": "#q"})
        assert errs == []
        assert out["clear"] is True  # default

    def test_missing_text(self):
        _, errs = validate_action({"action": "web_type", "selector": "#q"})
        assert errs

    def test_by_label(self):
        out, errs = validate_action({"action": "web_type", "text": "user@x.com", "label": "Email"})
        assert errs == []


class TestWebReadSchema:
    def test_defaults(self):
        out, errs = validate_action({"action": "web_read"})
        assert errs == []
        assert out["full_page"] is False

    def test_with_selector(self):
        out, errs = validate_action({"action": "web_read", "selector": "#content"})
        assert errs == []


class TestWebExtractSchema:
    def test_defaults(self):
        out, errs = validate_action({"action": "web_extract"})
        assert errs == []
        assert out["selector"] == "table"
        assert out["format"] == "json"

    def test_invalid_format(self):
        _, errs = validate_action({"action": "web_extract", "format": "csv"})
        assert errs


class TestWebWaitForSchema:
    def test_defaults(self):
        out, errs = validate_action({"action": "web_wait_for"})
        assert errs == []
        assert out["timeout"] == 30.0

    def test_timeout_bounds(self):
        _, errs = validate_action({"action": "web_wait_for", "timeout": 0.0})
        assert errs
        _, errs = validate_action({"action": "web_wait_for", "timeout": 200.0})
        assert errs

    def test_invalid_state(self):
        _, errs = validate_action({"action": "web_wait_for", "state": "floating"})
        assert errs


class TestWebScreenshotSchema:
    def test_defaults(self):
        out, errs = validate_action({"action": "web_screenshot"})
        assert errs == []
        assert out["full_page"] is False


class TestWebEvalJsSchema:
    def test_valid(self):
        out, errs = validate_action({"action": "web_eval_js", "expression": "1+1"})
        assert errs == []

    def test_empty_expression(self):
        _, errs = validate_action({"action": "web_eval_js", "expression": ""})
        assert errs


class TestWebDownloadSchema:
    def test_no_args_ok(self):
        out, errs = validate_action({"action": "web_download"})
        assert errs == []
        assert out["url"] is None

    def test_with_url_and_path(self):
        out, errs = validate_action({
            "action": "web_download",
            "url": "https://x.com/f.pdf",
            "save_path": "/tmp/f.pdf",
        })
        assert errs == []


class TestWebUploadSchema:
    def test_valid(self):
        out, errs = validate_action({
            "action": "web_upload",
            "selector": "#file",
            "file_paths": ["/tmp/a.pdf"],
        })
        assert errs == []

    def test_missing_selector(self):
        _, errs = validate_action({"action": "web_upload", "file_paths": ["/tmp/a"]})
        assert errs

    def test_empty_file_paths(self):
        _, errs = validate_action({"action": "web_upload", "selector": "#f", "file_paths": []})
        assert errs


class TestWebTabsSchema:
    def test_defaults(self):
        out, errs = validate_action({"action": "web_tabs"})
        assert errs == []
        assert out["tab_action"] == "list"

    def test_switch_with_index(self):
        out, errs = validate_action({"action": "web_tabs", "tab_action": "switch", "index": 2})
        assert errs == []

    def test_invalid_tab_action(self):
        _, errs = validate_action({"action": "web_tabs", "tab_action": "explode"})
        assert errs

    def test_negative_index(self):
        _, errs = validate_action({"action": "web_tabs", "tab_action": "switch", "index": -1})
        assert errs


@pytest.mark.parametrize(
    "name",
    [
        "web_open", "web_click", "web_type", "web_read", "web_extract",
        "web_wait_for", "web_screenshot", "web_eval_js", "web_download",
        "web_upload", "web_tabs",
    ],
)
def test_web_actions_are_modeled(name):
    """All web actions are in the ACTION_MODELS registry."""
    assert name in ACTION_MODELS
