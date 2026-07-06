"""
Sentinel Desktop v26.0.0 - Plugin Marketplace.

Browse, install, and uninstall community plugins from a registry.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Built-in registry URL (can be overridden via env)
REGISTRY_URL = os.environ.get(
    "SENTINEL_MARKETPLACE_URL",
    "https://raw.githubusercontent.com/dirtysouthalpha/sentinel-desktop/main/plugins/registry.json",
)

# Local plugins directory
PLUGINS_DIR = Path(__file__).parent.parent / "plugins"


@dataclass
class PluginInfo:
    """Metadata for a marketplace plugin."""
    name: str
    description: str = ""
    author: str = ""
    version: str = "0.0.0"
    download_url: str = ""
    sha256: str = ""
    tags: list[str] = field(default_factory=list)
    installed: bool = False


def fetch_registry() -> list[PluginInfo]:
    """Fetch the plugin registry from the remote URL. Returns empty list on failure."""
    try:
        req = urllib.request.Request(REGISTRY_URL, headers={"User-Agent": "Sentinel-Desktop"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        plugins = []
        for entry in data.get("plugins", []):
            plugins.append(PluginInfo(
                name=entry.get("name", ""),
                description=entry.get("description", ""),
                author=entry.get("author", ""),
                version=entry.get("version", "0.0.0"),
                download_url=entry.get("download_url", ""),
                sha256=entry.get("sha256", ""),
                tags=entry.get("tags", []),
            ))
        return plugins
    except Exception as e:
        logger.warning("Failed to fetch plugin registry: %s", e)
        return []


def list_installed() -> list[str]:
    """List all installed plugin names."""
    if not PLUGINS_DIR.exists():
        return []
    installed = []
    for f in PLUGINS_DIR.glob("*.py"):
        if f.name == "__init__.py" or f.name == "template.py":
            continue
        installed.append(f.stem)
    return installed


def get_marketplace_listing() -> list[dict[str, Any]]:
    """Get full marketplace listing with install status. Returns list of dicts."""
    installed = set(list_installed())
    try:
        registry = fetch_registry()
    except Exception:
        registry = []

    # Build listing from registry
    listing = []
    for plugin in registry:
        listing.append({
            "name": plugin.name,
            "description": plugin.description,
            "author": plugin.author,
            "version": plugin.version,
            "tags": plugin.tags,
            "installed": plugin.name in installed,
            "download_url": plugin.download_url,
        })

    # Add locally installed plugins not in registry
    for name in installed:
        if not any(p["name"] == name for p in listing):
            listing.append({
                "name": name,
                "description": "Local plugin (not in registry)",
                "author": "unknown",
                "version": "local",
                "tags": [],
                "installed": True,
                "download_url": "",
            })

    return listing


def install_plugin(name: str) -> dict[str, Any]:
    """Download and install a plugin from the marketplace.

    Returns dict with keys: success, message, path.
    """
    registry = fetch_registry()
    plugin = next((p for p in registry if p.name == name), None)
    if not plugin:
        return {"success": False, "message": f"Plugin '{name}' not found in registry"}

    if not plugin.download_url:
        return {"success": False, "message": f"Plugin '{name}' has no download URL"}

    try:
        req = urllib.request.Request(plugin.download_url, headers={"User-Agent": "Sentinel-Desktop"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
    except Exception as e:
        return {"success": False, "message": f"Download failed: {e}"}

    # Verify SHA256 if provided
    if plugin.sha256:
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != plugin.sha256:
            return {"success": False, "message": f"SHA256 mismatch: expected {plugin.sha256}, got {actual_hash}"}

    # Validate it's Python source
    try:
        compile(content, name + ".py", "exec")
    except SyntaxError as e:
        return {"success": False, "message": f"Plugin has invalid Python syntax: {e}"}

    # Install to plugins directory
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    dest = PLUGINS_DIR / f"{name}.py"
    dest.write_bytes(content)

    logger.info("Installed plugin '%s' to %s", name, dest)
    return {"success": True, "message": f"Plugin '{name}' v{plugin.version} installed", "path": str(dest)}


def uninstall_plugin(name: str) -> dict[str, Any]:
    """Remove an installed plugin.

    Returns dict with keys: success, message.
    """
    # Protect built-in files
    if name in ("__init__", "template"):
        return {"success": False, "message": f"Cannot remove built-in file '{name}'"}

    target = PLUGINS_DIR / f"{name}.py"
    if not target.exists():
        return {"success": False, "message": f"Plugin '{name}' is not installed"}

    try:
        target.unlink()
        logger.info("Uninstalled plugin '%s'", name)
        return {"success": True, "message": f"Plugin '{name}' removed"}
    except OSError as e:
        return {"success": False, "message": f"Failed to remove: {e}"}
