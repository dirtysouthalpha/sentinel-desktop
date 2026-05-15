"""
Sentinel Desktop — Settings persistence layer.

Config is stored as JSON in the user's AppData directory (Windows)
or ~/.sentinel-desktop/ on other platforms.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, Any] = {
    "provider": "openai",
    "api_key": "",
    "model": "",
    "custom_base_url": "",
    "theme": "midnight",
    "approval_mode": True,
    "max_steps": 100,
    "screenshot_quality": 85,
    "cursor_feedback": True,
    "tenant_name": "",
    "tenant_lockdown": False,
    "sensitive_fields": [
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "credit_card",
        "ssn",
        "social_security",
    ],
    "api_host": "0.0.0.0",
    "api_port": 8091,
    "log_level": "INFO",
    "auto_screenshot": True,
    # Monitor to capture. None = primary (pyautogui default), 0 = virtual
    # union of all monitors (mss only), 1+ = specific monitor index.
    # "auto" picks the monitor containing the focused window (recommended);
    # 0 = virtual desktop union; 1+ = specific monitor index.
    "monitor": "auto",
    # How many screenshot messages stay in the LLM context at once.
    "image_history": 3,
    # Dry-run: state-changing actions log instead of executing.
    "dry_run": False,
    # Autonomous mode: skip every approval prompt and just let the agent run.
    # The Esc-x3 failsafe and Stop button still work.
    "autonomous": False,
    # Stealth input: route clicks/typing through Win32 PostMessage + UIA
    # Invoke instead of physical mouse/keyboard. Lets the user keep using
    # their own input device while the agent works in the background.
    # Falls back to physical input when the target app rejects synthesized
    # messages (Chromium-based apps, games, etc.).
    "stealth_input": False,
    # LLM retry policy.
    "llm_max_retries": 3,
    "llm_retry_base_delay": 1.0,
    # Use native LLM tool/function calling when the provider supports it.
    # Falls back to JSON-in-text parsing for providers that don't.
    "use_tools": True,
    # Up to 10 most recent goals; populated by the GUI as the user runs them.
    "recent_prompts": [],
    # Common prompt presets the user can launch from a chip button.
    "quick_actions": [
        "Take a screenshot and describe what you see, then finish.",
        "List all my open windows.",
        "Read my clipboard and tell me what's in it.",
        "What's currently focused on my screen?",
    ],
    # If True, the GUI hides to the system tray when minimized (requires
    # the optional pystray dependency).
    "minimize_to_tray": False,
    "start_in_tray": False,
}

# ---------------------------------------------------------------------------
# Config directory
# ---------------------------------------------------------------------------
if os.name == "nt":
    _CONFIG_DIR = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "SentinelDesktop",
    )
else:
    _CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".sentinel-desktop")

_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")


class Config:
    """Thin wrapper around a settings dict with save/load."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {**DEFAULTS}
        self._path = _CONFIG_PATH

    # -- dict-like access ----------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def as_dict(self) -> dict[str, Any]:
        return {**self._data}

    # -- persistence ---------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """Load config from disk, merge with defaults. Returns the dict."""
        if os.path.isfile(self._path):
            try:
                with open(self._path, encoding="utf-8") as fh:
                    data = json.load(fh)
                self._data.update(data)
                logger.info("Config loaded from %s", self._path)
            except Exception as exc:
                logger.warning("Failed to load config (%s) — using defaults", exc)
        return self._data

    def save(self, data: dict[str, Any] | None = None) -> None:
        """Persist config to disk. Optionally merge in new data first."""
        if data:
            self._data.update(data)
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            logger.info("Config saved to %s", self._path)
        except Exception as exc:
            logger.error("Failed to save config: %s", exc)

    def reset(self) -> None:
        self._data = {**DEFAULTS}

    # -- convenience properties ---------------------------------------------

    @property
    def provider(self) -> str:
        return self._data.get("provider", "openai")

    @property
    def api_key(self) -> str:
        return self._data.get("api_key", "")

    @property
    def model(self) -> str:
        return self._data.get("model", "")

    @property
    def max_steps(self) -> int:
        return self._data.get("max_steps", 100)

    @property
    def approval_mode(self) -> bool:
        return self._data.get("approval_mode", True)

    @approval_mode.setter
    def approval_mode(self, value: bool) -> None:
        self._data["approval_mode"] = value
