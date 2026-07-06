"""
Sentinel Desktop v2.0 - Configuration
Central settings, constants, and paths.
"""
import os
import json
from pathlib import Path

# Version
VERSION = "25.0.0"
APP_NAME = "Sentinel Desktop"
APP_TITLE = f"{APP_NAME} v{VERSION}"

# Paths
APP_DIR = Path(__file__).parent.parent
DATA_DIR = Path.home() / ".sentinel-desktop"
LOG_DIR = DATA_DIR / "logs"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
CONFIG_FILE = DATA_DIR / "config.json"

# Ensure dirs exist
for d in [DATA_DIR, LOG_DIR, SCREENSHOT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Neuralis Brain Configuration
BRAIN_URL = os.environ.get("NEURALIS_BRAIN_URL", "http://100.70.240.55:8001")
BRAIN_ENABLED_DEFAULT = True
BRAIN_TIMEOUT = 30

# UI Configuration
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 750
WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 600

# Colors - Sentinel Dark Theme
COLORS = {
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
}

# Default config
DEFAULT_CONFIG = {
    "brain_url": BRAIN_URL,
    "brain_enabled": BRAIN_ENABLED_DEFAULT,
    "appearance": "dark",
    "screenshot_format": "png",
    "mouse_speed": 0.3,
    "auto_scroll": True,
    "max_history": 100,
    "api_provider": "neuralis",
}


def load_config() -> dict:
    """Load user config or create default."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            # Merge defaults
            merged = {**DEFAULT_CONFIG, **cfg}
            return merged
        except Exception:
            return DEFAULT_CONFIG.copy()
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    """Save config to disk."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# System commands registry
COMMAND_CATEGORIES = {
    "system": "System Diagnostics",
    "automation": "Mouse & Keyboard",
    "network": "Network Tools",
    "process": "Process Management",
    "files": "File Operations",
    "ai": "AI Assistant",
}

# LLM Configuration
HATZ_API_KEY = os.environ.get("HATZ_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
LLM_ENABLED = bool(HATZ_API_KEY)
