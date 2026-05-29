"""
Sentinel Desktop — Shared utility functions used across multiple core modules.
"""

import platform
from datetime import datetime, timezone


def iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def is_windows() -> bool:
    """Return True when running on Microsoft Windows."""
    return platform.system() == "Windows"
