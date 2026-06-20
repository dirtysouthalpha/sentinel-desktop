"""Tests for core/jwt_auth.py — HS256 JWT Authentication Layer (v19)."""

from __future__ import annotations

import time

import pytest

from core.jwt_auth import (
    JWTClaimError,
    JWTConfig,
    JWTError,
    JWTExpiredError,
    JWTInvalidSignatureError,
    JWTMalformedError,
    _b64url_decode,
    _b64url_encode,
    decode,
    encode,
    extract_role,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg() -> JWTConfig:
    return JWTConfig(secret_key="test-secret-key")


@pytest.fixture
def cfg_full() -> JWTConfig:
    return JWTConfig(
        secret_key="full-secret",
        issuer="sentinel",
        audience="api",
        leeway_seconds=0,
    )


def _future_exp(seconds: int = 3600) -> int:
    return int(time.time()) + seconds


def _past_exp(seconds: int = 3600) -> int:
    return int(time.time()) - seconds


# ---------------------------------------------------------------------------
# JWTConfig
# ---------------------------------------------------------------------------


class TestJWTConfig:
    def test_default_algorithm(self):
        cfg = JWTConfig(secret_key="s")
        assert cfg.algorithm == "HS256"

    def test_empty_secret_raises(self):
        with pytest.raises(ValueError, match="secret_key"):
            JWTConfig(secret_key="")

    def test_unsupported_algorithm_raises(self):
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            JWTConfig(secret_key="s", algorithm="RS256")

    def test_valid_config(self):
        cfg = JWTConfig(secret_key="s", issuer="iss", audience="aud", leeway_seconds=60)
        assert cfg.issuer == "iss"
        assert cfg.audience == "aud"
        assert cfg.leeway_seconds == 60


# ---------------------------------------------------------------------------
# Base64url helpers
# ---------------------------------------------------------------------------


class TestBase64Helpers:
    def test_encode_decode_roundtrip(self):
        data = b"hello world \x00\xff"
        assert _b64url_decode(_b64url_encode(data)) == data

    def test_no_padding_in_encoded(self):
        encoded = _b64url_encode(b"x")
        assert "=" not in encoded

    def test_urlsafe_chars(self):
        # Standard base64 uses + and /; urlsafe uses - and _
        encoded = _b64url_encode(b"\xfb\xfc\xfd\xfe\xff")
        assert "+" not in encoded
        assert "/" not in encoded

    def test_decode_invalid_raises(self):
        with pytest.raises(JWTMalformedError):
            _b64url_decode("not!valid@base64#")

    def test_decode_with_or_without_padding(self):
        data = b"test"
        encoded = _b64url_encode(data)
        # With padding
        assert _b64url_decode(encoded + "==") == data
        # Without padding
        assert _b64url_decode(encoded) == data


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------


class TestEncode:
    def test_returns_three_parts(self, cfg):
        token = encode({"sub": "user", "exp": _future_exp()}, cfg)
        assert token.count(".") == 2

    def test_iat_added_automatically(self, cfg):
        token = encode({"sub": "u", "exp": _future_exp()}, cfg)
        claims = decode(token, cfg)
        assert "iat" in claims

    def test_iss_added_from_config(self):
        cfg = JWTConfig(secret_key="s", issuer="sentinel")
        token = encode({"sub": "u", "exp": _future_exp()}, cfg)
        claims = decode(token, cfg)
        assert claims["iss"] == "sentinel"

    def test_aud_added_from_config(self):
        cfg = JWTConfig(secret_key="s", audience="api")
        token = encode({"sub": "u", "exp": _future_exp()}, cfg)
        claims = decode(token, cfg)
        assert claims["aud"] == "api"

    def test_caller_iss_not_overwritten(self):
        cfg = JWTConfig(secret_key="s", issuer="default")
        token = encode({"sub": "u", "exp": _future_exp(), "iss": "custom"}, cfg)
        # decode with no issuer check so we can read the raw value
        no_check = JWTConfig(secret_key="s")
        claims = decode(token, no_check)
        assert claims["iss"] == "custom"

    def test_issued_at_override(self, cfg):
        custom_iat = 1_000_000
        token = encode({"sub": "u", "exp": _future_exp()}, cfg, issued_at=custom_iat)
        no_check = JWTConfig(secret_key="test-secret-key")
        claims = decode(token, no_check)
        assert claims["iat"] == custom_iat


# ---------------------------------------------------------------------------
# Decode — valid tokens
# ---------------------------------------------------------------------------


class TestDecodeValid:
    def test_roundtrip(self, cfg):
        original = {"sub": "alice", "role": "admin", "exp": _future_exp()}
        token = encode(original, cfg)
        claims = decode(token, cfg)
        assert claims["sub"] == "alice"
        assert claims["role"] == "admin"

    def test_within_leeway(self):
        cfg = JWTConfig(secret_key="s", leeway_seconds=30)
        # Expired 10 seconds ago — within 30s leeway
        token = encode({"sub": "u", "exp": _past_exp(10)}, cfg)
        claims = decode(token, cfg)
        assert claims["sub"] == "u"

    def test_no_exp_when_not_required(self):
        cfg = JWTConfig(secret_key="s", require_exp=False)
        token = encode({"sub": "u"}, cfg)
        claims = decode(token, cfg)
        assert claims["sub"] == "u"

    def test_audience_list(self):
        cfg = JWTConfig(secret_key="s", audience="api", require_exp=False)
        token = encode({"sub": "u", "aud": ["api", "extra"]}, cfg)
        claims = decode(token, cfg)
        assert claims["sub"] == "u"

    def test_extra_claims_preserved(self, cfg):
        token = encode({"sub": "u", "exp": _future_exp(), "custom": "value"}, cfg)
        claims = decode(token, cfg)
        assert claims["custom"] == "value"


# ---------------------------------------------------------------------------
# Decode — error cases
# ---------------------------------------------------------------------------


class TestDecodeErrors:
    def test_wrong_number_of_parts(self, cfg):
        with pytest.raises(JWTMalformedError):
            decode("only.two", cfg)

    def test_too_many_parts(self, cfg):
        with pytest.raises(JWTMalformedError):
            decode("a.b.c.d", cfg)

    def test_invalid_base64_header(self, cfg):
        with pytest.raises(JWTMalformedError):
            decode("!!not-b64!!.payload.sig", cfg)

    def test_wrong_secret_raises_invalid_sig(self, cfg):
        token = encode({"sub": "u", "exp": _future_exp()}, cfg)
        wrong_cfg = JWTConfig(secret_key="wrong-secret")
        with pytest.raises(JWTInvalidSignatureError):
            decode(token, wrong_cfg)

    def test_tampered_payload_raises_invalid_sig(self, cfg):
        token = encode({"sub": "u", "exp": _future_exp()}, cfg)
        parts = token.split(".")
        # Corrupt the payload by appending a char
        parts[1] = parts[1] + "x"
        tampered = ".".join(parts)
        with pytest.raises(JWTInvalidSignatureError):
            decode(tampered, cfg)

    def test_expired_token_raises(self):
        cfg = JWTConfig(secret_key="s", leeway_seconds=0)
        token = encode({"sub": "u", "exp": _past_exp(10)}, cfg)
        with pytest.raises(JWTExpiredError):
            decode(token, cfg)

    def test_missing_exp_when_required(self):
        cfg = JWTConfig(secret_key="s", require_exp=True)
        token = encode({"sub": "u"}, cfg)
        with pytest.raises(JWTClaimError, match="exp"):
            decode(token, cfg)

    def test_wrong_issuer(self):
        cfg = JWTConfig(secret_key="s", issuer="expected", require_exp=False)
        token = encode({"sub": "u", "iss": "wrong"}, cfg)
        with pytest.raises(JWTClaimError, match="issuer"):
            decode(token, cfg)

    def test_missing_issuer_when_required(self):
        cfg = JWTConfig(secret_key="s", issuer="expected", require_exp=False)
        token = encode({"sub": "u"}, JWTConfig(secret_key="s", require_exp=False))
        with pytest.raises(JWTClaimError, match="issuer"):
            decode(token, cfg)

    def test_wrong_audience_string(self):
        cfg = JWTConfig(secret_key="s", audience="api", require_exp=False)
        token = encode({"sub": "u", "aud": "other"}, JWTConfig(secret_key="s", require_exp=False))
        with pytest.raises(JWTClaimError, match="audience"):
            decode(token, cfg)

    def test_wrong_audience_list(self):
        cfg = JWTConfig(secret_key="s", audience="api", require_exp=False)
        token = encode(
            {"sub": "u", "aud": ["other1", "other2"]}, JWTConfig(secret_key="s", require_exp=False)
        )
        with pytest.raises(JWTClaimError, match="audience"):
            decode(token, cfg)

    def test_unsupported_algorithm_in_header(self, cfg):
        """A token with alg=none in the header should be rejected."""
        import base64
        import json

        header = (
            base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
            .rstrip(b"=")
            .decode()
        )
        payload = _b64url_encode(json.dumps({"sub": "u"}).encode())
        fake_token = f"{header}.{payload}.fakesig"
        with pytest.raises(JWTMalformedError, match="algorithm"):
            decode(fake_token, cfg)

    def test_jwt_error_hierarchy(self):
        assert issubclass(JWTMalformedError, JWTError)
        assert issubclass(JWTInvalidSignatureError, JWTError)
        assert issubclass(JWTExpiredError, JWTError)
        assert issubclass(JWTClaimError, JWTError)


# ---------------------------------------------------------------------------
# extract_role
# ---------------------------------------------------------------------------


class TestExtractRole:
    def test_role_string(self):
        assert extract_role({"role": "admin"}) == "admin"

    def test_roles_list(self):
        assert extract_role({"roles": ["operator", "viewer"]}) == "operator"

    def test_role_takes_priority_over_roles(self):
        assert extract_role({"role": "admin", "roles": ["viewer"]}) == "admin"

    def test_no_role_returns_none(self):
        assert extract_role({"sub": "user"}) is None

    def test_empty_role_string(self):
        assert extract_role({"role": ""}) is None

    def test_empty_roles_list(self):
        assert extract_role({"roles": []}) is None

    def test_non_string_role_ignored(self):
        assert extract_role({"role": 42}) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Full integration: encode → decode → extract_role
# ---------------------------------------------------------------------------


class TestJWTIntegration:
    def test_full_admin_flow(self):
        cfg = JWTConfig(secret_key="fleet-secret", issuer="sentinel", audience="sentinel-api")
        token = encode(
            {"sub": "brandon", "role": "admin", "exp": _future_exp()},
            cfg,
        )
        claims = decode(token, cfg)
        role = extract_role(claims)
        assert claims["sub"] == "brandon"
        assert role == "admin"

    def test_viewer_role_via_roles_list(self):
        cfg = JWTConfig(secret_key="s", require_exp=False)
        token = encode({"sub": "guest", "roles": ["viewer"]}, cfg)
        claims = decode(token, cfg)
        assert extract_role(claims) == "viewer"

    def test_expired_within_leeway_still_valid(self):
        cfg = JWTConfig(secret_key="s", leeway_seconds=60)
        token = encode({"sub": "u", "exp": _past_exp(30)}, cfg)
        claims = decode(token, cfg)
        assert claims["sub"] == "u"
