"""Sentinel Desktop v19 — OIDC Token Validation (stdlib-only).

Validates OIDC id_tokens from providers that use HS256 (shared-secret)
signing.  RS256 (asymmetric) providers are NOT supported without the
``cryptography`` package — that is an intentional constraint to keep the
dependency footprint minimal.

Supported flow::

    1. External OIDC provider (Okta, Azure AD with HS256 client secret,
       Keycloak symmetric keys) issues an id_token to the client.
    2. Client POSTs the id_token to Sentinel's /auth/oidc/token endpoint.
    3. Sentinel validates the token via :func:`validate_oidc_token` and
       extracts :class:`OIDCClaims`.
    4. The caller (API layer) calls :func:`provision_user` to auto-create
       or look up a local Sentinel user, then issues a Sentinel session.

Provider configuration (environment variables)::

    SENTINEL_OIDC_ISSUER       — expected ``iss`` claim (required)
    SENTINEL_OIDC_AUDIENCE     — expected ``aud`` claim (required)
    SENTINEL_JWT_SECRET        — shared HS256 secret (required)
    SENTINEL_OIDC_DEFAULT_ROLE — role for newly provisioned users (default: "viewer")
    SENTINEL_OIDC_ADMIN_EMAIL  — comma-separated emails that receive the admin role
    SENTINEL_OIDC_ADMIN_CLAIM  — claim name whose presence grants admin role

OIDC discovery (optional)::

    :func:`fetch_oidc_config` can fetch a provider's
    ``/.well-known/openid-configuration`` document for diagnostic purposes.
    Sentinel does **not** use the JWKS URI because we only support HS256
    (symmetric key), so no key-fetch round-trip is needed at token validation
    time.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from core.jwt_auth import JWTConfig, JWTError, decode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_ROLE = "viewer"
_CONNECT_TIMEOUT = 10  # seconds for discovery document fetch


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OIDCError(Exception):
    """Base exception for OIDC validation errors."""


class OIDCNotConfigured(OIDCError):
    """Required environment variables are missing."""


class OIDCTokenInvalid(OIDCError):
    """Token could not be validated (expired, bad sig, wrong claims)."""


class OIDCDiscoveryError(OIDCError):
    """Discovery document could not be fetched or parsed."""


# ---------------------------------------------------------------------------
# Claims data class
# ---------------------------------------------------------------------------


@dataclass
class OIDCClaims:
    """Extracted and validated claims from an OIDC id_token.

    Attributes:
        sub: Subject identifier (unique user ID from the IdP).
        email: User's email address (may be absent from some providers).
        name: Display name from the IdP (may be absent).
        role: Sentinel role derived from token claims or default.
        raw: Full decoded claims dict.
    """

    sub: str
    email: str | None
    name: str | None
    role: str
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _get_oidc_config() -> tuple[str, str, str]:
    """Read required OIDC env vars.

    Returns:
        Tuple of (issuer, audience, jwt_secret).

    Raises:
        OIDCNotConfigured: If any required variable is missing.
    """
    issuer = os.environ.get("SENTINEL_OIDC_ISSUER", "").strip()
    audience = os.environ.get("SENTINEL_OIDC_AUDIENCE", "").strip()
    secret = os.environ.get("SENTINEL_JWT_SECRET", "").strip()

    missing = [
        name
        for name, val in [
            ("SENTINEL_OIDC_ISSUER", issuer),
            ("SENTINEL_OIDC_AUDIENCE", audience),
            ("SENTINEL_JWT_SECRET", secret),
        ]
        if not val
    ]
    if missing:
        raise OIDCNotConfigured(f"OIDC not configured — missing env vars: {', '.join(missing)}")
    return issuer, audience, secret


def _derive_role(claims: dict[str, Any]) -> str:
    """Derive a Sentinel role from OIDC claims.

    Checks, in order:

    1. ``SENTINEL_OIDC_ADMIN_EMAIL`` — comma-separated list of emails that
       receive the ``admin`` role.
    2. ``SENTINEL_OIDC_ADMIN_CLAIM`` — name of a claim whose *presence* (any
       truthy value) grants the ``admin`` role.
    3. The ``role`` / ``roles`` claims in the token itself.
    4. ``SENTINEL_OIDC_DEFAULT_ROLE`` env var (default ``"viewer"``).

    Args:
        claims: Decoded JWT payload.

    Returns:
        Sentinel role string.
    """
    email = (claims.get("email") or "").lower().strip()

    # 1. Admin email allowlist
    admin_emails_raw = os.environ.get("SENTINEL_OIDC_ADMIN_EMAIL", "")
    if admin_emails_raw and email:
        admin_emails = {e.strip().lower() for e in admin_emails_raw.split(",")}
        if email in admin_emails:
            return "admin"

    # 2. Admin claim
    admin_claim = os.environ.get("SENTINEL_OIDC_ADMIN_CLAIM", "").strip()
    if admin_claim and claims.get(admin_claim):
        return "admin"

    # 3. Role/roles claim in token
    role_claim = claims.get("role")
    if isinstance(role_claim, str) and role_claim in ("admin", "operator", "viewer"):
        return role_claim
    roles_claim = claims.get("roles")
    if isinstance(roles_claim, list):
        for r in roles_claim:
            if isinstance(r, str) and r in ("admin", "operator", "viewer"):
                return r

    # 4. Default
    return os.environ.get("SENTINEL_OIDC_DEFAULT_ROLE", _DEFAULT_ROLE).strip() or _DEFAULT_ROLE


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


def validate_oidc_token(id_token: str) -> OIDCClaims:
    """Validate an OIDC id_token and extract Sentinel claims.

    The token must be HS256-signed with the shared secret in
    ``SENTINEL_JWT_SECRET``, issued by ``SENTINEL_OIDC_ISSUER``, and
    addressed to ``SENTINEL_OIDC_AUDIENCE``.

    Args:
        id_token: Compact JWT id_token string from the OIDC provider.

    Returns:
        :class:`OIDCClaims` with extracted and derived fields.

    Raises:
        OIDCNotConfigured: If required env vars are absent.
        OIDCTokenInvalid: If the token is invalid, expired, or mismatched.
    """
    issuer, audience, secret = _get_oidc_config()

    cfg = JWTConfig(
        secret_key=secret,
        issuer=issuer,
        audience=audience,
        require_exp=True,
    )
    try:
        claims = decode(id_token, cfg)
    except (JWTError, UnicodeDecodeError, ValueError) as exc:
        raise OIDCTokenInvalid(f"OIDC token validation failed: {exc}") from exc

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise OIDCTokenInvalid("OIDC token missing required 'sub' claim")

    email_raw = claims.get("email")
    email = str(email_raw).strip() if isinstance(email_raw, str) else None
    name_raw = claims.get("name")
    name = str(name_raw).strip() if isinstance(name_raw, str) else None
    role = _derive_role(claims)

    logger.info("OIDC token validated for sub=%s role=%s", sub, role)
    return OIDCClaims(sub=sub, email=email, name=name, role=role, raw=claims)


# ---------------------------------------------------------------------------
# OIDC discovery (diagnostic / informational)
# ---------------------------------------------------------------------------


def fetch_oidc_config(issuer: str | None = None) -> dict[str, Any]:
    """Fetch the OIDC provider's well-known discovery document.

    This is informational — Sentinel does not use the JWKS URI because
    only HS256 (symmetric) tokens are supported.

    Args:
        issuer: Base URL of the OIDC provider.  Defaults to
            ``SENTINEL_OIDC_ISSUER`` env var.

    Returns:
        Parsed JSON discovery document as a dict.

    Raises:
        OIDCNotConfigured: If no issuer is provided or configured.
        OIDCDiscoveryError: If the document cannot be fetched or parsed.
    """
    base = (issuer or os.environ.get("SENTINEL_OIDC_ISSUER", "")).rstrip("/")
    if not base:
        raise OIDCNotConfigured("SENTINEL_OIDC_ISSUER is not set")

    url = f"{base}/.well-known/openid-configuration"
    logger.debug("Fetching OIDC discovery document from %s", url)
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise OIDCDiscoveryError(f"Cannot reach OIDC discovery endpoint: {exc}") from exc

    try:
        doc: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise OIDCDiscoveryError(f"Discovery document is not valid JSON: {exc}") from exc

    if not isinstance(doc, dict):
        raise OIDCDiscoveryError("Discovery document root is not a JSON object")

    logger.info(
        "OIDC discovery: issuer=%s, algorithms=%s",
        doc.get("issuer"),
        doc.get("id_token_signing_alg_values_supported"),
    )
    return doc


# ---------------------------------------------------------------------------
# User provisioning helper
# ---------------------------------------------------------------------------


def provision_user(
    claims: OIDCClaims,
    auth_manager: Any,
) -> Any:
    """Look up or create a local Sentinel user from OIDC claims.

    Uses ``claims.sub`` as the canonical username.  If the user already
    exists, their role is updated to match the OIDC-derived role.  If they
    do not exist, a new account is created with a random password (the
    account is OIDC-only — local password login will fail unless the admin
    resets it).

    Args:
        claims: Validated OIDC claims from :func:`validate_oidc_token`.
        auth_manager: :class:`~core.auth.AuthManager` instance.

    Returns:
        The local :class:`~core.auth.User` record.
    """
    from core.auth import Role

    username = claims.sub
    existing = auth_manager.get_user(username)
    if existing is not None:
        # Update role if OIDC says it changed.
        try:
            current_role = Role(existing.role)
            desired_role = Role(claims.role)
        except ValueError:
            desired_role = Role.VIEWER
            current_role = Role.VIEWER

        if current_role != desired_role:
            auth_manager.update_user(username, role=desired_role)
            logger.info(
                "OIDC provisioning: updated role for '%s' → %s", username, desired_role.value
            )
        return auth_manager.get_user(username)

    # New user — generate a random unusable password so local login won't work.
    import secrets as _secrets

    random_pw = _secrets.token_urlsafe(32)
    try:
        role_enum = Role(claims.role)
    except ValueError:
        role_enum = Role.VIEWER

    user = auth_manager.create_user(username, random_pw, role=role_enum)
    logger.info("OIDC provisioning: created new user '%s' with role %s", username, role_enum.value)
    return user
