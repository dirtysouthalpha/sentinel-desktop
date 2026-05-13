"""Tests for the bcrypt password migration in core.auth."""

from __future__ import annotations

import hashlib

from core.auth import (
    AuthManager,
    Role,
    _hash_password,
    _hash_password_bcrypt,
    _is_bcrypt_hash,
    _verify_password,
)

# ---------------------------------------------------------------------------
# Hash format / verification primitives
# ---------------------------------------------------------------------------


def test_bcrypt_hash_format():
    h = _hash_password_bcrypt("hunter2")
    assert _is_bcrypt_hash(h)
    assert h.startswith("$2b$")


def test_verify_bcrypt_round_trip():
    h = _hash_password_bcrypt("hunter2")
    assert _verify_password("hunter2", h) is True
    assert _verify_password("nope", h) is False


def test_verify_legacy_sha256():
    """Pre-bcrypt users must still verify after the migration."""
    salt = "deadbeef" * 8
    stored = _hash_password("hunter2", salt)
    assert not _is_bcrypt_hash(stored)
    assert _verify_password("hunter2", stored, salt) is True
    assert _verify_password("wrong", stored, salt) is False


def test_verify_malformed_bcrypt_returns_false():
    """A garbled $2b$ string must not raise."""
    assert _verify_password("anything", "$2b$invalid-hash") is False


# ---------------------------------------------------------------------------
# AuthManager wiring
# ---------------------------------------------------------------------------


def test_create_user_uses_bcrypt(tmp_path):
    am = AuthManager(config_path=str(tmp_path / "users.json"))
    user = am.create_user("alice", "hunter2", Role.OPERATOR)
    assert _is_bcrypt_hash(user.password_hash)
    assert user.salt == ""  # bcrypt embeds its own salt
    assert am.authenticate("alice", "hunter2") is user
    assert am.authenticate("alice", "wrong") is None


def test_authenticate_upgrades_legacy_hash(tmp_path):
    """A legacy SHA-256 user gets transparently rehashed to bcrypt on login."""
    am = AuthManager(config_path=str(tmp_path / "users.json"))
    # Create the default admin (already bcrypt) then forcibly downgrade
    # to simulate an upgraded-from-old-install user.
    admin = am.get_user("admin")
    assert admin is not None
    legacy_salt = "cafebabe" * 8
    admin.salt = legacy_salt
    admin.password_hash = hashlib.sha256(f"{legacy_salt}sentinel".encode()).hexdigest()
    assert not _is_bcrypt_hash(admin.password_hash)

    # First successful login should rehash.
    result = am.authenticate("admin", "sentinel")
    assert result is admin
    assert _is_bcrypt_hash(admin.password_hash), "expected hash upgraded to bcrypt"
    assert admin.salt == ""

    # Subsequent logins still work.
    assert am.authenticate("admin", "sentinel") is admin


def test_update_user_password_rehashes_with_bcrypt(tmp_path):
    am = AuthManager(config_path=str(tmp_path / "users.json"))
    am.create_user("bob", "old-pw", Role.VIEWER)
    am.update_user("bob", password="new-pw")
    bob = am.get_user("bob")
    assert bob is not None
    assert _is_bcrypt_hash(bob.password_hash)
    assert am.authenticate("bob", "new-pw") is bob
    assert am.authenticate("bob", "old-pw") is None


def test_static_helpers_are_bcrypt(tmp_path):
    h = AuthManager.hash_password("hunter2")
    assert _is_bcrypt_hash(h)
    assert AuthManager.verify_password("hunter2", h) is True
    assert AuthManager.verify_password("wrong", h) is False
