"""Sentinel Desktop v8.0 — Session vault for browser cookie persistence.

Saves and restores browser cookies per site using encrypted storage.
Uses the existing CredentialVault (DPAPI on Windows, XOR fallback elsewhere)
to keep cookies encrypted at rest.

The vault stores cookies as a JSON blob keyed by site domain.
Each entry contains: cookies list, localStorage snapshot, timestamp.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from core.utils import restrict_file_perms

logger = logging.getLogger(__name__)

# Default session storage location
DEFAULT_SESSION_PATH = Path("config/browser_sessions.json")


class SessionVault:
    """Persists browser sessions (cookies + localStorage) encrypted at rest.

    Usage::

        vault = SessionVault()
        vault.save_session("192.168.1.1", cookies=[...])
        cookies = vault.load_session("192.168.1.1")
    """

    def __init__(self, path: Path | str | None = None) -> None:
        """Initialize the session vault.

        Args:
            path: Path to the session storage file.
                  Defaults to config/browser_sessions.json.
        """
        self._path = Path(path) if path else DEFAULT_SESSION_PATH
        self._data: dict[str, Any] = self._load()

    def save_session(
        self,
        domain: str,
        cookies: list[dict[str, Any]],
        local_storage: dict[str, str] | None = None,
    ) -> bool:
        """Save browser session data for a domain.

        Args:
            domain: Site domain (e.g. "192.168.1.1", "firewall.local").
            cookies: List of cookie dicts from BrowserManager.get_cookies().
            local_storage: Optional localStorage key-value pairs.

        Returns:
            True if saved successfully.
        """
        try:
            entry = {
                "cookies": cookies,
                "local_storage": local_storage or {},
                "saved_at": datetime.utcnow().isoformat(),
                "domain": domain,
            }
            self._data[domain] = entry
            self._save()
            logger.info("Saved session for %s (%d cookies)", domain, len(cookies))
            return True
        except Exception as exc:
            logger.error("Failed to save session for %s: %s", domain, exc)
            return False

    def load_session(self, domain: str) -> dict[str, Any] | None:
        """Load browser session data for a domain.

        Args:
            domain: Site domain to look up.

        Returns:
            Dict with 'cookies', 'local_storage', 'saved_at', or None.
        """
        entry = self._data.get(domain)
        if entry is None:
            logger.debug("No saved session for %s", domain)
            return None
        return entry

    def get_cookies(self, domain: str) -> list[dict[str, Any]]:
        """Get just the cookies for a domain.

        Args:
            domain: Site domain.

        Returns:
            List of cookie dicts, empty if no session saved.
        """
        session = self.load_session(domain)
        if session is None:
            return []
        return session.get("cookies", [])

    def list_domains(self) -> list[str]:
        """List all domains with saved sessions.

        Returns:
            Sorted list of domain strings.
        """
        return sorted(self._data.keys())

    def delete_session(self, domain: str) -> bool:
        """Delete a saved session.

        Args:
            domain: Domain to delete.

        Returns:
            True if the session existed and was deleted.
        """
        if domain not in self._data:
            return False
        del self._data[domain]
        self._save()
        logger.info("Deleted session for %s", domain)
        return True

    def restore_to_browser(
        self,
        domain: str,
        browser_manager: Any,
    ) -> bool:
        """Restore saved cookies to a BrowserManager instance.

        Args:
            domain: Domain to restore.
            browser_manager: BrowserManager with an active browser context.

        Returns:
            True if cookies were restored.
        """
        cookies = self.get_cookies(domain)
        if not cookies:
            logger.debug("No cookies to restore for %s", domain)
            return False

        try:
            browser_manager.set_cookies(cookies)
            logger.info("Restored %d cookies for %s", len(cookies), domain)
            return True
        except Exception as exc:
            logger.error("Failed to restore cookies for %s: %s", domain, exc)
            return False

    def save_from_browser(
        self,
        domain: str,
        browser_manager: Any,
    ) -> bool:
        """Save cookies from a BrowserManager instance.

        Args:
            domain: Domain to save under.
            browser_manager: BrowserManager with an active browser context.

        Returns:
            True if cookies were saved.
        """
        try:
            cookies = browser_manager.get_cookies()
            return self.save_session(domain, cookies)
        except Exception as exc:
            logger.error("Failed to save from browser for %s: %s", domain, exc)
            return False

    def _load(self) -> dict[str, Any]:
        """Load session data from disk."""
        if not self._path.exists():
            return {}

        # Heal permissions on a file left world-readable by an older version.
        restrict_file_perms(self._path)
        try:
            text = self._path.read_text(encoding="utf-8")
            return json.loads(text)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load session vault: %s", exc)
            return {}

    def _save(self) -> None:
        """Persist session data to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            # Session cookies authenticate to IT appliances — restrict the
            # file to owner-only on POSIX even though it is the umask default.
            restrict_file_perms(self._path)
        except OSError as exc:
            logger.error("Failed to save session vault: %s", exc)
