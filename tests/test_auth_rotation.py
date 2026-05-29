"""Tests for auth password-rotation helpers.

Covers:
- is_default_password() — standalone constant-time check
- AuthManager.requires_password_rotation() — per-user rotation check
- AuthManager.get_users_requiring_rotation() — bulk rotation scan
"""

from __future__ import annotations

from core.auth import (
    DEFAULT_ADMIN_PASSWORD,
    AuthManager,
    Role,
    is_default_password,
)

# ---------------------------------------------------------------------------
# is_default_password
# ---------------------------------------------------------------------------


class TestIsDefaultPassword:
    """Test the standalone is_default_password helper."""

    def test_matches_default(self) -> None:
        assert is_default_password(DEFAULT_ADMIN_PASSWORD) is True

    def test_does_not_match_other(self) -> None:
        assert is_default_password("not-the-default") is False

    def test_does_not_match_empty(self) -> None:
        assert is_default_password("") is False

    def test_does_not_match_similar_prefix(self) -> None:
        # A password that starts with the same characters shouldn't match
        assert is_default_password(DEFAULT_ADMIN_PASSWORD + "extra") is False

    def test_case_sensitive(self) -> None:
        # If the default has mixed case, check that case matters
        if DEFAULT_ADMIN_PASSWORD != DEFAULT_ADMIN_PASSWORD.lower():
            assert is_default_password(DEFAULT_ADMIN_PASSWORD.lower()) is False


# ---------------------------------------------------------------------------
# AuthManager.requires_password_rotation
# ---------------------------------------------------------------------------


class TestRequiresPasswordRotation:
    """Test AuthManager.requires_password_rotation."""

    def test_default_admin_needs_rotation(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        # Default admin is created with DEFAULT_ADMIN_PASSWORD
        assert manager.requires_password_rotation("admin") is True

    def test_changed_password_no_rotation(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        manager.update_user("admin", password="new-secure-password")
        assert manager.requires_password_rotation("admin") is False

    def test_nonexistent_user_returns_false(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        assert manager.requires_password_rotation("ghost") is False

    def test_operator_with_default_needs_rotation(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        manager.create_user("op-user", DEFAULT_ADMIN_PASSWORD, role=Role.OPERATOR)
        assert manager.requires_password_rotation("op-user") is True

    def test_viewer_with_custom_password_no_rotation(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        manager.create_user("viewer1", "my-custom-pw", role=Role.VIEWER)
        assert manager.requires_password_rotation("viewer1") is False


# ---------------------------------------------------------------------------
# AuthManager.get_users_requiring_rotation
# ---------------------------------------------------------------------------


class TestGetUsersRequiringRotation:
    """Test AuthManager.get_users_requiring_rotation."""

    def test_default_admin_only(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        result = manager.get_users_requiring_rotation()
        assert len(result) == 1
        assert result[0].username == "admin"

    def test_multiple_users_with_default(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        manager.create_user("op1", DEFAULT_ADMIN_PASSWORD, role=Role.OPERATOR)
        manager.create_user("op2", DEFAULT_ADMIN_PASSWORD, role=Role.OPERATOR)
        result = manager.get_users_requiring_rotation()
        usernames = {u.username for u in result}
        assert usernames == {"admin", "op1", "op2"}

    def test_mixed_passwords(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        manager.create_user("secure-op", "strong-password", role=Role.OPERATOR)
        manager.create_user("insecure-op", DEFAULT_ADMIN_PASSWORD, role=Role.OPERATOR)
        result = manager.get_users_requiring_rotation()
        usernames = {u.username for u in result}
        assert "secure-op" not in usernames
        assert "insecure-op" in usernames
        assert "admin" in usernames

    def test_all_rotated_returns_empty(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        manager.update_user("admin", password="new-secure-password")
        result = manager.get_users_requiring_rotation()
        assert result == []

    def test_no_users_at_all(self, tmp_path) -> None:
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        # Delete the auto-created admin
        manager.delete_user("admin")
        result = manager.get_users_requiring_rotation()
        assert result == []

    def test_after_password_change_rotation_clears(self, tmp_path) -> None:
        """After rotating password, user should disappear from rotation list."""
        config = tmp_path / "users.json"
        manager = AuthManager(config_path=str(config))
        manager.create_user("temp-user", DEFAULT_ADMIN_PASSWORD, role=Role.OPERATOR)

        # Before rotation
        assert manager.requires_password_rotation("temp-user") is True

        # Rotate password
        manager.update_user("temp-user", password="fresh-password")

        # After rotation
        assert manager.requires_password_rotation("temp-user") is False
        result = manager.get_users_requiring_rotation()
        usernames = {u.username for u in result}
        assert "temp-user" not in usernames
