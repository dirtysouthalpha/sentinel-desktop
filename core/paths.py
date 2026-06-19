"""Shared storage resolver — single source of truth for Sentinel data directories.

Non-portable mode (default): %APPDATA%/SentinelDesktop on Windows,
~/.sentinel-desktop on Linux/macOS — identical to prior behavior.

Portable mode: activated when a ``portable_data/`` directory exists next to
the executable (PyInstaller bundle), or when the ``SENTINEL_PORTABLE=1``
env var is set. All storage then redirects to that folder so the entire
installation is self-contained and USB-portable.
"""

import os
import sys
from pathlib import Path


def _exe_dir() -> Path:
    """Return the directory containing the running executable (or interpreter)."""
    return Path(sys.executable).parent


def is_portable() -> bool:
    """Return True if Sentinel is running in portable mode.

    Detected by either of:
    - A ``portable_data/`` directory next to the executable.
    - ``SENTINEL_PORTABLE=1`` environment variable (useful for testing).
    """
    if os.environ.get("SENTINEL_PORTABLE", "").lower() in ("1", "true", "yes"):
        return True
    return (_exe_dir() / "portable_data").exists()


def data_dir() -> Path:
    """Return the root data directory for all Sentinel storage.

    In portable mode: ``<exe_dir>/portable_data/``.
    Otherwise: ``%APPDATA%/SentinelDesktop`` (Windows) or
    ``~/.sentinel-desktop`` (Linux/macOS).
    """
    if is_portable():
        return _exe_dir() / "portable_data"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "SentinelDesktop"
    return Path.home() / ".sentinel-desktop"


def config_path() -> Path:
    """Return the path to ``config.json``."""
    return data_dir() / "config.json"


def checkpoint_dir() -> Path:
    """Return the path to the checkpoints directory."""
    return data_dir() / "checkpoints"
