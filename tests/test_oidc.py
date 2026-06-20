"""Tests for core/oidc.py — OIDC token validation and user provisioning."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.jwt_auth import JWTConfig, encode
from core.oidc import (
    OIDCClaims,
    OIDCDiscoveryError,
    OIDCNotConfiguredError,
    OIDCTokenInvalidError,
    _derive_role,
    _get_oidc_config,
    fetch_oidc_config,
    provision_user,
    validate_oidc_token,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SECRET = "test-secret-key-for-oidc"
ISSUER = "https://idp.example.com"
AUDIENCE = "sentinel-desktop"


def _make_token(
    sub: str = "user@idp",
    extra: dict[str, Any] | None = None,
    *,
    secret: str = SECRET,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    exp_offset: int = 3600,
) -> str:
    cfg = JWTConfig(secret_key=secret, issuer=issuer, audience=audience)
    claims: dict[str, Any] = {
        "sub": sub,
        "iss": issuer,
        "aud": audience,
        "exp": int(time.time()) + exp_offset,
    }
    if extra:
        claims.update(extra)
    return encode(claims, cfg)


@pytest.fixture()
def oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("SENTINEL_OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("SENTINEL_JWT_SECRET", SECRET)
    monkeypatch.delenv("SENTINEL_OIDC_DEFAULT_ROLE", raising=False)
    monkeypatch.delenv("SENTINEL_OIDC_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("SENTINEL_OIDC_ADMIN_CLAIM", raising=False)


# ---------------------------------------------------------------------------
# _get_oidc_config
# ---------------------------------------------------------------------------


class TestGetOidcConfig:
    def test_returns_tuple_when_all_set(self, oidc_env: None) -> None:
        issuer, audience, secret = _get_oidc_config()
        assert issuer == ISSUER
        assert audience == AUDIENCE
        assert secret == SECRET

    def test_raises_when_issuer_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_AUDIENCE", AUDIENCE)
        monkeypatch.setenv("SENTINEL_JWT_SECRET", SECRET)
        monkeypatch.delenv("SENTINEL_OIDC_ISSUER", raising=False)
        with pytest.raises(OIDCNotConfiguredError, match="SENTINEL_OIDC_ISSUER"):
            _get_oidc_config()

    def test_raises_when_audience_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ISSUER", ISSUER)
        monkeypatch.setenv("SENTINEL_JWT_SECRET", SECRET)
        monkeypatch.delenv("SENTINEL_OIDC_AUDIENCE", raising=False)
        with pytest.raises(OIDCNotConfiguredError, match="SENTINEL_OIDC_AUDIENCE"):
            _get_oidc_config()

    def test_raises_when_secret_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ISSUER", ISSUER)
        monkeypatch.setenv("SENTINEL_OIDC_AUDIENCE", AUDIENCE)
        monkeypatch.delenv("SENTINEL_JWT_SECRET", raising=False)
        with pytest.raises(OIDCNotConfiguredError, match="SENTINEL_JWT_SECRET"):
            _get_oidc_config()

    def test_raises_when_all_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k in ("SENTINEL_OIDC_ISSUER", "SENTINEL_OIDC_AUDIENCE", "SENTINEL_JWT_SECRET"):
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(OIDCNotConfiguredError):
            _get_oidc_config()


# ---------------------------------------------------------------------------
# _derive_role
# ---------------------------------------------------------------------------


class TestDeriveRole:
    def test_default_viewer(self, oidc_env: None) -> None:
        assert _derive_role({}) == "viewer"

    def test_default_role_env(self, oidc_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_DEFAULT_ROLE", "operator")
        assert _derive_role({}) == "operator"

    def test_role_claim_string(self, oidc_env: None) -> None:
        assert _derive_role({"role": "admin"}) == "admin"

    def test_role_claim_operator(self, oidc_env: None) -> None:
        assert _derive_role({"role": "operator"}) == "operator"

    def test_role_claim_invalid_falls_through(self, oidc_env: None) -> None:
        assert _derive_role({"role": "superuser"}) == "viewer"

    def test_roles_list(self, oidc_env: None) -> None:
        assert _derive_role({"roles": ["operator"]}) == "operator"

    def test_roles_list_first_valid(self, oidc_env: None) -> None:
        assert _derive_role({"roles": ["admin", "operator"]}) == "admin"

    def test_admin_email_allowlist(self, oidc_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ADMIN_EMAIL", "boss@corp.com,admin@corp.com")
        assert _derive_role({"email": "admin@corp.com"}) == "admin"

    def test_admin_email_case_insensitive(
        self, oidc_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ADMIN_EMAIL", "Boss@Corp.Com")
        assert _derive_role({"email": "boss@corp.com"}) == "admin"

    def test_admin_email_not_matched(self, oidc_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ADMIN_EMAIL", "other@corp.com")
        assert _derive_role({"email": "user@corp.com"}) == "viewer"

    def test_admin_claim_presence(self, oidc_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ADMIN_CLAIM", "is_admin")
        assert _derive_role({"is_admin": True}) == "admin"

    def test_admin_claim_falsy_does_not_grant(
        self, oidc_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ADMIN_CLAIM", "is_admin")
        assert _derive_role({"is_admin": False}) == "viewer"

    def test_admin_claim_absent_does_not_grant(
        self, oidc_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ADMIN_CLAIM", "is_admin")
        assert _derive_role({}) == "viewer"

    def test_email_allowlist_wins_over_role_claim(
        self, oidc_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ADMIN_EMAIL", "boss@corp.com")
        # Email allowlist is checked first, before role/roles claim.
        assert _derive_role({"email": "boss@corp.com", "role": "viewer"}) == "admin"


# ---------------------------------------------------------------------------
# validate_oidc_token
# ---------------------------------------------------------------------------


class TestValidateOidcToken:
    def test_valid_token_returns_claims(self, oidc_env: None) -> None:
        token = _make_token(sub="uid-123", extra={"email": "user@corp.com", "name": "Alice"})
        claims = validate_oidc_token(token)
        assert isinstance(claims, OIDCClaims)
        assert claims.sub == "uid-123"
        assert claims.email == "user@corp.com"
        assert claims.name == "Alice"
        assert claims.role == "viewer"

    def test_not_configured_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SENTINEL_OIDC_ISSUER", raising=False)
        monkeypatch.delenv("SENTINEL_OIDC_AUDIENCE", raising=False)
        monkeypatch.delenv("SENTINEL_JWT_SECRET", raising=False)
        with pytest.raises(OIDCNotConfiguredError):
            validate_oidc_token("any.token.here")

    def test_expired_token_raises(self, oidc_env: None) -> None:
        token = _make_token(exp_offset=-7200)
        with pytest.raises(OIDCTokenInvalidError, match="expired"):
            validate_oidc_token(token)

    def test_wrong_secret_raises(self, oidc_env: None) -> None:
        token = _make_token(secret="wrong-secret")
        with pytest.raises(OIDCTokenInvalidError):
            validate_oidc_token(token)

    def test_wrong_issuer_raises(self, oidc_env: None) -> None:
        token = _make_token(issuer="https://evil.com")
        with pytest.raises(OIDCTokenInvalidError):
            validate_oidc_token(token)

    def test_wrong_audience_raises(self, oidc_env: None) -> None:
        token = _make_token(audience="other-app")
        with pytest.raises(OIDCTokenInvalidError):
            validate_oidc_token(token)

    def test_missing_sub_raises(self, oidc_env: None) -> None:
        cfg = JWTConfig(secret_key=SECRET, issuer=ISSUER, audience=AUDIENCE)
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": int(time.time()) + 3600,
        }
        token = encode(claims, cfg)
        with pytest.raises(OIDCTokenInvalidError, match="sub"):
            validate_oidc_token(token)

    def test_role_derived_from_token(self, oidc_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        token = _make_token(extra={"role": "operator"})
        claims = validate_oidc_token(token)
        assert claims.role == "operator"

    def test_email_none_when_absent(self, oidc_env: None) -> None:
        token = _make_token()
        claims = validate_oidc_token(token)
        assert claims.email is None

    def test_name_none_when_absent(self, oidc_env: None) -> None:
        token = _make_token()
        claims = validate_oidc_token(token)
        assert claims.name is None

    def test_raw_claims_populated(self, oidc_env: None) -> None:
        token = _make_token(extra={"foo": "bar"})
        claims = validate_oidc_token(token)
        assert claims.raw.get("foo") == "bar"

    def test_garbage_token_raises(self, oidc_env: None) -> None:
        with pytest.raises(OIDCTokenInvalidError):
            validate_oidc_token("not.a.jwt")

    def test_empty_string_raises(self, oidc_env: None) -> None:
        with pytest.raises(OIDCTokenInvalidError):
            validate_oidc_token("")


# ---------------------------------------------------------------------------
# fetch_oidc_config
# ---------------------------------------------------------------------------


class TestFetchOidcConfig:
    def test_no_issuer_raises_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SENTINEL_OIDC_ISSUER", raising=False)
        with pytest.raises(OIDCNotConfiguredError):
            fetch_oidc_config()

    def test_uses_env_issuer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ISSUER", "https://idp.example.com")

        fake_response = MagicMock()
        fake_response.read.return_value = b'{"issuer": "https://idp.example.com"}'
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            doc = fetch_oidc_config()
        assert doc["issuer"] == "https://idp.example.com"

    def test_explicit_issuer_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ISSUER", "https://wrong.example.com")
        fake_response = MagicMock()
        fake_response.read.return_value = b'{"issuer": "https://explicit.example.com"}'
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            doc = fetch_oidc_config(issuer="https://explicit.example.com")
        assert doc["issuer"] == "https://explicit.example.com"

    def test_url_error_raises_discovery_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import urllib.error

        monkeypatch.setenv("SENTINEL_OIDC_ISSUER", "https://idp.example.com")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(OIDCDiscoveryError, match="reach"):
                fetch_oidc_config()

    def test_invalid_json_raises_discovery_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ISSUER", "https://idp.example.com")
        fake_response = MagicMock()
        fake_response.read.return_value = b"not-json"
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            with pytest.raises(OIDCDiscoveryError, match="JSON"):
                fetch_oidc_config()

    def test_non_object_json_raises_discovery_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTINEL_OIDC_ISSUER", "https://idp.example.com")
        fake_response = MagicMock()
        fake_response.read.return_value = b"[1, 2, 3]"
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=fake_response):
            with pytest.raises(OIDCDiscoveryError, match="object"):
                fetch_oidc_config()


# ---------------------------------------------------------------------------
# provision_user
# ---------------------------------------------------------------------------


def _make_auth_manager() -> MagicMock:
    from core.auth import Role, User

    mgr = MagicMock()
    mgr.get_user.return_value = None

    def _create_user(username: str, password: str, role: Any = Role.VIEWER) -> User:
        u = MagicMock(spec=User)
        u.username = username
        u.role = role
        return u

    mgr.create_user.side_effect = _create_user
    return mgr


class TestProvisionUser:
    def test_creates_new_user(self) -> None:
        mgr = _make_auth_manager()
        claims = OIDCClaims(sub="new-uid", email="new@corp.com", name="New", role="viewer")
        provision_user(claims, mgr)
        mgr.create_user.assert_called_once()
        args, kwargs = mgr.create_user.call_args
        assert args[0] == "new-uid"  # username = sub
        assert len(args[1]) > 10  # random unusable password

    def test_returns_existing_user_when_found(self) -> None:
        from core.auth import Role, User

        existing = MagicMock(spec=User)
        existing.username = "existing"
        existing.role = Role.VIEWER

        mgr = MagicMock()
        mgr.get_user.return_value = existing
        mgr.get_user.side_effect = [existing, existing]  # first call + after update

        claims = OIDCClaims(sub="existing", email=None, name=None, role="viewer")
        provision_user(claims, mgr)
        mgr.create_user.assert_not_called()

    def test_updates_role_when_changed(self) -> None:
        from core.auth import Role, User

        existing = MagicMock(spec=User)
        existing.username = "uid-123"
        existing.role = Role.VIEWER

        updated = MagicMock(spec=User)
        updated.username = "uid-123"
        updated.role = Role.ADMIN

        mgr = MagicMock()
        mgr.get_user.side_effect = [existing, updated]

        claims = OIDCClaims(sub="uid-123", email=None, name=None, role="admin")
        user = provision_user(claims, mgr)
        mgr.update_user.assert_called_once_with("uid-123", role=Role.ADMIN)
        assert user.role == Role.ADMIN

    def test_no_update_when_role_same(self) -> None:
        from core.auth import Role, User

        existing = MagicMock(spec=User)
        existing.username = "uid-123"
        existing.role = Role.OPERATOR

        mgr = MagicMock()
        mgr.get_user.return_value = existing

        claims = OIDCClaims(sub="uid-123", email=None, name=None, role="operator")
        provision_user(claims, mgr)
        mgr.update_user.assert_not_called()

    def test_invalid_role_in_claims_uses_viewer(self) -> None:
        from core.auth import Role

        mgr = _make_auth_manager()
        claims = OIDCClaims(sub="uid-x", email=None, name=None, role="superuser")
        provision_user(claims, mgr)
        _, kwargs = mgr.create_user.call_args
        assert kwargs.get("role") == Role.VIEWER or mgr.create_user.call_args[0][2] == Role.VIEWER


# ---------------------------------------------------------------------------
# AuthManager.provision_from_oidc integration
# ---------------------------------------------------------------------------


class TestAuthManagerProvisionFromOidc:
    def test_roundtrip(self, tmp_path: Any, oidc_env: None) -> None:
        """End-to-end: validate token → provision user → return user object."""
        from core.auth import AuthManager

        am = AuthManager(config_path=str(tmp_path / "users.json"))
        token = _make_token(sub="oidc-user", extra={"email": "oidc@corp.com", "role": "operator"})
        user = am.provision_from_oidc(token)
        assert user.username == "oidc-user"
        from core.auth import Role

        assert user.role == Role.OPERATOR

    def test_invalid_token_raises(self, tmp_path: Any, oidc_env: None) -> None:
        from core.auth import AuthManager
        from core.oidc import OIDCTokenInvalidError

        am = AuthManager(config_path=str(tmp_path / "users.json"))
        with pytest.raises(OIDCTokenInvalidError):
            am.provision_from_oidc("not.a.valid.token")

    def test_not_configured_raises(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        from core.auth import AuthManager
        from core.oidc import OIDCNotConfiguredError

        monkeypatch.delenv("SENTINEL_OIDC_ISSUER", raising=False)
        monkeypatch.delenv("SENTINEL_OIDC_AUDIENCE", raising=False)
        monkeypatch.delenv("SENTINEL_JWT_SECRET", raising=False)
        am = AuthManager(config_path=str(tmp_path / "users.json"))
        with pytest.raises(OIDCNotConfiguredError):
            am.provision_from_oidc("any.token.value")
