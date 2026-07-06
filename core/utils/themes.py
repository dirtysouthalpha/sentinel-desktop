"""Theme system for Sentinel Desktop."""
from core.config_legacy import COLORS

THEMES = {
    "dark": {
        "bg_primary": "#0a0e14",
        "bg_secondary": "#131820",
        "bg_tertiary": "#1a2332",
        "accent": "#00d4ff",
        "accent_hover": "#00b4d8",
        "text_primary": "#e0e6ed",
        "text_secondary": "#8b9bb4",
        "success": "#00ff88",
        "warning": "#ffaa00",
        "error": "#ff4466",
        "user_bubble": "#1a3a5c",
        "assistant_bubble": "#1e2d3d",
    },
    "midnight": {
        "bg_primary": "#0d0d1a",
        "bg_secondary": "#1a1a2e",
        "bg_tertiary": "#232342",
        "accent": "#7c3aed",
        "accent_hover": "#6d28d9",
        "text_primary": "#f0f0ff",
        "text_secondary": "#a0a0c0",
        "success": "#10b981",
        "warning": "#f59e0b",
        "error": "#ef4444",
        "user_bubble": "#312e81",
        "assistant_bubble": "#1e1b4b",
    },
    "forest": {
        "bg_primary": "#0a1a0a",
        "bg_secondary": "#132613",
        "bg_tertiary": "#1a331a",
        "accent": "#22c55e",
        "accent_hover": "#16a34a",
        "text_primary": "#e0f0e0",
        "text_secondary": "#8baa8b",
        "success": "#22c55e",
        "warning": "#eab308",
        "error": "#dc2626",
        "user_bubble": "#14532d",
        "assistant_bubble": "#1e3d2d",
    },
    "sunset": {
        "bg_primary": "#1a0a0a",
        "bg_secondary": "#2d1313",
        "bg_tertiary": "#3d1a1a",
        "accent": "#f97316",
        "accent_hover": "#ea580c",
        "text_primary": "#fff0e0",
        "text_secondary": "#c0a0a0",
        "success": "#22c55e",
        "warning": "#facc15",
        "error": "#ef4444",
        "user_bubble": "#7c2d12",
        "assistant_bubble": "#4a1d0d",
    },
    "ocean": {
        "bg_primary": "#0a0a1a",
        "bg_secondary": "#131326",
        "bg_tertiary": "#1a1a33",
        "accent": "#06b6d4",
        "accent_hover": "#0891b2",
        "text_primary": "#e0f0ff",
        "text_secondary": "#8baac0",
        "success": "#22c55e",
        "warning": "#eab308",
        "error": "#ef4444",
        "user_bubble": "#155e75",
        "assistant_bubble": "#0e3d4a",
    },
}

THEME_NAMES = list(THEMES.keys())


def get_theme(name: str) -> dict:
    """Get a theme by name."""
    return THEMES.get(name, THEMES["dark"])


def apply_theme(name: str):
    """Apply a theme to the global COLORS dict."""
    theme = get_theme(name)
    for key, value in theme.items():
        COLORS[key] = value
    return theme
