"""Sentinel Desktop v19 — HS256 JWT Authentication Layer.

Provides JSON Web Token (JWT) encoding and decoding using only the Python
standard library (``base64``, ``hmac``, ``hashlib``, ``json``, ``time``).
The only supported signing algorithm is **HS256** (HMAC-SHA256 with a shared
secret), which is sufficient for internal fleet authentication without
introducing an external cryptography dependency.

Integration with OIDC providers
--------------------------------
External identity providers (Okta, Azure AD, Google Workspace) can issue
standard HS256 JWTs signed with a shared secret, or RS256 JWTs (which
require a future ``cryptography``-dep upgrade).  This module validates
the tokens after the OIDC flow completes and the token is presented to the
Sentinel API.

Claim conventions
-----------------
``sub``
    Subject identifier (username or user ID).
``role``
    Sentinel role string (``"admin"``, ``"operator"``, ``"viewer"``).
    Also checked in ``roles`` (list) for providers that emit arrays.
``exp``
    Expiry timestamp (Unix epoch seconds).  Required by default.
``iat``
    Issued-at timestamp.  Included in :func:`encode` outputs.
``iss``
    Issuer string.  Validated when :attr:`JWTConfig.issuer` is set.
``aud``
    Audience string.  Validated when :attr:`JWTConfig.audience` is set.

Usage::

    config = JWTConfig(secret_key="super-secret", issuer="sentinel")
    token = encode({"sub": "alice", "role": "admin"}, config)
    claims = decode(token, config)
    role = extract_role(claims)   # "admin"
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from typing import Any

_B64URL_RE = re.compile(r"^[A-Za-z0-9_\-]*={0,2}$")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class JWTError(Exception):
    """Base class for all JWT validation errors."""


class JWTMalformedError(JWTError):
    """Token cannot be parsed — wrong format or corrupted base64."""


class JWTInvalidSignatureError(JWTError):
    """HMAC signature does not match the token header + payload."""


class JWTExpiredError(JWTError):
    """Token ``exp`` claim is in the past (beyond the configured leeway)."""


class JWTClaimError(JWTError):
    """A required claim is missing or has an unexpected value (iss/aud)."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class JWTConfig:
    """Configuration for JWT encode/decode operations.

    Attributes:
        secret_key: Shared HMAC secret used to sign and verify tokens.
        algorithm: Signing algorithm. Currently only ``"HS256"`` is supported.
        issuer: Expected ``iss`` claim value. If ``None`` the issuer is not
            validated.
        audience: Expected ``aud`` claim value. If ``None`` the audience is
            not validated.
        leeway_seconds: Clock-skew tolerance in seconds when checking ``exp``.
        require_exp: If ``True`` (default), tokens without an ``exp`` claim
            are rejected.
    """

    secret_key: str
    algorithm: str = "HS256"
    issuer: str | None = None
    audience: str | None = None
    leeway_seconds: int = 30
    require_exp: bool = True

    def __post_init__(self) -> None:
        if self.algorithm != "HS256":
            raise ValueError(f"Unsupported algorithm '{self.algorithm}'. Only HS256 is supported.")
        if not self.secret_key:
            raise ValueError("secret_key must not be empty.")


# ---------------------------------------------------------------------------
# Low-level base64url helpers
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    """Encode *data* as base64url with no padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode a base64url string (with or without padding).

    Raises:
        JWTMalformedError: If the string contains non-base64url characters or
            cannot be decoded.
    """
    # Strip any existing padding before validation
    stripped = s.rstrip("=")
    if not _B64URL_RE.match(stripped):
        raise JWTMalformedError("Invalid base64url characters in token segment")
    # Restore padding
    padding = 4 - len(stripped) % 4
    padded = stripped + ("=" * padding if padding != 4 else "")
    try:
        return base64.urlsafe_b64decode(padded)
    except Exception as exc:
        raise JWTMalformedError(f"Invalid base64url encoding: {exc}") from exc


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def _sign(header_b64: str, payload_b64: str, secret: str) -> str:
    """Compute the HS256 signature for ``header_b64.payload_b64``."""
    message = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    return _b64url_encode(sig)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def encode(
    claims: dict[str, Any],
    config: JWTConfig,
    *,
    issued_at: int | None = None,
) -> str:
    """Create a signed JWT from *claims*.

    Args:
        claims: Payload claims dict.  If ``exp`` is not present and the
            caller wants the token to never expire, set ``require_exp=False``
            in *config*; otherwise include ``exp`` in *claims*.
        config: JWT configuration (secret, issuer, etc.).
        issued_at: Override the ``iat`` value (Unix seconds). Defaults to
            ``int(time.time())``.

    Returns:
        Compact JWT string (``header.payload.signature``).
    """
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = dict(claims)
    payload.setdefault("iat", issued_at if issued_at is not None else int(time.time()))
    if config.issuer and "iss" not in payload:
        payload["iss"] = config.issuer
    if config.audience and "aud" not in payload:
        payload["aud"] = config.audience

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig_b64 = _sign(header_b64, payload_b64, config.secret_key)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode(token: str, config: JWTConfig) -> dict[str, Any]:
    """Validate and decode a JWT.

    Performs the following checks in order:

    1. Token has exactly three ``"."``-separated parts.
    2. Header specifies ``alg: HS256``.
    3. HMAC signature is valid.
    4. ``exp`` is present (if ``require_exp=True``) and not expired.
    5. ``iss`` matches ``config.issuer`` (if set).
    6. ``aud`` matches ``config.audience`` (if set).

    Args:
        token: Compact JWT string.
        config: JWT configuration for validation.

    Returns:
        Decoded payload claims dict.

    Raises:
        JWTMalformedError: If the token cannot be parsed.
        JWTInvalidSignatureError: If the signature does not match.
        JWTExpiredError: If the token has expired.
        JWTClaimError: If a required claim is missing or wrong.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise JWTMalformedError(f"Expected 3 JWT parts, got {len(parts)}")

    header_b64, payload_b64, sig_b64 = parts

    # Decode header
    try:
        header = json.loads(_b64url_decode(header_b64))
    except (json.JSONDecodeError, JWTMalformedError) as exc:
        raise JWTMalformedError(f"Cannot decode JWT header: {exc}") from exc

    if header.get("alg") != "HS256":
        raise JWTMalformedError(f"Unsupported JWT algorithm: {header.get('alg')!r}")

    # Verify signature
    expected_sig = _sign(header_b64, payload_b64, config.secret_key)
    if not hmac.compare_digest(expected_sig, sig_b64):
        raise JWTInvalidSignatureError("JWT signature verification failed")

    # Decode payload
    try:
        claims: dict[str, Any] = json.loads(_b64url_decode(payload_b64))
    except (json.JSONDecodeError, JWTMalformedError) as exc:
        raise JWTMalformedError(f"Cannot decode JWT payload: {exc}") from exc

    # Check expiry
    now = int(time.time())
    if "exp" in claims:
        if now > claims["exp"] + config.leeway_seconds:
            raise JWTExpiredError(
                f"JWT expired at {claims['exp']} (now={now}, leeway={config.leeway_seconds}s)"
            )
    elif config.require_exp:
        raise JWTClaimError("JWT missing required 'exp' claim")

    # Check issuer
    if config.issuer is not None:
        if claims.get("iss") != config.issuer:
            raise JWTClaimError(
                f"JWT issuer mismatch: expected {config.issuer!r}, got {claims.get('iss')!r}"
            )

    # Check audience
    if config.audience is not None:
        aud = claims.get("aud")
        if isinstance(aud, list):
            if config.audience not in aud:
                raise JWTClaimError(f"JWT audience mismatch: expected {config.audience!r} in {aud}")
        elif aud != config.audience:
            raise JWTClaimError(f"JWT audience mismatch: expected {config.audience!r}, got {aud!r}")

    return claims


def extract_role(claims: dict[str, Any]) -> str | None:
    """Extract the Sentinel role string from *claims*.

    Checks ``role`` (string) and ``roles`` (list) in that order.  Returns
    the first value found, or ``None`` if neither claim is present.

    Args:
        claims: Decoded JWT payload dict.

    Returns:
        Role string (e.g. ``"admin"``) or ``None``.
    """
    role = claims.get("role")
    if isinstance(role, str) and role:
        return role
    roles = claims.get("roles")
    if isinstance(roles, list) and roles:
        return str(roles[0])
    return None
