"""Gap tests for core/auth.py — lines 195-196, 245-247, 467-472."""

from __future__ import annotations

from unittest.mock import patch

from core import auth as auth_module
from core.auth import AuthManager, Role

# ---------------------------------------------------------------------------
# Lines 195-196: OSError during config directory creation in __init__
# ---------------------------------------------------------------------------


def test_init_mkdir_oserror_logged(tmp_path):
    """If mkdir raises OSError, the exception is logged but init continues."""
    config = tmp_path / "subdir" / "users.json"

    with patch.object(
        auth_module.Path,
        "mkdir",
        side_effect=OSError("permission denied"),
    ):
        # Should not raise — OSError is caught and logged
        manager = AuthManager(config_path=str(config))

    # Default admin still gets created in memory even though mkdir failed
    admin = manager.get_user("admin")
    assert admin is not None


# ---------------------------------------------------------------------------
# Lines 245-247: OSError during _save (write failure)
# ---------------------------------------------------------------------------


def test_save_oserror_returns_false(tmp_path):
    """_save returns False when the write raises OSError."""
    config = tmp_path / "users.json"
    manager = AuthManager(config_path=str(config))

    with patch("builtins.open", side_effect=OSError("disk full")):
        result = manager._save()

    assert result is False


def test_create_user_survives_save_failure(tmp_path):
    """create_user still adds user in memory even if _save fails."""
    config = tmp_path / "users.json"
    manager = AuthManager(config_path=str(config))

    with patch.object(manager, "_save", return_value=False):
        user = manager.create_user("bob", "pass", role=Role.OPERATOR)

    assert user.username == "bob"
    assert manager.get_user("bob") is not None


# ---------------------------------------------------------------------------
# Lines 467-472: Expired session cleanup in validate_session
# ---------------------------------------------------------------------------


def test_validate_expired_session_removes_and_returns_none(tmp_path):
    """An expired session is deleted from the store and returns None."""
    config = tmp_path / "users.json"
    manager = AuthManager(config_path=str(config))

    user = manager.get_user("admin")
    token = manager.create_session(user)

    # Forcibly expire the session by rewinding expires_at into the past
    session = manager._sessions[token]
    session["expires_at"] = session["created_at"] - 1

    # validate_session should clean up and return None
    assert manager.validate_session(token) is None

    # The token must be removed from the session store
    assert token not in manager._sessions


def test_validate_expired_session_count_decreases(tmp_path):
    """Expiring a session reduces the active session count."""
    config = tmp_path / "users.json"
    manager = AuthManager(config_path=str(config))

    user = manager.get_user("admin")
    token = manager.create_session(user)
    assert manager.active_session_count() == 1

    # Force-expire
    manager._sessions[token]["expires_at"] = 0
    manager.validate_session(token)

    assert manager.active_session_count() == 0
