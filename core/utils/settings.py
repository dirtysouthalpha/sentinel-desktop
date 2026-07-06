"""Settings persistence - save/load user preferences."""
import os
import json

DEFAULTS = {
    "brain_url": "http://100.70.240.55:8001",
    "brain_enabled": True,
    "mouse_speed": 0.5,
    "screenshot_format": "png",
    "theme": "dark",
    "llm_enabled": True,
    "minimize_to_tray": True,
    "startup_summary": True,
}


def get_settings_path():
    """Get path to settings file."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".sentinel_desktop", "settings.json")


def load_settings():
    """Load settings from disk, merging with defaults."""
    path = get_settings_path()
    settings = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path) as f:
                saved = json.load(f)
            settings.update(saved)
        except (json.JSONDecodeError, IOError):
            pass
    return settings


def save_settings(settings):
    """Save settings to disk."""
    path = get_settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    merged = dict(DEFAULTS)
    merged.update(settings)
    with open(path, "w") as f:
        json.dump(merged, f, indent=2)
    return path
