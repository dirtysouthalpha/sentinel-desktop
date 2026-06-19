"""Sentinel Desktop — RBAC Authentication Module.

Role-Based Access Control with session management, API key auth,
and password hashing for the Sentinel Desktop FastAPI server.
"""

from __future__ import annotations

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
        """Return True if this role has greater or equal privilege."""
        order = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}
        return order[self] >= order[other]

    def __gt__(self, other: Role) -> bool:
        """Return True if this role has strictly greater privilege."""
        order = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}
        return order[self] > order[other]

    def __le__(self, other: Role) -> bool:
        """Return True if this role has less or equal privilege."""
        order = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}
        return order[self] <= order[other]

    def __lt__(self, other: Role) -> bool:
        """Return True if this role has strictly less privilege."""
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
        """Serialise to a JSON-friendly dict.

        Returns:
            dict[str, Any]: Dictionary containing all user fields.

        """
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
        """Deserialise from a dict (e.g. loaded from JSON).

        Args:
            data: Dictionary with user fields (username, password_hash, salt, etc.).

        Returns:
            User: Reconstructed User instance.

        """
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
# Passwords are hashed with bcrypt — the resulting string starts with
# ``$2b$`` and embeds the salt + cost factor. ``User.salt`` is an empty
# string for all users (bcrypt embeds its own salt).
#
# (v18) The legacy SHA-256(salt || password) verification path from the
# pre-bcrypt era has been removed. Any still-stored SHA-256 hashes can no
# longer be verified; affected users must reset their password. The
# transparent-upgrade-on-login code was removed along with it.
# ---------------------------------------------------------------------------


def _hash_password_bcrypt(password: str) -> str:
    """Hash *password* with bcrypt. Returns a ``$2b$...`` string."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("ascii")


def _is_bcrypt_hash(stored_hash: str) -> bool:
    """Check if a stored hash is a bcrypt-format hash (``$2a$``, ``$2b$``, ``$2y$``)."""
    return stored_hash.startswith(("$2a$", "$2b$", "$2y$"))


def _verify_password(password: str, stored_hash: str, legacy_salt: str = "") -> bool:
    """Constant-time verify *password* against a bcrypt ``stored_hash``.

    The *legacy_salt* parameter is accepted for call-site compatibility but
    is unused: v18 removed the SHA-256 verification path, and bcrypt embeds
    its own salt.
    """
    del legacy_salt  # accepted for compatibility; unused in bcrypt-only path
    if not _is_bcrypt_hash(stored_hash):
        # v18: non-bcrypt stored hashes (legacy SHA-256) are no longer verified.
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("ascii"))
    except (ValueError, TypeError):
        logger.debug("bcrypt verification failed for stored_hash prefix %s", stored_hash[:8])
        return False


def is_default_password(password: str) -> bool:
    """Return ``True`` if *password* matches ``DEFAULT_ADMIN_PASSWORD``.

    This is a fast constant-time check that callers can use to determine
    whether a user still needs to rotate the bootstrap password.

    Args:
        password: The password string to check.

    Returns:
        bool: True if the password matches the default admin password.

    """
    return secrets.compare_digest(password, DEFAULT_ADMIN_PASSWORD)


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------


class AuthManager:
    """Central authentication and authorisation manager for Sentinel Desktop.

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
        """Initialize the auth manager and load or bootstrap user data.

        Args:
            config_path: Path to the JSON file storing user records. Created
                automatically if it does not exist.

        """
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

    def _save(self) -> bool:
        """Persist all users to the JSON config file.

        Returns ``True`` on success, ``False`` on failure.
        """
        payload = {
            "users": [u.to_dict() for u in self._users.values()],
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            logger.debug("Saved %d user(s) to %s", len(self._users), self.config_path)
            return True
        except OSError as exc:
            logger.error("Failed to write user config: %s", exc)
            return False

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

        Args:
            username: Unique username for the new account.
            password: Plain-text password (will be bcrypt-hashed before storage).
            role: Role to assign (defaults to VIEWER).

        Returns:
            User: The created ``User`` instance.

        Raises:
            ValueError: If *username* already exists.

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
        """Delete a user.

        Args:
            username: The username to delete.

        Returns:
            bool: True if the user existed and was removed, False otherwise.

        """
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

        Args:
            username: Username of the user to update.

        Keyword Args:
            password: New plain-text password (will be bcrypt-hashed).
            role: New role to assign.
            regenerate_api_key: If True, generate a fresh API key.

        Returns:
            User | None: The updated ``User``, or ``None`` if not found.

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
        """Return a list of all registered users.

        Returns:
            list[User]: All user accounts.

        """
        return list(self._users.values())

    def get_user(self, username: str) -> User | None:
        """Look up a user by username.

        Args:
            username: The username to look up.

        Returns:
            User | None: The matching User, or None if not found.

        """
        return self._users.get(username)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, username: str, password: str) -> User | None:
        """Verify a username/password pair.

        Args:
            username: The username to authenticate.
            password: The plain-text password to verify.

        Returns:
            User | None: The ``User`` on success or ``None`` on failure.
            Updates ``last_login`` on success.

        If the user authenticates with ``DEFAULT_ADMIN_PASSWORD``, a warning
        is logged and the caller should check
        ``AuthManager.requires_password_rotation`` to enforce rotation.

        """
        user = self._users.get(username)
        if user is None:
            logger.warning("Authentication failed: unknown user '%s'", username)
            return None

        if not _verify_password(password, user.password_hash, user.salt):
            logger.warning("Authentication failed: bad password for '%s'", username)
            return None

        # Warn if the user is still using the bootstrap default password.
        if is_default_password(password):
            logger.warning(
                "User '%s' authenticated with the default admin password — "
                "password rotation is required before normal operation",
                username,
            )

        user.last_login = time.time()
        self._save()
        logger.info("User '%s' authenticated successfully", username)
        return user

    def authenticate_api_key(self, key: str) -> User | None:
        """Look up the user that owns *key*.

        Args:
            key: The API key string to look up.

        Returns:
            User | None: The ``User`` or ``None`` if the key is unknown.

        """
        username = self._api_key_index.get(key)
        if username is None:
            return None
        return self._users.get(username)

    def requires_password_rotation(self, username: str) -> bool:
        """Return ``True`` if *username*'s current password matches ``DEFAULT_ADMIN_PASSWORD``.

        This can be used by the API server to refuse startup or force a
        password change redirect before allowing normal operation.

        Args:
            username: The username to check.

        Returns:
            bool: True if the user's password matches the default.

        """
        user = self._users.get(username)
        if user is None:
            return False
        return _verify_password(DEFAULT_ADMIN_PASSWORD, user.password_hash, user.salt)

    def get_users_requiring_rotation(self) -> list[User]:
        """Return all users whose password still matches ``DEFAULT_ADMIN_PASSWORD``.

        Returns:
            list[User]: Users requiring password rotation.

        """
        return [
            u
            for u in self._users.values()
            if _verify_password(DEFAULT_ADMIN_PASSWORD, u.password_hash, u.salt)
        ]

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

        Args:
            user: The authenticated user.
            method: HTTP method (``GET``, ``POST``, ``PUT``, ``DELETE``, …).
            path: Request path, e.g. ``/api/goal``.

        Returns:
            bool: ``True`` if the action is permitted.

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

        Args:
            user: The authenticated user to create a session for.

        Returns:
            str: An opaque session token string.

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

    def create_jwt_session(self, user: User) -> str | None:
        """Create a signed JWT for *user* if ``SENTINEL_JWT_SECRET`` is set.

        The JWT carries ``sub`` (username), ``role``, and ``exp`` (24-hour TTL
        matching the opaque session lifetime).  Returns ``None`` when the env
        var is absent so callers can fall back to :meth:`create_session`.

        Args:
            user: The authenticated user.

        Returns:
            Compact JWT string, or ``None`` if JWT auth is not configured.
        """
        import os

        secret = os.environ.get("SENTINEL_JWT_SECRET")
        if not secret:
            return None

        from core.jwt_auth import JWTConfig, encode

        cfg = JWTConfig(
            secret_key=secret,
            issuer="sentinel",
            audience="sentinel-api",
        )
        claims = {
            "sub": user.username,
            "role": user.role if isinstance(user.role, str) else user.role.value,
            "exp": int(time.time()) + SESSION_EXPIRY_SECONDS,
        }
        token = encode(claims, cfg)
        logger.info("JWT session created for user '%s'", user.username)
        return token

    def validate_jwt_token(self, bearer_header: str | None) -> User | None:
        """Validate a ``Bearer <jwt>`` authorisation header.

        Returns the associated :class:`User` when the JWT is valid and the
        subject exists in the user store; ``None`` otherwise.  JWT auth is
        silently disabled when ``SENTINEL_JWT_SECRET`` is not set.

        Args:
            bearer_header: Raw value of the ``Authorization`` header.

        Returns:
            User or None.
        """
        import os

        secret = os.environ.get("SENTINEL_JWT_SECRET")
        if not secret or not bearer_header:
            return None
        if not bearer_header.startswith("Bearer "):
            return None

        raw_token = bearer_header[len("Bearer "):]
        try:
            from core.jwt_auth import JWTConfig, decode

            cfg = JWTConfig(
                secret_key=secret,
                issuer="sentinel",
                audience="sentinel-api",
            )
            claims = decode(raw_token, cfg)
        except Exception:  # JWTError and subclasses  # noqa: BLE001
            return None

        username = claims.get("sub")
        if not isinstance(username, str) or not username:
            return None

        user = self._users.get(username)
        if user is None:
            return None

        logger.debug("JWT auth: user '%s' validated via token", username)
        return user

    def validate_session(self, token: str) -> User | None:
        """Validate *token* and return the associated ``User``.

        Args:
            token: The session token to validate.

        Returns:
            User | None: The associated User, or None if the token is
            missing, expired, or revoked. Expired sessions are cleaned up.

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
