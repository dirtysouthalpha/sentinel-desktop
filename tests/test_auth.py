"""Tests for core/auth.py — RBAC, password hashing, session management."""

import json
import time

import pytest

from core.auth import (
    AuthManager,
    Role,
    User,
    _generate_salt,
    _hash_password,
    _hash_password_bcrypt,
    _is_bcrypt_hash,
    _verify_password,
)


class TestRole:
    def test_values(self):
        assert Role.VIEWER.value == "viewer"
        assert Role.OPERATOR.value == "operator"
        assert Role.ADMIN.value == "admin"

    def test_ordering(self):
        assert Role.VIEWER < Role.OPERATOR < Role.ADMIN
        assert Role.ADMIN > Role.OPERATOR > Role.VIEWER
        assert Role.OPERATOR >= Role.OPERATOR
        assert Role.VIEWER <= Role.OPERATOR

    def test_is_string_enum(self):
        assert isinstance(Role.ADMIN, str)
        assert Role.ADMIN == "admin"


class TestUser:
    def test_to_dict_roundtrip(self):
        u = User(
            username="test",
            password_hash="h",
            salt="s",
            role="admin",
            api_key="key",
            created=1000.0,
            last_login=2000.0,
        )
        d = u.to_dict()
        assert d["username"] == "test"
        assert d["role"] == "admin"
        assert d["last_login"] == 2000.0

        restored = User.from_dict(d)
        assert restored.username == u.username
        assert restored.password_hash == u.password_hash
        assert restored.salt == u.salt
        assert restored.role == u.role
        assert restored.api_key == u.api_key
        assert restored.created == u.created
        assert restored.last_login == u.last_login

    def test_from_dict_missing_last_login(self):
        d = {
            "username": "test",
            "password_hash": "h",
            "salt": "s",
            "role": "viewer",
            "api_key": "key",
            "created": 1000.0,
        }
        u = User.from_dict(d)
        assert u.last_login is None


class TestPasswordHashing:
    def test_legacy_sha256(self):
        salt = _generate_salt()
        hashed = _hash_password("secret", salt)
        assert isinstance(hashed, str)
        assert len(hashed) == 64
        assert _hash_password("secret", salt) == hashed

    def test_bcrypt_hash(self):
        hashed = _hash_password_bcrypt("secret")
        assert hashed.startswith("$2b$")
        assert _is_bcrypt_hash(hashed)

    def test_is_bcrypt_hash_detects_formats(self):
        assert _is_bcrypt_hash("$2a$10$xxx")
        assert _is_bcrypt_hash("$2b$10$xxx")
        assert _is_bcrypt_hash("$2y$10$xxx")
        assert not _is_bcrypt_hash("abc123")

    def test_verify_bcrypt_password(self):
        hashed = _hash_password_bcrypt("mypassword")
        assert _verify_password("mypassword", hashed)
        assert not _verify_password("wrong", hashed)

    def test_verify_legacy_password(self):
        salt = _generate_salt()
        hashed = _hash_password("legacy_pass", salt)
        assert _verify_password("legacy_pass", hashed, salt)
        assert not _verify_password("wrong", hashed, salt)


class TestAuthManager:
    @pytest.fixture()
    def auth(self, tmp_path):
        config = tmp_path / "users.json"
        return AuthManager(config_path=str(config))

    def test_default_admin_created(self, auth):
        users = auth.list_users()
        assert len(users) == 1
        assert users[0].username == "admin"
        assert users[0].role == "admin"

    def test_authenticate_default_admin(self, auth):
        user = auth.authenticate("admin", "sentinel")
        assert user is not None
        assert user.username == "admin"
        assert user.last_login is not None

    def test_authenticate_wrong_password(self, auth):
        assert auth.authenticate("admin", "wrong") is None

    def test_authenticate_unknown_user(self, auth):
        assert auth.authenticate("nobody", "x") is None

    def test_create_user(self, auth):
        user = auth.create_user("bob", "pass123", role=Role.OPERATOR)
        assert user.username == "bob"
        assert user.role == "operator"
        assert len(user.api_key) > 0

    def test_create_duplicate_user_raises(self, auth):
        auth.create_user("bob", "pass")
        with pytest.raises(ValueError, match="already exists"):
            auth.create_user("bob", "pass2")

    def test_delete_user(self, auth):
        auth.create_user("bob", "pass")
        assert auth.delete_user("bob") is True
        assert auth.get_user("bob") is None

    def test_delete_nonexistent_user(self, auth):
        assert auth.delete_user("ghost") is False

    def test_update_user_password(self, auth):
        auth.create_user("bob", "old")
        updated = auth.update_user("bob", password="new")
        assert updated is not None
        assert auth.authenticate("bob", "new") is not None
        assert auth.authenticate("bob", "old") is None

    def test_update_user_role(self, auth):
        auth.create_user("bob", "pass", role=Role.VIEWER)
        updated = auth.update_user("bob", role=Role.ADMIN)
        assert updated.role == "admin"

    def test_update_nonexistent_user(self, auth):
        assert auth.update_user("ghost", password="x") is None

    def test_regenerate_api_key(self, auth):
        user = auth.create_user("bob", "pass")
        old_key = user.api_key
        updated = auth.update_user("bob", regenerate_api_key=True)
        assert updated.api_key != old_key

    def test_authenticate_api_key(self, auth):
        user = auth.create_user("bob", "pass")
        found = auth.authenticate_api_key(user.api_key)
        assert found is not None
        assert found.username == "bob"

    def test_authenticate_api_key_unknown(self, auth):
        assert auth.authenticate_api_key("badkey") is None

    def test_session_lifecycle(self, auth):
        user = auth.create_user("bob", "pass")
        token = auth.create_session(user)
        assert len(token) > 0
        assert auth.validate_session(token) is not None
        assert auth.active_session_count() == 1

        auth.revoke_session(token)
        assert auth.validate_session(token) is None
        assert auth.active_session_count() == 0

    def test_revoke_unknown_session(self, auth):
        assert auth.revoke_session("badtoken") is False

    def test_session_info(self, auth):
        user = auth.create_user("bob", "pass")
        token = auth.create_session(user)
        info = auth.get_session_info(token)
        assert info is not None
        assert info["username"] == "bob"

    def test_revoke_all_sessions(self, auth):
        user = auth.create_user("bob", "pass")
        auth.create_session(user)
        auth.create_session(user)
        assert auth.active_session_count() == 2
        count = auth.revoke_all_sessions("bob")
        assert count == 2
        assert auth.active_session_count() == 0

    def test_delete_user_revokes_sessions(self, auth):
        user = auth.create_user("bob", "pass")
        auth.create_session(user)
        auth.delete_user("bob")
        assert auth.active_session_count() == 0


class TestCheckPermission:
    @pytest.fixture()
    def auth(self, tmp_path):
        config = tmp_path / "users.json"
        return AuthManager(config_path=str(config))

    def test_admin_can_do_anything(self, auth):
        admin = auth.get_user("admin")
        assert auth.check_permission(admin, "DELETE", "/api/anything") is True
        assert auth.check_permission(admin, "POST", "/api/goal") is True

    def test_viewer_read_only(self, auth):
        user = auth.create_user("viewer1", "pass", role=Role.VIEWER)
        assert auth.check_permission(user, "GET", "/api/status") is True
        assert auth.check_permission(user, "POST", "/api/goal") is False
        assert auth.check_permission(user, "DELETE", "/api/thing") is False

    def test_operator_allowed_post_prefixes(self, auth):
        user = auth.create_user("op1", "pass", role=Role.OPERATOR)
        assert auth.check_permission(user, "POST", "/api/goal") is True
        assert auth.check_permission(user, "POST", "/api/command") is True
        assert auth.check_permission(user, "GET", "/api/status") is True

    def test_operator_blocked_other_post(self, auth):
        user = auth.create_user("op1", "pass", role=Role.OPERATOR)
        assert auth.check_permission(user, "POST", "/api/admin/users") is False

    def test_operator_blocked_delete(self, auth):
        user = auth.create_user("op1", "pass", role=Role.OPERATOR)
        assert auth.check_permission(user, "DELETE", "/api/goal") is False


class TestPersistence:
    def test_users_survive_reload(self, tmp_path):
        config = tmp_path / "users.json"
        auth1 = AuthManager(config_path=str(config))
        auth1.create_user("bob", "pass", role=Role.OPERATOR)

        auth2 = AuthManager(config_path=str(config))
        assert auth2.get_user("bob") is not None
        assert auth2.get_user("bob").role == "operator"

    def test_corrupt_config_handled(self, tmp_path):
        config = tmp_path / "users.json"
        config.write_text("NOT JSON", encoding="utf-8")
        auth = AuthManager(config_path=str(config))
        # Should boot with default admin despite corrupt file
        assert auth.get_user("admin") is not None

    def test_hash_password_static(self):
        hashed = AuthManager.hash_password("test")
        assert AuthManager.verify_password("test", hashed)

    def test_verify_password_static(self):
        hashed = _hash_password_bcrypt("pw")
        assert AuthManager.verify_password("pw", hashed)
