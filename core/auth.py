"""
Sentinel Desktop — RBAC Authentication Module
=============================================
Role-Based Access Control with session management, API key auth,
and password hashing for the Sentinel Desktop FastAPI server.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import bcrypt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SALT_LENGTH: int = 32
API_KEY_LENGTH: int = 32  # secrets.token_hex(32) → 64-char hex string
SESSION_EXPIRY_SECONDS: int = 86_400  # 24 hours
DEFAULT_ADMIN_USERNAME: str = "admin"
DEFAULT_ADMIN_PASSWORD: str = "[REDACTED]"  # noqa: S105


# ---------------------------------------------------------------------------
# Role Enum & Permission Tables
# ---------------------------------------------------------------------------


class Role(str, Enum):
    """User roles ordered by ascending privilege."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"

    def __ge__(self, other: Role) -> bool:
        order = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}
        return order[self] >= order[other]

    def __gt__(self, other: Role) -> bool:
        order = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}
        return order[self] > order[other]

    def __le__(self, other: Role) -> bool:
        order = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}
        return order[self] <= order[other]

    def __lt__(self, other: Role) -> bool:
        order = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}
        return order[self] < order[other]


# OPERATOR-allowed POST path prefixes (checked with startswith)
_OPERATOR_POST_PREFIXES: tuple[str, ...] = (
    "/api/goal",
    "/api/command",
    "/api/stop",
    "/api/scripts",
    "/api/run",
)

# HTTP methods a VIEWER may use on any path
_VIEWER_METHODS: frozenset = frozenset({"GET", "HEAD", "OPTIONS"})


# ---------------------------------------------------------------------------
# User Data Class
# ---------------------------------------------------------------------------


@dataclass
class User:
    """Represents a single user account."""

    username: str
    password_hash: str
    salt: str
    role: str  # stored as string for JSON serialisation
    api_key: str
    created: float  # unix timestamp
    last_login: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "salt": self.salt,
            "role": self.role,
            "api_key": self.api_key,
            "created": self.created,
            "last_login": self.last_login,
        }

    @classmethod
    def from_dict(cls: type[User], data: dict[str, Any]) -> User:
        """Deserialise from a dict (e.g. loaded from JSON)."""
        return cls(
            username=data["username"],
            password_hash=data["password_hash"],
            salt=data["salt"],
            role=data["role"],
            api_key=data["api_key"],
            created=data["created"],
            last_login=data.get("last_login"),
        )


# ---------------------------------------------------------------------------
# Password Helpers
#
# New users are hashed with bcrypt — the resulting string starts with
# ``$2b$`` and embeds the salt + cost factor. ``User.salt`` becomes an
# empty string for these users.
#
# Legacy users from the pre-bcrypt era use SHA-256(salt || password)
# stored as a 64-char hex digest with a separate hex salt. They continue
# to verify via _verify_password, and on the next successful login the
# hash is transparently upgraded to bcrypt.
# ---------------------------------------------------------------------------


def _generate_salt() -> str:
    """Return a hex-encoded random salt. Kept for legacy callers only."""
    return secrets.token_hex(SALT_LENGTH)


def _hash_password(password: str, salt: str) -> str:
    """Hash *password* with *salt* using SHA-256 (legacy verification path)."""
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def _hash_password_bcrypt(password: str) -> str:
    """Hash *password* with bcrypt. Returns a ``$2b$...`` string."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("ascii")


def _is_bcrypt_hash(stored_hash: str) -> bool:
    """``True`` for bcrypt-format hashes (``$2a$``, ``$2b$``, ``$2y$``)."""
    return stored_hash.startswith(("$2a$", "$2b$", "$2y$"))


def _verify_password(password: str, stored_hash: str, legacy_salt: str = "") -> bool:
    """Constant-time verify *password* against a bcrypt or legacy SHA-256 hash."""
    if _is_bcrypt_hash(stored_hash):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("ascii"))
        except (ValueError, TypeError):
            logger.debug("bcrypt verification failed for stored_hash prefix %s", stored_hash[:8])
            return False
    legacy = _hash_password(password, legacy_salt)
    return secrets.compare_digest(legacy, stored_hash)


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------


class AuthManager:
    """
    Central authentication and authorisation manager for Sentinel Desktop.

    Features
    --------
    * User CRUD backed by a JSON file
    * Password verification (bcrypt; transparent rehash from legacy SHA-256
      on next successful login)
    * API-key based authentication
    * Role-based permission checks (VIEWER / OPERATOR / ADMIN)
    * Time-limited session tokens with create / validate / revoke lifecycle
    """

    def __init__(self, config_path: str = "config/users.json") -> None:
        self.config_path: Path = Path(config_path)
        self._users: dict[str, User] = {}  # username → User
        self._api_key_index: dict[str, str] = {}  # api_key → username
        self._sessions: dict[str, dict[str, Any]] = {}  # token → session info

        # Ensure parent directory exists
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("Failed to create config directory %s", self.config_path.parent)

        # Load existing data or bootstrap with the default admin
        self._load()
        if not self._users:
            logger.info("No users found — creating default admin account")
            self.create_user(
                username=DEFAULT_ADMIN_USERNAME,
                password=DEFAULT_ADMIN_PASSWORD,
                role=Role.ADMIN,
            )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load users from the JSON config file."""
        if not self.config_path.exists():
            logger.debug("Config file %s does not exist yet", self.config_path)
            return

        try:
            with open(self.config_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read user config: %s", exc)
            return

        for user_dict in data.get("users", []):
            user = User.from_dict(user_dict)
            self._users[user.username] = user
            self._api_key_index[user.api_key] = user.username

        logger.info("Loaded %d user(s) from %s", len(self._users), self.config_path)

    def _save(self) -> None:
        """Persist all users to the JSON config file."""
        payload = {
            "users": [u.to_dict() for u in self._users.values()],
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            logger.debug("Saved %d user(s) to %s", len(self._users), self.config_path)
        except OSError as exc:
            logger.error("Failed to write user config: %s", exc)

    # ------------------------------------------------------------------
    # User CRUD
    # ------------------------------------------------------------------

    def create_user(
        self,
        username: str,
        password: str,
        role: Role = Role.VIEWER,
    ) -> User:
        """Create a new user and persist to disk.

        Returns the created ``User`` instance.

        Raises
        ------
        ValueError
            If *username* already exists.
        """
        if username in self._users:
            raise ValueError(f"User '{username}' already exists")

        user = User(
            username=username,
            password_hash=_hash_password_bcrypt(password),
            salt="",  # bcrypt embeds the salt; field kept for legacy compat
            role=role.value,
            api_key=secrets.token_hex(API_KEY_LENGTH),
            created=time.time(),
            last_login=None,
        )
        self._users[username] = user
        self._api_key_index[user.api_key] = username
        self._save()
        logger.info("Created user '%s' with role %s", username, role.value)
        return user

    def delete_user(self, username: str) -> bool:
        """Delete a user. Returns ``True`` if the user existed and was removed."""
        user = self._users.pop(username, None)
        if user is None:
            return False

        # Clean up API-key index
        self._api_key_index.pop(user.api_key, None)

        # Revoke any active sessions for this user
        tokens_to_revoke = [
            tok for tok, sess in self._sessions.items() if sess.get("username") == username
        ]
        for tok in tokens_to_revoke:
            del self._sessions[tok]

        self._save()
        logger.info("Deleted user '%s'", username)
        return True

    def update_user(
        self,
        username: str,
        *,
        password: str | None = None,
        role: Role | None = None,
        regenerate_api_key: bool = False,
    ) -> User | None:
        """Update mutable fields of an existing user.

        Returns the updated ``User``, or ``None`` if the user was not found.
        """
        user = self._users.get(username)
        if user is None:
            return None

        if password is not None:
            user.password_hash = _hash_password_bcrypt(password)
            user.salt = ""

        if role is not None:
            user.role = role.value

        if regenerate_api_key:
            self._api_key_index.pop(user.api_key, None)
            user.api_key = secrets.token_hex(API_KEY_LENGTH)
            self._api_key_index[user.api_key] = username

        self._save()
        logger.info("Updated user '%s'", username)
        return user

    def list_users(self) -> list[User]:
        """Return a list of all registered users."""
        return list(self._users.values())

    def get_user(self, username: str) -> User | None:
        """Look up a user by username."""
        return self._users.get(username)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, username: str, password: str) -> User | None:
        """Verify a username/password pair.

        Returns the ``User`` on success or ``None`` on failure.
        Updates ``last_login`` on success.
        """
        user = self._users.get(username)
        if user is None:
            logger.warning("Authentication failed: unknown user '%s'", username)
            return None

        if not _verify_password(password, user.password_hash, user.salt):
            logger.warning("Authentication failed: bad password for '%s'", username)
            return None

        # Transparently upgrade legacy SHA-256 hashes to bcrypt on first
        # successful login so the at-rest hash strengthens over time.
        if not _is_bcrypt_hash(user.password_hash):
            user.password_hash = _hash_password_bcrypt(password)
            user.salt = ""
            logger.info("Upgraded user '%s' hash from legacy SHA-256 to bcrypt", username)

        user.last_login = time.time()
        self._save()
        logger.info("User '%s' authenticated successfully", username)
        return user

    def authenticate_api_key(self, key: str) -> User | None:
        """Look up the user that owns *key*.

        Returns the ``User`` or ``None`` if the key is unknown.
        """
        username = self._api_key_index.get(key)
        if username is None:
            return None
        return self._users.get(username)

    # ------------------------------------------------------------------
    # Authorisation / Permission Checks
    # ------------------------------------------------------------------

    def check_permission(
        self,
        user: User,
        method: str,
        path: str,
    ) -> bool:
        """Decide whether *user* is allowed to perform *method* on *path*.

        Parameters
        ----------
        user : User
            The authenticated user.
        method : str
            HTTP method (``GET``, ``POST``, ``PUT``, ``DELETE``, …).
        path : str
            Request path, e.g. ``/api/goal``.

        Returns
        -------
        bool
            ``True`` if the action is permitted.
        """
        method = method.upper()
        role = Role(user.role)

        # ADMIN — everything allowed
        if role == Role.ADMIN:
            return True

        # VIEWER — read-only methods on any path
        if role == Role.VIEWER:
            return method in _VIEWER_METHODS

        # OPERATOR — all reads + specific POST endpoints
        if method in _VIEWER_METHODS:
            return True

        if method == "POST":
            return any(path.startswith(prefix) for prefix in _OPERATOR_POST_PREFIXES)

        # All other methods (PUT, DELETE, PATCH, …) require ADMIN
        return False

    # ------------------------------------------------------------------
    # Session Management
    # ------------------------------------------------------------------

    def create_session(self, user: User) -> str:
        """Create a new session token for *user*.

        Returns an opaque token string.
        """
        token = secrets.token_urlsafe(48)
        now = time.time()
        self._sessions[token] = {
            "username": user.username,
            "role": user.role,
            "created_at": now,
            "expires_at": now + SESSION_EXPIRY_SECONDS,
        }
        logger.info("Session created for user '%s'", user.username)
        return token

    def validate_session(self, token: str) -> User | None:
        """Validate *token* and return the associated ``User``.

        Returns ``None`` if the token is missing, expired, or revoked.
        Expired sessions are cleaned up automatically.
        """
        session = self._sessions.get(token)
        if session is None:
            return None

        now = time.time()
        if now > session["expires_at"]:
            # Session expired — remove it
            del self._sessions[token]
            logger.info(
                "Session for '%s' expired and was removed",
                session["username"],
            )
            return None

        # Optionally refresh expiry on activity (sliding window)
        session["expires_at"] = now + SESSION_EXPIRY_SECONDS

        return self._users.get(session["username"])

    def revoke_session(self, token: str) -> bool:
        """Revoke a session token. Returns ``True`` if it existed."""
        if token in self._sessions:
            username = self._sessions[token]["username"]
            del self._sessions[token]
            logger.info("Session revoked for user '%s'", username)
            return True
        return False

    def revoke_all_sessions(self, username: str) -> int:
        """Revoke every session belonging to *username*.

        Returns the number of sessions revoked.
        """
        to_remove = [
            tok for tok, sess in self._sessions.items() if sess.get("username") == username
        ]
        for tok in to_remove:
            del self._sessions[tok]
        logger.info("Revoked %d session(s) for user '%s'", len(to_remove), username)
        return len(to_remove)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_session_info(self, token: str) -> dict[str, Any] | None:
        """Return raw session metadata (for debugging) or ``None``."""
        return self._sessions.get(token)

    def active_session_count(self) -> int:
        """Return the number of currently active sessions."""
        return len(self._sessions)

    @staticmethod
    def hash_password(password: str) -> str:
        """Public helper to hash a password with bcrypt."""
        return _hash_password_bcrypt(password)

    @staticmethod
    def verify_password(password: str, stored_hash: str, legacy_salt: str = "") -> bool:
        """Public helper to verify a password against a stored hash."""
        return _verify_password(password, stored_hash, legacy_salt)
