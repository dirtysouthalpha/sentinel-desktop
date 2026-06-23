import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.themes import THEMES, THEME_NAMES, get_theme, apply_theme


def test_themes_exist():
    assert len(THEMES) >= 5

def test_theme_names():
    assert "dark" in THEME_NAMES
    assert "midnight" in THEME_NAMES
    assert "forest" in THEME_NAMES

def test_get_theme():
    theme = get_theme("dark")
    assert "bg_primary" in theme
    assert "accent" in theme

def test_get_theme_fallback():
    theme = get_theme("nonexistent")
    assert theme == THEMES["dark"]

def test_apply_theme():
    theme = apply_theme("midnight")
    assert "#7c3aed" in theme["accent"]

def test_theme_has_all_keys():
    required = ["bg_primary", "bg_secondary", "bg_tertiary", "accent", "accent_hover",
                "text_primary", "text_secondary", "success", "warning", "error",
                "user_bubble", "assistant_bubble"]
    for name, theme in THEMES.items():
        for key in required:
            assert key in theme, f"Theme {name} missing {key}"
