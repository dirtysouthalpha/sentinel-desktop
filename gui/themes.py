"""
Sentinel Desktop v2 — Theme definitions for CustomTkinter.
"""

# Sentinel brand colors
COLORS = {
    # Primary
    "bg_dark": "#0d1117",
    "bg_panel": "#161b22",
    "bg_card": "#1c2128",
    "bg_input": "#21262d",
    "bg_hover": "#292e36",

    # Accent
    "accent": "#e8793a",       # Sentinel orange
    "accent_hover": "#f09050",
    "accent_dim": "#c45a20",
    "accent_glow": "#ff8c42",

    # Text
    "text_primary": "#e6edf3",
    "text_secondary": "#8b949e",
    "text_muted": "#6e7681",
    "text_link": "#58a6ff",

    # Status
    "success": "#3fb950",
    "warning": "#d29922",
    "error": "#f85149",
    "info": "#58a6ff",

    # Borders
    "border": "#30363d",
    "border_focus": "#e8793a",

    # Provider chips
    "chip_provider": "#1f6feb",
    "chip_tenant": "#238636",
    "chip_step": "#6e40c9",
}

# Theme configurations for CustomTkinter
CTK_THEMES = {
    "dark": {
        "color_theme": "dark-blue",
        "window_bg": COLORS["bg_dark"],
        "panel_bg": COLORS["bg_panel"],
        "card_bg": COLORS["bg_card"],
        "input_bg": COLORS["bg_input"],
        "text": COLORS["text_primary"],
        "text_secondary": COLORS["text_secondary"],
        "accent": COLORS["accent"],
        "border": COLORS["border"],
    },
    "light": {
        "color_theme": "blue",
        "window_bg": "#ffffff",
        "panel_bg": "#f6f8fa",
        "card_bg": "#ffffff",
        "input_bg": "#f0f0f0",
        "text": "#1f2328",
        "text_secondary": "#656d76",
        "accent": "#e8793a",
        "border": "#d0d7de",
    },
}

# Font definitions
FONTS = {
    "header": ("Segoe UI", 18, "bold"),
    "subheader": ("Segoe UI", 14, "bold"),
    "body": ("Segoe UI", 12),
    "body_bold": ("Segoe UI", 12, "bold"),
    "code": ("Cascadia Code", 11),
    "small": ("Segoe UI", 10),
    "tiny": ("Segoe UI", 9),
    "mono": ("Consolas", 11),
}

# Status indicator config
STATUS_COLORS = {
    "idle": COLORS["text_muted"],
    "running": COLORS["accent"],
    "success": COLORS["success"],
    "error": COLORS["error"],
    "warning": COLORS["warning"],
    "waiting": COLORS["info"],
}
