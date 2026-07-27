"""
Sentinel Desktop v30.0.0 - Plugin Marketplace.

Browse, install, and uninstall community plugins from a registry.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Restrict plugin names to a safe charset with an alphanumeric start, so
# traversal tokens (``..``, ``/``, ``\``, a leading dash, or an absolute path)
# can never form a valid name. Without this, install/uninstall joined an
# unsanitized name onto PLUGINS_DIR — a registry (or caller) supplying
# ``name="../../core/engine"`` reached write_bytes()/unlink() OUTSIDE the
# plugins directory (arbitrary file write / delete). Ported from the v22
# "Aria" lineage fix (tag archive-v22-aria-final, commit 83841b4).
_PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# A registry entry must pin its payload with a full SHA-256 hex digest.
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Cloud instance-metadata endpoints — reaching one returns cloud credentials.
# A plugin download_url comes from the (remote) registry, so a compromised
# registry could point it at the host's metadata service. Block them. Ported
# from the v22 http_client SSRF fixes (commits ea07472, ea03e99).
_METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",  # AWS / Azure / GCP IPv4 IMDS
        "169.254.170.2",  # AWS ECS task metadata
        "169.254.169.253",  # AWS IMDS (alternate)
        "metadata.google.internal",  # GCP metadata
        "metadata.azure.com",  # Azure metadata
    }
)


def _is_metadata_url(url: str) -> bool:
    """True if *url*'s host is a known cloud instance-metadata endpoint."""
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return True  # unparseable → treat as unsafe
    return host in _METADATA_HOSTS or host.startswith("169.254.")


# Only https:// downloads are installable. Blocking metadata hosts alone was
# not enough: the download_url comes from the remote registry, so `file://`
# (read any local file and install it as an importable plugin), `http://` (no
# transport integrity) and loopback/link-local hosts (SSRF into services that
# trust localhost) all had to be refused too.
_ALLOWED_SCHEMES = frozenset({"https"})


def _is_allowed_download_url(url: str) -> tuple[bool, str]:
    """Validate a registry-supplied download URL.

    Returns ``(ok, reason)``; *reason* is empty when ok.
    """
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False, "download URL is unparseable"

    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return False, f"download URL scheme {scheme or '(none)'!r} is not allowed (https only)"

    host = (parts.hostname or "").lower()
    if not host:
        return False, "download URL has no host"

    if _is_metadata_url(url):
        return False, "refusing to fetch cloud metadata endpoint"

    # Reject addresses that are only meaningful on this host / this link.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
            return False, "download URL points at localhost"
        return True, ""

    if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
        return False, f"download URL points at a local address ({host})"
    return True, ""

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
        req = urllib.request.Request(REGISTRY_URL, headers={"User-Agent": "Sentinel-Desktop"})  # noqa: S310  # https URL
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310  # scheme allowlisted
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


def _safe_plugin_path(name: str) -> Path:
    """Validate *name* and return its resolved ``<name>.py`` path under PLUGINS_DIR.

    Raises ValueError if the name is empty, contains ``..`` or path
    separators, or resolves outside PLUGINS_DIR. The regex blocks traversal
    tokens up front; the resolved-containment check is defense-in-depth.
    """
    if not isinstance(name, str) or ".." in name or not _PLUGIN_NAME_RE.match(name):
        raise ValueError(f"invalid plugin name: {name!r}")
    root = PLUGINS_DIR.resolve()
    dest = (root / f"{name}.py").resolve()
    if root != dest.parent:
        raise ValueError(f"plugin name escapes plugins dir: {name!r}")
    return dest


def install_plugin(name: str) -> dict[str, Any]:
    """Download and install a plugin from the marketplace.

    Returns dict with keys: success, message, path.
    """
    registry = fetch_registry()
    plugin = next((p for p in registry if p.name == name), None)
    if not plugin:
        return {"success": False, "message": f"Plugin '{name}' not found in registry"}

    # Validate the destination name before fetching anything: a name we would
    # never install is not worth a network round-trip, and this keeps the
    # traversal guard the first thing an attacker-controlled name meets.
    try:
        dest = _safe_plugin_path(name)
    except ValueError as e:
        return {"success": False, "message": f"Rejected plugin name: {e}"}

    if not plugin.download_url:
        return {"success": False, "message": f"Plugin '{name}' has no download URL"}

    allowed, reason = _is_allowed_download_url(plugin.download_url)
    if not allowed:
        return {"success": False, "message": f"Rejected download URL: {reason}"}

    # An unpinned plugin is an unverifiable remote code drop. Pre-v31 a
    # registry that simply omitted "sha256" silently skipped integrity
    # checking, so require it before fetching anything.
    expected_hash = (plugin.sha256 or "").strip().lower()
    if not _SHA256_RE.match(expected_hash):
        return {
            "success": False,
            "message": (
                f"Plugin '{name}' has no valid sha256 in the registry; "
                "refusing to install unverified code"
            ),
        }

    try:
        req = urllib.request.Request(plugin.download_url, headers={"User-Agent": "Sentinel-Desktop"})  # noqa: S310  # scheme allowlisted
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310  # scheme allowlisted
            content = resp.read()
    except Exception as e:
        return {"success": False, "message": f"Download failed: {e}"}

    actual_hash = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(actual_hash, expected_hash):
        return {"success": False, "message": f"SHA256 mismatch: expected {expected_hash}, got {actual_hash}"}

    # Validate it's Python source
    try:
        compile(content, name + ".py", "exec")
    except SyntaxError as e:
        return {"success": False, "message": f"Plugin has invalid Python syntax: {e}"}

    # Install to plugins directory (dest was validated up front).
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
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

    # Validate the name can't escape the plugins dir (arbitrary-delete guard).
    try:
        target = _safe_plugin_path(name)
    except ValueError as e:
        return {"success": False, "message": f"Rejected plugin name: {e}"}
    if not target.exists():
        return {"success": False, "message": f"Plugin '{name}' is not installed"}

    try:
        target.unlink()
        logger.info("Uninstalled plugin '%s'", name)
        return {"success": True, "message": f"Plugin '{name}' removed"}
    except OSError as e:
        return {"success": False, "message": f"Failed to remove: {e}"}
