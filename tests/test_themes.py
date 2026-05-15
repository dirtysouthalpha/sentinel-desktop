"""Tests for gui.themes — pure functions only (no Tkinter required)."""

from gui.themes import THEMES, get_theme, get_theme_names


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
