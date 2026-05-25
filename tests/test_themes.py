"""Tests for gui.themes — pure functions only (no Tkinter required)."""

import sys
from unittest.mock import patch

import customtkinter as ctk

from gui.themes import THEMES, apply_theme, get_theme, get_theme_names


def test_get_theme_returns_named_theme():
    theme = get_theme("sentinel")
    assert theme["accent"] == "#00F0FF"
    assert theme["label"] == "\U0001f6e1️ Sentinel"


def test_get_theme_falls_back_to_sentinel():
    theme = get_theme("nonexistent_theme_xyz")
    assert theme is THEMES["sentinel"]


def test_get_theme_names_returns_all_themes():
    names = get_theme_names()
    assert len(names) == len(THEMES)
    assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in names)


def test_get_theme_names_includes_sentinel():
    names = get_theme_names()
    keys = [k for k, _ in names]
    assert "sentinel" in keys
    assert "matrix" in keys
    assert "light" in keys


def test_every_theme_has_required_keys():
    required = {"accent", "bg_primary", "text_primary", "label"}
    for name, theme in THEMES.items():
        missing = required - set(theme.keys())
        assert not missing, f"Theme {name!r} missing keys: {missing}"


def test_every_theme_has_valid_appearance():
    for name, theme in THEMES.items():
        assert theme["appearance"] in ("dark", "light"), f"{name}: bad appearance"


def test_theme_colors_are_hex():
    color_keys = [
        "accent",
        "accent_hover",
        "bg_primary",
        "bg_secondary",
        "text_primary",
        "text_secondary",
    ]
    for name, theme in THEMES.items():
        for key in color_keys:
            val = theme.get(key, "")
            assert val.startswith("#"), f"{name}.{key} = {val!r} not a hex color"
            assert len(val) == 7, f"{name}.{key} = {val!r} not 7 chars"


def test_sentinel_theme_matches_override_spec():
    s = get_theme("sentinel")
    assert s["accent"] == "#00F0FF"
    assert s["bg_primary"] == "#050608"
    assert s["tag_assistant"] == "#95E400"
    assert s["tag_action"] == "#FBBC00"


# ---------------------------------------------------------------------------
# apply_theme
# ---------------------------------------------------------------------------
def test_apply_theme_by_name_returns_theme_and_calls_ctk():
    with (
        patch.object(ctk, "set_appearance_mode") as mock_appearance,
        patch.object(ctk, "set_default_color_theme") as mock_color,
    ):
        result = apply_theme("matrix")
    assert result is THEMES["matrix"]
    mock_appearance.assert_called_once_with("dark")
    mock_color.assert_called_once_with("dark-blue")


def test_apply_theme_unknown_name_falls_back_to_sentinel():
    with patch.object(ctk, "set_appearance_mode"), patch.object(ctk, "set_default_color_theme"):
        result = apply_theme("does_not_exist")
    assert result is THEMES["sentinel"]


def test_apply_theme_accepts_dict_passthrough():
    custom = {"appearance": "light", "color_theme": "blue", "accent": "#123456"}
    with (
        patch.object(ctk, "set_appearance_mode") as mock_appearance,
        patch.object(ctk, "set_default_color_theme") as mock_color,
    ):
        result = apply_theme(custom)
    assert result is custom
    mock_appearance.assert_called_once_with("light")
    mock_color.assert_called_once_with("blue")


def test_apply_theme_dict_uses_defaults_when_keys_missing():
    with (
        patch.object(ctk, "set_appearance_mode") as mock_appearance,
        patch.object(ctk, "set_default_color_theme") as mock_color,
    ):
        result = apply_theme({})
    assert result == {}
    mock_appearance.assert_called_once_with("dark")
    mock_color.assert_called_once_with("dark-blue")


def test_apply_theme_returns_sentinel_when_customtkinter_missing():
    # Setting the module to None makes ``import customtkinter`` raise ImportError.
    with patch.dict(sys.modules, {"customtkinter": None}):
        result = apply_theme("matrix")
    assert result is THEMES["sentinel"]
