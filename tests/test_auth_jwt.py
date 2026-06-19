"""Tests for JWT integration in core/auth.py — v19 Fortress."""

from __future__ import annotations

import time

import pytest

from core.auth import DEFAULT_ADMIN_PASSWORD, AuthManager
from core.jwt_auth import JWTConfig, decode

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth(tmp_path):
    return AuthManager(config_path=str(tmp_path / "users.json"))


@pytest.fixture
def jwt_secret(monkeypatch):
    monkeypatch.setenv("SENTINEL_JWT_SECRET", "test-fleet-secret")
    return "test-fleet-secret"


# ---------------------------------------------------------------------------
# create_jwt_session
# ---------------------------------------------------------------------------


class TestCreateJwtSession:
    def test_returns_none_without_env(self, auth):
        user = auth.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
        assert user is not None
        result = auth.create_jwt_session(user)
        assert result is None

    def test_returns_jwt_string_with_env(self, auth, jwt_secret):
        user = auth.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
        assert user is not None
        token = auth.create_jwt_session(user)
        assert token is not None
        assert token.count(".") == 2  # header.payload.sig

    def test_jwt_contains_sub_and_role(self, auth, jwt_secret):
        user = auth.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
        assert user is not None
        token = auth.create_jwt_session(user)
        assert token is not None
        cfg = JWTConfig(
            secret_key=jwt_secret,
            issuer="sentinel",
            audience="sentinel-api",
        )
        claims = decode(token, cfg)
        assert claims["sub"] == "admin"
        assert claims["role"] == "admin"

    def test_jwt_has_exp(self, auth, jwt_secret):
        user = auth.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
        assert user is not None
        token = auth.create_jwt_session(user)
        assert token is not None
        cfg = JWTConfig(
            secret_key=jwt_secret,
            issuer="sentinel",
            audience="sentinel-api",
        )
        claims = decode(token, cfg)
        now = int(time.time())
        assert claims["exp"] > now  # future expiry

    def test_jwt_exp_24h(self, auth, jwt_secret):
        user = auth.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
        assert user is not None
        token = auth.create_jwt_session(user)
        assert token is not None
        cfg = JWTConfig(
            secret_key=jwt_secret,
            issuer="sentinel",
            audience="sentinel-api",
        )
        claims = decode(token, cfg)
        # Should be approximately 24 hours (86400s) in the future
        ttl = claims["exp"] - int(time.time())
        assert 86_390 < ttl <= 86_400 + 5  # allow small clock drift


# ---------------------------------------------------------------------------
# validate_jwt_token
# ---------------------------------------------------------------------------


class TestValidateJwtToken:
    def test_returns_none_without_env(self, auth):
        # No secret configured → always None
        result = auth.validate_jwt_token("Bearer anything")
        assert result is None

    def test_returns_none_for_none_header(self, auth, jwt_secret):
        result = auth.validate_jwt_token(None)
        assert result is None

    def test_returns_none_for_missing_bearer_prefix(self, auth, jwt_secret):
        result = auth.validate_jwt_token("Token abc")
        assert result is None

    def test_returns_user_for_valid_jwt(self, auth, jwt_secret):
        user = auth.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
        assert user is not None
        token = auth.create_jwt_session(user)
        assert token is not None
        validated = auth.validate_jwt_token(f"Bearer {token}")
        assert validated is not None
        assert validated.username == "admin"

    def test_returns_none_for_wrong_secret(self, auth, jwt_secret):
        # Token signed with a different secret
        from core.jwt_auth import JWTConfig as JC
        from core.jwt_auth import encode

        cfg = JC(secret_key="wrong-secret", issuer="sentinel", audience="sentinel-api")
        bad_token = encode({"sub": "admin", "role": "admin", "exp": int(time.time()) + 3600}, cfg)
        result = auth.validate_jwt_token(f"Bearer {bad_token}")
        assert result is None

    def test_returns_none_for_expired_token(self, auth, jwt_secret):
        from core.jwt_auth import JWTConfig as JC
        from core.jwt_auth import encode

        cfg = JC(
            secret_key=jwt_secret,
            issuer="sentinel",
            audience="sentinel-api",
            leeway_seconds=0,
        )
        expired = encode({"sub": "admin", "role": "admin", "exp": int(time.time()) - 60}, cfg)
        result = auth.validate_jwt_token(f"Bearer {expired}")
        assert result is None

    def test_returns_none_for_unknown_user(self, auth, jwt_secret):
        # JWT with valid sig but non-existent sub
        from core.jwt_auth import JWTConfig as JC
        from core.jwt_auth import encode

        cfg = JC(secret_key=jwt_secret, issuer="sentinel", audience="sentinel-api")
        token = encode({"sub": "ghost", "role": "admin", "exp": int(time.time()) + 3600}, cfg)
        result = auth.validate_jwt_token(f"Bearer {token}")
        assert result is None

    def test_returns_none_for_malformed_token(self, auth, jwt_secret):
        result = auth.validate_jwt_token("Bearer not.a.valid.jwt.here")
        assert result is None

    def test_returns_none_for_missing_sub(self, auth, jwt_secret):
        from core.jwt_auth import JWTConfig as JC
        from core.jwt_auth import encode

        cfg = JC(secret_key=jwt_secret, issuer="sentinel", audience="sentinel-api")
        token = encode({"role": "admin", "exp": int(time.time()) + 3600}, cfg)
        result = auth.validate_jwt_token(f"Bearer {token}")
        assert result is None

    def test_roundtrip_create_then_validate(self, auth, jwt_secret):
        """Full SSO path: create JWT at login, validate on subsequent request."""
        user = auth.authenticate("admin", DEFAULT_ADMIN_PASSWORD)
        assert user is not None

        jwt = auth.create_jwt_session(user)
        assert jwt is not None

        validated = auth.validate_jwt_token(f"Bearer {jwt}")
        assert validated is not None
        assert validated.username == user.username
