"""
Sentinel Desktop v28.0.0 - Auto-Update Checker.

Checks GitHub releases for newer versions of Sentinel Desktop.
"""

from __future__ import annotations

import json
import logging
import urllib.request

from core import __version__

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com/repos/dirtysouthalpha/sentinel-desktop/releases/latest"


def get_latest_version() -> str | None:
    """Fetch the latest release tag from GitHub. Returns None on failure."""
    try:
        req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "Sentinel-Desktop"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        tag = data.get("tag_name", "")
        return tag.lstrip("v") if tag else None
    except Exception as e:
        logger.debug("Update check failed: %s", e)
        return None


def is_update_available() -> tuple[bool, str | None]:
    """Check if a newer version is available.

    Returns:
        (is_available, latest_version)
    """
    latest = get_latest_version()
    if not latest:
        return False, None

    def parse(v: str) -> tuple:
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        return tuple(parts)

    return parse(latest) > parse(__version__), latest
