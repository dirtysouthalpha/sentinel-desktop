"""Sentinel Desktop v15.0 — Configuration persistence.

Loads/saves settings from a JSON file so agent preferences survive restarts.
Integrates with the working memory module for in-session overrides.

Usage::

    from core.config_store import ConfigStore, get_default_store

    cfg = get_default_store()
    cfg.set("llm.provider", "openai")
    val = cfg.get("llm.provider", default="anthropic")
    cfg.save()
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from core.utils import restrict_file_perms

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path.home() / ".sentinel" / "config.json"
_SINGLETON: ConfigStore | None = None
_SINGLETON_LOCK = threading.Lock()


class ConfigStore:
    """Flat/nested key-value config with JSON persistence.

    Keys use dot-notation for nesting: ``llm.provider``.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        """Initialize config store.

        Args:
            path: JSON file path. Defaults to ~/.sentinel/config.json.
        """
        self._path = Path(path) if path else _DEFAULT_PATH
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load config from disk. Silent no-op if file doesn't exist."""
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
                # Tighten perms on legacy files written before the 0600 fix;
                # this file holds LLM API keys and the JWT signing secret.
                restrict_file_perms(self._path)
                logger.debug("Config loaded from %s", self._path)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Config load failed (%s) — starting empty", exc)
                self._data = {}

    def save(self) -> bool:
        """Write config to disk. Returns True on success."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self._data, indent=2, ensure_ascii=False)
            # Atomic write: stage the payload in a uniquely-named temp, fsync,
            # lock perms, then os.replace into place. A crash mid-write leaves
            # the live config intact — the old code wrote it directly with no
            # fsync and a truncated write silently wiped every LLM API key and
            # the JWT signing secret, forcing a full re-key + re-auth.
            tmp = self._path.parent / f".config-{uuid.uuid4().hex}.tmp"
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            # Owner-only on POSIX: this file holds LLM API keys and the JWT
            # signing secret. Restrict the temp inode before the atomic replace
            # so the renamed config.json is owner-only.
            restrict_file_perms(tmp)
            tmp.replace(self._path)
            return True
        except OSError as exc:
            logger.error("Config save failed: %s", exc)
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by dot-notation key.

        Args:
            key:     Dot-separated path, e.g. ``"llm.provider"``.
            default: Returned if key not found.
        """
        with self._lock:
            parts = key.split(".")
            node = self._data
            for part in parts:
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return node

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        """Set a value by dot-notation key.

        Args:
            key:       Dot-separated path.
            value:     Any JSON-serializable value.
            auto_save: Persist to disk immediately. Default True.
        """
        with self._lock:
            parts = key.split(".")
            node = self._data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        if auto_save:
            self.save()

    def delete(self, key: str, auto_save: bool = True) -> bool:
        """Delete a key. Returns True if it existed."""
        with self._lock:
            parts = key.split(".")
            node = self._data
            for part in parts[:-1]:
                if not isinstance(node, dict) or part not in node:
                    return False
                node = node[part]
            existed = parts[-1] in node
            node.pop(parts[-1], None)
        if auto_save and existed:
            self.save()
        return existed

    def keys(self, prefix: str = "") -> list[str]:
        """Return all dot-notation keys, optionally filtered by prefix."""
        all_keys = list(_flatten(self._data))
        if prefix:
            all_keys = [k for k in all_keys if k.startswith(prefix)]
        return all_keys

    def all(self) -> dict[str, Any]:
        """Return a shallow copy of the entire config dict."""
        with self._lock:
            return dict(self._data)

    def reset(self, auto_save: bool = True) -> None:
        """Clear all config keys."""
        with self._lock:
            self._data = {}
        if auto_save:
            self.save()


def _flatten(d: dict, prefix: str = "") -> list[str]:
    """Recursively flatten nested dict into dot-notation key list."""
    keys = []
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.extend(_flatten(v, full))
        else:
            keys.append(full)
    return keys


def get_default_store() -> ConfigStore:
    """Return the process-wide singleton ConfigStore."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is None:
            _SINGLETON = ConfigStore()
        return _SINGLETON
