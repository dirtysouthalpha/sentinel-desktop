"""
Sentinel Desktop v2 — Settings persistence layer.

Config is stored as JSON in the user's AppData directory (Windows)
or ~/.sentinel-desktop/ on other platforms.
"""

import json
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
DEFAULTS: Dict[str, Any] = {
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
        "password", "passwd", "secret", "token", "api_key",
        "credit_card", "ssn", "social_security",
    ],
    "api_host": "0.0.0.0",
    "api_port": 8091,
    "log_level": "INFO",
    "auto_screenshot": True,
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

    def __init__(self):
        self._data: Dict[str, Any] = {**DEFAULTS}
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

    def as_dict(self) -> Dict[str, Any]:
        return {**self._data}

    # -- persistence ---------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        """Load config from disk, merge with defaults. Returns the dict."""
        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._data.update(data)
                logger.info("Config loaded from %s", self._path)
            except Exception as exc:
                logger.warning("Failed to load config (%s) — using defaults", exc)
        return self._data

    def save(self, data: Optional[Dict[str, Any]] = None) -> None:
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
