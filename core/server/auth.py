"""API authentication and role-based access control.

Manages API keys, user sessions, and permission checks for the
Sentinel Desktop headless server. Supports multi-tenant deployments.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AUTH_FILE = Path(os.environ.get("SENTINEL_AUTH_FILE", Path.home() / ".sentinel" / "auth.json"))


class Role(Enum):
    """User roles with increasing privilege."""

    VIEWER = "viewer"  # read-only access
    OPERATOR = "operator"  # can run workflows but not manage system
    ADMIN = "admin"  # full system access
    SUPER = "super"  # can manage users and roles


class Permission:
    """Named permissions that can be checked."""

    VIEW_STATUS = "view_status"
    RUN_ACTIONS = "run_actions"
    RUN_WORKFLOWS = "run_workflows"
    MANAGE_WORKFLOWS = "manage_workflows"
    MANAGE_FLEET = "manage_fleet"
    MANAGE_USERS = "manage_users"
    MANAGE_CONFIG = "manage_config"
    VIEW_LOGS = "view_logs"
    VIEW_METRICS = "view_metrics"


# Role -> permission mapping
_ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.VIEWER: {Permission.VIEW_STATUS, Permission.VIEW_LOGS, Permission.VIEW_METRICS},
    Role.OPERATOR: {
        Permission.VIEW_STATUS,
        Permission.RUN_ACTIONS,
        Permission.RUN_WORKFLOWS,
        Permission.VIEW_LOGS,
        Permission.VIEW_METRICS,
    },
    Role.ADMIN: {
        Permission.VIEW_STATUS,
        Permission.RUN_ACTIONS,
        Permission.RUN_WORKFLOWS,
        Permission.MANAGE_WORKFLOWS,
        Permission.MANAGE_FLEET,
        Permission.MANAGE_CONFIG,
        Permission.VIEW_LOGS,
        Permission.VIEW_METRICS,
    },
    Role.SUPER: {p for p in dir(Permission) if not p.startswith("_")},
}


@dataclass
class APIKey:
    """An API key for programmatic access."""

    name: str
    key_hash: str
    role: str
    created_at: float
    last_used: float = 0.0
    expires_at: float = 0.0  # 0 = never
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "key_hash": self.key_hash,
            "role": self.role,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "expires_at": self.expires_at,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> APIKey:
        return cls(**data)


class AuthManager:
    """Manage API keys and RBAC for the Sentinel Desktop server."""

    def __init__(self, auth_file: str | Path | None = None) -> None:
        self._auth_file = Path(auth_file) if auth_file else _AUTH_FILE
        self._keys: dict[str, APIKey] = {}  # name -> key
        self._load()

    def _load(self) -> None:
        if self._auth_file.exists():
            try:
                data = json.loads(self._auth_file.read_text(encoding="utf-8"))
                for name, keydata in data.get("keys", {}).items():
                    self._keys[name] = APIKey.from_dict(keydata)
            except Exception as exc:
                logger.warning("Failed to load auth file: %s", exc)

    def _save(self) -> None:
        self._auth_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"keys": {name: k.to_dict() for name, k in self._keys.items()}}
        self._auth_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _hash_key(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def create_key(self, name: str, role: str = "operator", expires_in_days: int = 0) -> str:
        """Create a new API key. Returns the plaintext key (shown once)."""
        if name in self._keys:
            raise ValueError(f"Key '{name}' already exists")

        plaintext = "sk_sentinel_" + secrets.token_urlsafe(32)
        key_hash = self._hash_key(plaintext)
        now = time.time()

        self._keys[name] = APIKey(
            name=name,
            key_hash=key_hash,
            role=role,
            created_at=now,
            expires_at=now + (expires_in_days * 86400) if expires_in_days > 0 else 0.0,
        )
        self._save()
        logger.info("API key created: %s (role=%s)", name, role)
        return plaintext

    def revoke_key(self, name: str) -> bool:
        """Revoke an API key."""
        if name in self._keys:
            del self._keys[name]
            self._save()
            return True
        return False

    def check_key(self, key_value: str) -> APIKey | None:
        """Validate an API key and return the associated key info."""
        key_hash = self._hash_key(key_value)
        for api_key in self._keys.values():
            if hmac.compare_digest(api_key.key_hash, key_hash):
                if not api_key.enabled:
                    return None
                if api_key.expires_at > 0 and time.time() > api_key.expires_at:
                    return None
                api_key.last_used = time.time()
                self._save()
                return api_key
        return None

    def check_permission(self, key_value: str, permission: str) -> bool:
        """Check if an API key has the required permission."""
        api_key = self.check_key(key_value)
        if not api_key:
            return False
        try:
            role = Role(api_key.role)
        except ValueError:
            return False
        return permission in _ROLE_PERMISSIONS.get(role, set())

    def list_keys(self) -> list[dict[str, Any]]:
        """List all API key names and their metadata (without hashes)."""
        return [
            {"name": k.name, "role": k.role, "enabled": k.enabled, "created_at": k.created_at, "last_used": k.last_used}
            for k in self._values()
        ]

    def _values(self) -> list[APIKey]:
        return list(self._keys.values())

    def require_auth(self, permission: str = Permission.RUN_ACTIONS) -> Any:
        """Decorator factory for FastAPI endpoints."""

        def decorator(func: Any) -> Any:
            import functools

            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                # Extract authorization from request context
                request = kwargs.get("request") or (args[0] if args else None)
                auth_header = ""
                if hasattr(request, "headers"):
                    auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    key = auth_header[7:]
                    if self.check_permission(key, permission):
                        return await func(*args, **kwargs)
                from fastapi import HTTPException

                raise HTTPException(status_code=401, detail="Unauthorized")

            return wrapper

        return decorator


__all__ = ["Role", "Permission", "APIKey", "AuthManager"]
