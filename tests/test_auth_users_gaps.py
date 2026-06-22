"""Regression: GET /auth/users must gate to ADMIN and strip credential fields.

``_handle_auth_users`` previously returned ``auth_manager.list_users()``
unchanged. Because :class:`core.auth.User` is a dataclass whose fields
include ``password_hash``, ``salt`` and ``api_key``, FastAPI serialized
every credential over the wire to ANY authenticated caller — including
VIEWER-tier JWTs — an offline-cracking / account-takeover vector. The
handler docstring said "admin only" but no role check existed.

Fix: ``_require_admin`` gates the endpoint (the static ``SENTINEL_API_TOKEN``
is admin; JWTs must resolve to a user whose role is ADMIN), and the
response maps each user to a public profile only.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import api.server as mod
from config import Config
from core.auth import Role, User


def _run(coro):
    return asyncio.run(coro)


class _FakeAuth:
    def __init__(self, users, jwt_user=None):
        self._users = users
        self._jwt_user = jwt_user

    def list_users(self):
        return list(self._users)

    def validate_jwt_token(self, authorization):
        return self._jwt_user


class _FakeEngine:
    def __init__(self, users, jwt_user=None):
        self.auth_manager = _FakeAuth(users, jwt_user)


def _user(name, role):
    return User(
        username=name,
        password_hash=f"HASH_{name}",
        salt=f"SALT_{name}",
        role=role,
        api_key=f"KEY_{name}",
        created=1.0,
        last_login=None,
    )


def _make_server():
    return mod.SentinelServer(Config())


USERS = [_user("admin", Role.ADMIN), _user("viewer", Role.VIEWER)]


class TestAuthUsersAdminGate:
    def test_static_token_admin_returns_stripped_profiles(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, "root-token")
        server = _make_server()
        server.engine = _FakeEngine(USERS)
        result = _run(server._handle_auth_users(authorization="Bearer root-token"))
        assert len(result["users"]) == 2
        for profile in result["users"]:
            assert set(profile) == {"username", "role", "created", "last_login"}
            assert "password_hash" not in profile
            assert "salt" not in profile
            assert "api_key" not in profile

    def test_jwt_admin_allowed_and_stripped(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        server = _make_server()
        server.engine = _FakeEngine(USERS, jwt_user=_user("admin", Role.ADMIN))
        result = _run(server._handle_auth_users(authorization="Bearer some.jwt.token"))
        assert len(result["users"]) == 2
        for profile in result["users"]:
            assert "password_hash" not in profile
            assert "salt" not in profile
            assert "api_key" not in profile

    def test_jwt_viewer_forbidden(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        server = _make_server()
        server.engine = _FakeEngine(USERS, jwt_user=_user("viewer", Role.VIEWER))
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_auth_users(authorization="Bearer some.jwt.token"))
        assert exc.value.status_code == 403

    def test_jwt_operator_forbidden(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        server = _make_server()
        server.engine = _FakeEngine(USERS, jwt_user=_user("op", Role.OPERATOR))
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_auth_users(authorization="Bearer some.jwt.token"))
        assert exc.value.status_code == 403

    def test_legacy_no_auth_still_strips_secrets(self):
        server = _make_server()
        server.engine = _FakeEngine(USERS)
        result = _run(server._handle_auth_users(authorization=None))
        for profile in result["users"]:
            assert "password_hash" not in profile
            assert "salt" not in profile
            assert "api_key" not in profile
