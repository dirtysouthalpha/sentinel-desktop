"""Tests for gui.themes — pure functions only (no Tkinter required)."""

import sys
from unittest.mock import patch

import customtkinter as ctk

from gui.themes import (
    _DEFAULT_TOKENS,
    THEMES,
    _resolve_theme,
    apply_theme,
    get_theme,
    get_theme_names,
)


def test_get_theme_returns_named_theme():
    theme = get_theme("sentinel")
    assert theme["accent"] == "#00F0FF"
    assert theme["label"] == "\U0001f6e1\ufe0f Sentinel"


def test_get_theme_falls_back_to_sentinel():
    theme = get_theme("nonexistent_theme_xyz")
    assert theme["accent"] == "#00F0FF"


def test_get_theme_names_returns_all_themes():
    names = get_theme_names()
    assert len(names) == len(THEMES)
    assert all(
        isinstance(pair, tuple) and len(pair) == 2 for pair in names
    )


def test_get_theme_names_includes_sentinel():
    names = get_theme_names()
    keys = [k for k, _ in names]
    assert "sentinel" in keys
    assert "matrix" in keys
    assert "light" in keys


def test_every_theme_has_required_keys():
    required = {"accent", "bg_primary", "text_primary", "label"}
    for name in THEMES:
        theme = get_theme(name)
        missing = required - set(theme.keys())
        assert not missing, f"Theme {name!r} missing keys: {missing}"


def test_every_theme_has_valid_appearance():
    for name in THEMES:
        theme = get_theme(name)
        assert theme["appearance"] in ("dark", "light"), (
            f"{name}: bad appearance"
        )


def test_theme_colors_are_hex():
    color_keys = [
        "accent",
        "accent_hover",
        "bg_primary",
        "bg_secondary",
        "text_primary",
        "text_secondary",
    ]
    for name in THEMES:
        theme = get_theme(name)
        for key in color_keys:
            val = theme.get(key, "")
            assert val.startswith("#"), (
                f"{name}.{key} = {val!r} not a hex color"
            )
            assert len(val) == 7, (
                f"{name}.{key} = {val!r} not 7 chars"
            )


def test_sentinel_theme_matches_override_spec():
    s = get_theme("sentinel")
    assert s["accent"] == "#00F0FF"
    assert s["bg_primary"] == "#050608"
    assert s["tag_assistant"] == "#95E400"
    assert s["tag_action"] == "#FBBC00"


def test_resolve_theme_fills_defaults():
    merged = _resolve_theme({"label": "Test"})
    assert merged["accent"] == _DEFAULT_TOKENS["accent"]
    assert merged["bg_primary"] == _DEFAULT_TOKENS["bg_primary"]
    assert merged["label"] == "Test"


def test_resolve_theme_override_wins():
    merged = _resolve_theme({"accent": "#custom"})
    assert merged["accent"] == "#custom"


# ---------------------------------------------------------------------------
# apply_theme
# ---------------------------------------------------------------------------
def test_apply_theme_by_name_returns_theme_and_calls_ctk():
    with (
        patch.object(ctk, "set_appearance_mode") as mock_appearance,
        patch.object(ctk, "set_default_color_theme") as mock_color,
    ):
        result = apply_theme("matrix")
    assert result["accent"] == "#00ff41"
    mock_appearance.assert_called_once_with("dark")
    mock_color.assert_called_once_with("dark-blue")


def test_apply_theme_unknown_name_falls_back_to_sentinel():
    with (
        patch.object(ctk, "set_appearance_mode"),
        patch.object(ctk, "set_default_color_theme"),
    ):
        result = apply_theme("does_not_exist")
    assert result["accent"] == "#00F0FF"


def test_apply_theme_accepts_dict_merges_defaults():
    custom = {"appearance": "light", "color_theme": "blue", "accent": "#123456"}
    with (
        patch.object(ctk, "set_appearance_mode") as mock_appearance,
        patch.object(ctk, "set_default_color_theme") as mock_color,
    ):
        result = apply_theme(custom)
    assert result["accent"] == "#123456"
    assert result["bg_primary"] == _DEFAULT_TOKENS["bg_primary"]
    mock_appearance.assert_called_once_with("light")
    mock_color.assert_called_once_with("blue")


def test_apply_theme_dict_uses_defaults_when_keys_missing():
    with (
        patch.object(ctk, "set_appearance_mode") as mock_appearance,
        patch.object(ctk, "set_default_color_theme") as mock_color,
    ):
        result = apply_theme({})
    assert result["accent"] == _DEFAULT_TOKENS["accent"]
    mock_appearance.assert_called_once_with("dark")
    mock_color.assert_called_once_with("dark-blue")


def test_apply_theme_returns_sentinel_when_customtkinter_missing():
    with patch.dict(sys.modules, {"customtkinter": None}):
        result = apply_theme("matrix")
    assert result["accent"] == "#00F0FF"
