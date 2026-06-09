"""Sentinel Desktop v14.0 — Theme definitions for CustomTkinter.

19 built-in themes. Default "sentinel" matches Sentinel Override's
cyberpunk HUD exactly (cyan #00F0FF, near-black #050608, lime/amber).
Tokens synced with sentinel-override/popup.css :root variables.
Each theme only specifies overrides — _DEFAULT_TOKENS fills the rest.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default token set — every theme inherits these then overrides selectively.
# Synced with sentinel-override/popup.css design tokens.
# ---------------------------------------------------------------------------
_DEFAULT_TOKENS: dict[str, Any] = {
    "appearance": "dark",
    "color_theme": "dark-blue",
    # Accent
    "accent": "#00F0FF",
    "accent_hover": "#00c8d4",
    # Surfaces
    "bg_primary": "#050608",
    "bg_secondary": "#0A0C10",
    "bg_tertiary": "#111418",
    "bg_input": "#0A0C10",
    "bg_elevated": "#333539",
    "bg_hover": "#333539",
    # Text
    "text_primary": "#e2e2e8",
    "text_secondary": "#b9cacb",
    "text_tertiary": "#849495",
    # Borders
    "border_color": "#3b494b",
    "border_active": "#00F0FF",
    # Status
    "status_idle": "#849495",
    "status_running": "#95E400",
    "status_error": "#ff3b3b",
    "status_warning": "#FBBC00",
    # Chat tags
    "tag_user": "#00F0FF",
    "tag_assistant": "#95E400",
    "tag_action": "#FBBC00",
    "tag_error": "#ff3b3b",
    "tag_system": "#849495",
    # Overlay
    "overlay_ring": "#00F0FF",
    "overlay_fill": "#00F0FF",
    # Glow effects
    "glow_accent": "#00F0FF",
    "glow_success": "#95E400",
    "glow_error": "#ff3b3b",
    # Radius — Override uses 4px everywhere
    "radius": 4,
    # Sidebar
    "sidebar_bg": "#0A0C10",
    "sidebar_width": 200,
    "sidebar_icon_size": 18,
}

# ---------------------------------------------------------------------------
# Themes — each only specifies what differs from defaults.
# ---------------------------------------------------------------------------
THEMES: dict[str, dict[str, Any]] = {
    # ── Sentinel (default) — Override Cyberpunk HUD ─────────────────
    "sentinel": {
        "label": "\U0001f6e1\ufe0f Sentinel",
    },
    # ── Dark family ─────────────────────────────────────────────────
    "midnight": {
        "label": "\U0001f30c Midnight",
        "accent": "#4A90D9",
        "accent_hover": "#5BA0E9",
        "bg_primary": "#1a1a2e",
        "bg_secondary": "#16213e",
        "bg_input": "#0f3460",
        "bg_hover": "#1e2e52",
        "text_primary": "#e0e0e0",
        "text_secondary": "#a0a0b0",
        "status_idle": "#666666",
        "status_running": "#2ecc71",
        "tag_user": "#4A90D9",
        "tag_assistant": "#2ecc71",
        "tag_action": "#f39c12",
        "overlay_ring": "#4A90D9",
        "overlay_fill": "#4A90D9",
        "border_active": "#4A90D9",
        "glow_accent": "#4A90D9",
    },
    "dark": {
        "label": "\U0001f319 Dark",
        "accent": "#1f6aa5",
        "accent_hover": "#2a7abf",
        "bg_primary": "#2b2b2b",
        "bg_secondary": "#333333",
        "bg_input": "#404040",
        "bg_hover": "#444444",
        "text_primary": "#d0d0d0",
        "text_secondary": "#909090",
        "status_idle": "#666666",
        "tag_user": "#1f6aa5",
        "tag_assistant": "#2ecc71",
        "tag_action": "#f39c12",
        "overlay_ring": "#1f6aa5",
        "overlay_fill": "#1f6aa5",
        "border_active": "#1f6aa5",
        "glow_accent": "#1f6aa5",
    },
    "matrix": {
        "label": "\U0001f4bb Matrix",
        "accent": "#00ff41",
        "accent_hover": "#33ff66",
        "bg_input": "#0f1a0f",
        "bg_hover": "#1a3a1a",
        "text_primary": "#00ff41",
        "text_secondary": "#009926",
        "text_tertiary": "#006600",
        "status_idle": "#004d00",
        "status_running": "#00ff41",
        "tag_user": "#00ff41",
        "tag_assistant": "#33ff66",
        "tag_action": "#99ff99",
        "overlay_ring": "#00ff41",
        "overlay_fill": "#00ff41",
        "border_color": "#1a3a1a",
        "border_active": "#00ff41",
        "glow_accent": "#00ff41",
        "sidebar_bg": "#0a140a",
    },
    "tron": {
        "label": "\U0001f537 Tron",
        "accent": "#00d4ff",
        "accent_hover": "#33e8ff",
        "bg_input": "#101c2a",
        "bg_hover": "#182535",
        "text_primary": "#c0e8ff",
        "text_secondary": "#5a8aa5",
        "status_idle": "#2a4a5a",
        "status_running": "#00d4ff",
        "status_error": "#ff3366",
        "tag_user": "#00d4ff",
        "tag_assistant": "#66eeff",
        "tag_action": "#ffaa00",
        "tag_error": "#ff3366",
        "overlay_ring": "#00d4ff",
        "overlay_fill": "#00d4ff",
        "border_color": "#2a4a5a",
        "border_active": "#00d4ff",
        "glow_accent": "#00d4ff",
    },
    "cyberpunk": {
        "label": "\u26a1 Cyberpunk",
        "accent": "#ff2a6d",
        "accent_hover": "#ff5588",
        "bg_input": "#1a0018",
        "bg_hover": "#280040",
        "text_primary": "#ff2a6d",
        "text_secondary": "#cc2288",
        "status_idle": "#660033",
        "status_running": "#05d9e8",
        "tag_user": "#ff2a6d",
        "tag_assistant": "#05d9e8",
        "tag_action": "#f5dd42",
        "overlay_ring": "#ff2a6d",
        "overlay_fill": "#ff2a6d",
        "border_active": "#ff2a6d",
        "glow_accent": "#ff2a6d",
    },
    "neon": {
        "label": "\U0001f4a3 Neon",
        "accent": "#e040fb",
        "accent_hover": "#cc33ff",
        "bg_input": "#1f0033",
        "bg_hover": "#280045",
        "text_primary": "#e0b0ff",
        "text_secondary": "#9966cc",
        "status_idle": "#4d0080",
        "status_running": "#e040fb",
        "status_error": "#ff0066",
        "tag_user": "#e040fb",
        "tag_assistant": "#cc66ff",
        "tag_action": "#ff9900",
        "tag_error": "#ff0066",
        "overlay_ring": "#e040fb",
        "overlay_fill": "#e040fb",
        "border_active": "#e040fb",
        "glow_accent": "#e040fb",
    },
    "terminal": {
        "label": "\U0001f7e2 Terminal",
        "accent": "#33ff33",
        "accent_hover": "#66ff66",
        "bg_primary": "#000000",
        "bg_input": "#141414",
        "bg_hover": "#1e1e1e",
        "text_primary": "#33ff33",
        "text_secondary": "#008800",
        "text_tertiary": "#005500",
        "status_idle": "#004400",
        "status_running": "#33ff33",
        "tag_user": "#33ff33",
        "tag_assistant": "#44ff44",
        "tag_action": "#ffff00",
        "overlay_ring": "#33ff33",
        "overlay_fill": "#33ff33",
        "border_color": "#004400",
        "border_active": "#33ff33",
        "glow_accent": "#33ff33",
        "sidebar_bg": "#0a0a0a",
    },
    "blood": {
        "label": "\U0001fa78 Blood",
        "accent": "#ff1a1a",
        "accent_hover": "#ff3333",
        "bg_input": "#200000",
        "bg_hover": "#2a0000",
        "text_primary": "#ff3333",
        "text_secondary": "#993333",
        "status_idle": "#4d0000",
        "status_running": "#ff1a1a",
        "tag_user": "#ff1a1a",
        "tag_assistant": "#ff4444",
        "tag_action": "#ff8800",
        "overlay_ring": "#ff1a1a",
        "overlay_fill": "#ff1a1a",
        "border_active": "#ff1a1a",
        "glow_accent": "#ff1a1a",
    },
    "ocean": {
        "label": "\U0001f30a Ocean",
        "color_theme": "blue",
        "accent": "#0077be",
        "accent_hover": "#0088dd",
        "bg_primary": "#001122",
        "bg_secondary": "#001a33",
        "bg_input": "#002244",
        "bg_hover": "#002a50",
        "text_primary": "#c0ddef",
        "text_secondary": "#5a8ea8",
        "status_idle": "#003355",
        "status_running": "#00aaff",
        "tag_user": "#0077be",
        "tag_assistant": "#00aaff",
        "tag_action": "#ffbb33",
        "overlay_ring": "#0077be",
        "overlay_fill": "#0077be",
        "border_active": "#0077be",
        "glow_accent": "#0077be",
    },
    # ── Override-exclusive presets (from popup.css) ──────────────────
    "ember": {
        "label": "\U0001f525 Ember",
        "accent": "#ff7a45",
        "accent_hover": "#ff9966",
        "bg_input": "#1a0f05",
        "bg_hover": "#2a1505",
        "text_primary": "#ffd4b8",
        "text_secondary": "#e89e7a",
        "status_idle": "#663300",
        "status_running": "#ff7a45",
        "tag_user": "#ff7a45",
        "tag_assistant": "#ffaa44",
        "overlay_ring": "#ff7a45",
        "overlay_fill": "#ff7a45",
        "border_active": "#ff7a45",
        "glow_accent": "#ff7a45",
    },
    "frost": {
        "label": "\u2744\ufe0f Frost",
        "accent": "#00b8d4",
        "accent_hover": "#33ccdd",
        "bg_input": "#0a1520",
        "bg_hover": "#152030",
        "text_primary": "#c0e8ff",
        "text_secondary": "#98c8e8",
        "status_idle": "#1a3a4a",
        "status_running": "#00b8d4",
        "tag_user": "#00b8d4",
        "tag_assistant": "#66ddff",
        "overlay_ring": "#00b8d4",
        "overlay_fill": "#00b8d4",
        "border_active": "#00b8d4",
        "glow_accent": "#00b8d4",
    },
    "phantom": {
        "label": "\U0001f47b Phantom",
        "accent": "#8a5cff",
        "accent_hover": "#a077ff",
        "bg_input": "#15102a",
        "bg_hover": "#201a35",
        "text_primary": "#c8c0e8",
        "text_secondary": "#a8a0d8",
        "status_idle": "#2a2255",
        "status_running": "#8a5cff",
        "tag_user": "#8a5cff",
        "tag_assistant": "#aa88ff",
        "overlay_ring": "#8a5cff",
        "overlay_fill": "#8a5cff",
        "border_active": "#8a5cff",
        "glow_accent": "#8a5cff",
    },
    # ── Light / warm family ─────────────────────────────────────────
    "light": {
        "label": "\u2600\ufe0f Light",
        "appearance": "light",
        "color_theme": "blue",
        "accent": "#1f6aa5",
        "accent_hover": "#2a7abf",
        "bg_primary": "#f0f0f0",
        "bg_secondary": "#e0e0e0",
        "bg_tertiary": "#d0d0d0",
        "bg_input": "#ffffff",
        "bg_elevated": "#cccccc",
        "bg_hover": "#d0d0d0",
        "text_primary": "#222222",
        "text_secondary": "#666666",
        "text_tertiary": "#999999",
        "status_idle": "#999999",
        "status_running": "#2ecc71",
        "status_error": "#e74c3c",
        "tag_user": "#1f6aa5",
        "tag_assistant": "#27ae60",
        "tag_action": "#e67e22",
        "overlay_ring": "#1f6aa5",
        "overlay_fill": "#1f6aa5",
        "border_color": "#cccccc",
        "border_active": "#1f6aa5",
        "glow_accent": "#1f6aa5",
        "sidebar_bg": "#e0e0e0",
    },
    "sunset": {
        "label": "\U0001f305 Sunset",
        "accent": "#ff6b35",
        "accent_hover": "#ff8855",
        "bg_primary": "#1a0a00",
        "bg_secondary": "#2a1500",
        "bg_input": "#3a2000",
        "bg_hover": "#4a2a00",
        "text_primary": "#ffd4b8",
        "text_secondary": "#b07040",
        "status_idle": "#663300",
        "status_running": "#ff6b35",
        "tag_user": "#ff6b35",
        "tag_assistant": "#ffaa44",
        "tag_action": "#ffdd00",
        "overlay_ring": "#ff6b35",
        "overlay_fill": "#ff6b35",
        "border_active": "#ff6b35",
        "glow_accent": "#ff6b35",
    },
    "paper": {
        "label": "\U0001f4dc Paper",
        "appearance": "light",
        "color_theme": "blue",
        "accent": "#8b7355",
        "accent_hover": "#a08866",
        "bg_primary": "#f5f0e8",
        "bg_secondary": "#ebe5d8",
        "bg_tertiary": "#ddd5c8",
        "bg_input": "#ffffff",
        "bg_elevated": "#d5cfc0",
        "bg_hover": "#ddd5c8",
        "text_primary": "#3a3226",
        "text_secondary": "#7a6e5e",
        "text_tertiary": "#9a9080",
        "status_idle": "#b0a890",
        "status_running": "#6b8e4e",
        "status_error": "#c44",
        "tag_user": "#8b7355",
        "tag_assistant": "#6b8e4e",
        "tag_action": "#b8860b",
        "overlay_ring": "#8b7355",
        "overlay_fill": "#8b7355",
        "border_color": "#c8c0b0",
        "border_active": "#8b7355",
        "glow_accent": "#8b7355",
        "sidebar_bg": "#ebe5d8",
    },
    "forest": {
        "label": "\U0001f332 Forest",
        "accent": "#2d6a4f",
        "accent_hover": "#3a8a66",
        "bg_primary": "#0a1208",
        "bg_secondary": "#0f1a0c",
        "bg_input": "#142210",
        "bg_hover": "#1a2e16",
        "text_primary": "#a8d5a0",
        "text_secondary": "#5a8a50",
        "status_idle": "#2a4a22",
        "status_running": "#52b788",
        "tag_user": "#2d6a4f",
        "tag_assistant": "#52b788",
        "tag_action": "#d4a037",
        "overlay_ring": "#2d6a4f",
        "overlay_fill": "#2d6a4f",
        "border_color": "#1a3a18",
        "border_active": "#2d6a4f",
        "glow_accent": "#2d6a4f",
    },
    "mono": {
        "label": "\u2b1b Mono",
        "accent": "#cccccc",
        "accent_hover": "#ffffff",
        "bg_primary": "#111111",
        "bg_secondary": "#1a1a1a",
        "bg_input": "#222222",
        "bg_hover": "#2a2a2a",
        "text_primary": "#cccccc",
        "text_secondary": "#777777",
        "text_tertiary": "#555555",
        "status_idle": "#444444",
        "status_running": "#ffffff",
        "tag_user": "#cccccc",
        "tag_assistant": "#ffffff",
        "tag_action": "#999999",
        "overlay_ring": "#cccccc",
        "overlay_fill": "#cccccc",
        "border_color": "#333333",
        "border_active": "#cccccc",
        "glow_accent": "#cccccc",
    },
}

# Ensure every theme has a label.
for _key, _val in THEMES.items():
    _val.setdefault("label", _key)


def _resolve_theme(overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge user-overrides onto default tokens."""
    merged = dict(_DEFAULT_TOKENS)
    merged.update(overrides)
    return merged


def get_theme(name: str) -> dict[str, Any]:
    """Get a fully-resolved theme by name, falling back to sentinel."""
    raw = THEMES.get(name, THEMES["sentinel"])
    return _resolve_theme(raw)


def get_theme_names() -> list[tuple[str, str]]:
    """Return list of (key, label) tuples for all themes."""
    return [(k, v["label"]) for k, v in THEMES.items()]


def apply_theme(name_or_dict: str | dict[str, Any]) -> dict[str, Any]:
    """Apply a named theme or theme dict to customtkinter.

    Returns the fully-resolved theme dict.
    """
    try:
        import customtkinter as ctk
    except ImportError:
        return get_theme("sentinel")

    if isinstance(name_or_dict, str):
        theme = get_theme(name_or_dict)
    else:
        theme = _resolve_theme(name_or_dict)

    ctk.set_appearance_mode(theme.get("appearance", "dark"))
    ctk.set_default_color_theme(theme.get("color_theme", "dark-blue"))

    return theme
