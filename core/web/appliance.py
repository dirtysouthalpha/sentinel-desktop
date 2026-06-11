"""Sentinel Desktop v8.0 — Self-signed certificate handler.

Manages a whitelist of hostnames where self-signed HTTPS certificate warnings
should be auto-accepted. Essential for IT admin tasks targeting network
appliances (firewalls, routers, switches) with self-signed web UIs.

The whitelist is loaded from a JSON config file. Hosts not on the whitelist
are never auto-accepted — the browser shows the warning normally.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default config path — lives alongside other state files.
DEFAULT_CERT_WHITELIST_PATH = Path("config/cert_whitelist.json")

# Default appliance hostnames that commonly use self-signed certs.
_DEFAULT_WHITELIST: list[str] = []


def load_whitelist(path: Path | str | None = None) -> list[str]:
    """Load the certificate whitelist from disk.

    Args:
        path: Path to the whitelist JSON file. Defaults to
              config/cert_whitelist.json.

    Returns:
        List of hostname strings (may be empty).
    """
    filepath = Path(path) if path else DEFAULT_CERT_WHITELIST_PATH

    if not filepath.exists():
        logger.debug("No cert whitelist at %s — using empty list", filepath)
        return list(_DEFAULT_WHITELIST)

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        hostnames = data.get("whitelist", [])
        logger.info("Loaded %d whitelisted cert hosts from %s", len(hostnames), filepath)
        return hostnames
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load cert whitelist: %s", exc)
        return list(_DEFAULT_WHITELIST)


def save_whitelist(hostnames: list[str], path: Path | str | None = None) -> None:
    """Save the certificate whitelist to disk.

    Args:
        hostnames: List of hostname strings to whitelist.
        path: Path to save to. Defaults to config/cert_whitelist.json.
    """
    filepath = Path(path) if path else DEFAULT_CERT_WHITELIST_PATH
    filepath.parent.mkdir(parents=True, exist_ok=True)

    data = {"whitelist": sorted(set(hostnames))}
    filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Saved %d whitelisted cert hosts to %s", len(data["whitelist"]), filepath)


def is_whitelisted(hostname: str, whitelist: list[str] | None = None) -> bool:
    """Check if a hostname is in the self-signed cert whitelist.

    Args:
        hostname: Hostname to check (e.g. "192.168.1.1", "firewall.local").
        whitelist: List of whitelisted hostnames. If None, loads from disk.

    Returns:
        True if the hostname is whitelisted.
    """
    if whitelist is None:
        whitelist = load_whitelist()

    # Support exact match and wildcard suffix matching (*.local → any .local host)
    hostname_lower = hostname.lower()
    for entry in whitelist:
        entry_lower = entry.lower()
        if entry_lower == hostname_lower:
            return True
        if entry_lower.startswith("*.") and hostname_lower.endswith(entry_lower[1:]):
            return True

    return False


def should_ignore_cert_errors(
    url: str,
    whitelist: list[str] | None = None,
) -> bool:
    """Determine if HTTPS errors should be ignored for a URL.

    Args:
        url: Target URL.
        whitelist: List of whitelisted hostnames. If None, loads from disk.

    Returns:
        True if the URL's host is whitelisted.
    """
    # Extract hostname from URL
    try:
        # Simple extraction — no need for urllib for this
        if "://" in url:
            host_part = url.split("://", 1)[1].split("/")[0]
        else:
            host_part = url.split("/")[0]

        # Strip port
        hostname = host_part.split(":")[0]
    except (IndexError, ValueError):  # pragma: no cover
        return False

    return is_whitelisted(hostname, whitelist)
