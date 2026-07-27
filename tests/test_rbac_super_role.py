"""Regression test for the v31 SUPER-role permission fix.

``_ROLE_PERMISSIONS[Role.SUPER]`` was built from ``dir(Permission)``, i.e. the
attribute *names* ("VIEW_STATUS"), while ``check_permission`` compares against
the permission *values* ("view_status"). The result was that SUPER — the
highest-privilege role — was denied every permission, while ADMIN below it had
almost all of them.
"""

from __future__ import annotations

import pytest

from core.server.auth import _ROLE_PERMISSIONS, AuthManager, Permission, Role

ALL_PERMISSION_VALUES = {
    getattr(Permission, name)
    for name in dir(Permission)
    if not name.startswith("_") and isinstance(getattr(Permission, name), str)
}


def test_all_permission_values_are_snake_case():
    """Guards the premise: names are UPPER, values are lower."""
    assert ALL_PERMISSION_VALUES
    for value in ALL_PERMISSION_VALUES:
        assert value == value.lower()


def test_super_role_holds_permission_values_not_names():
    granted = _ROLE_PERMISSIONS[Role.SUPER]
    assert granted == ALL_PERMISSION_VALUES
    # The old bug: the set contained names like "VIEW_STATUS".
    assert "VIEW_STATUS" not in granted
    assert Permission.VIEW_STATUS in granted


@pytest.mark.parametrize("permission", sorted(ALL_PERMISSION_VALUES))
def test_super_is_granted_every_permission(tmp_path, permission):
    manager = AuthManager(auth_file=tmp_path / "auth.json")
    key = manager.create_key("root", role="super")
    assert manager.check_permission(key, permission) is True, (
        f"SUPER denied {permission!r}"
    )


def test_super_is_a_superset_of_admin(tmp_path):
    admin_perms = _ROLE_PERMISSIONS[Role.ADMIN]
    super_perms = _ROLE_PERMISSIONS[Role.SUPER]
    assert admin_perms <= super_perms

    manager = AuthManager(auth_file=tmp_path / "auth.json")
    super_key = manager.create_key("root", role="super")
    for permission in sorted(admin_perms):
        assert manager.check_permission(super_key, permission) is True


def test_super_can_manage_users_admin_cannot(tmp_path):
    """MANAGE_USERS is the permission that distinguishes SUPER from ADMIN."""
    manager = AuthManager(auth_file=tmp_path / "auth.json")
    super_key = manager.create_key("root", role="super")
    admin_key = manager.create_key("boss", role="admin")
    assert manager.check_permission(super_key, Permission.MANAGE_USERS) is True
    assert manager.check_permission(admin_key, Permission.MANAGE_USERS) is False


def test_lower_roles_are_still_bounded(tmp_path):
    manager = AuthManager(auth_file=tmp_path / "auth.json")
    viewer = manager.create_key("eyes", role="viewer")
    operator = manager.create_key("hands", role="operator")

    assert manager.check_permission(viewer, Permission.VIEW_STATUS) is True
    assert manager.check_permission(viewer, Permission.RUN_ACTIONS) is False
    assert manager.check_permission(viewer, Permission.MANAGE_USERS) is False

    assert manager.check_permission(operator, Permission.RUN_WORKFLOWS) is True
    assert manager.check_permission(operator, Permission.MANAGE_CONFIG) is False
    assert manager.check_permission(operator, Permission.MANAGE_USERS) is False


def test_unknown_role_grants_nothing(tmp_path):
    manager = AuthManager(auth_file=tmp_path / "auth.json")
    key = manager.create_key("weird", role="wizard")
    for permission in sorted(ALL_PERMISSION_VALUES):
        assert manager.check_permission(key, permission) is False


# ---------------------------------------------------------------------------
# last_used write amplification
# ---------------------------------------------------------------------------


def test_check_key_does_not_rewrite_the_store_every_call(tmp_path, monkeypatch):
    """Pre-v31 every authenticated request rewrote the whole auth file."""
    manager = AuthManager(auth_file=tmp_path / "auth.json")
    key = manager.create_key("api", role="operator")

    saves = []
    real_save = manager._save
    monkeypatch.setattr(manager, "_save", lambda: saves.append(1) or real_save())

    for _ in range(25):
        assert manager.check_key(key) is not None

    # First call persists (last_used was 0.0); the rest must not.
    assert len(saves) <= 1, f"auth store rewritten {len(saves)} times for 25 requests"


def test_check_key_still_tracks_last_used_in_memory(tmp_path):
    manager = AuthManager(auth_file=tmp_path / "auth.json")
    key = manager.create_key("api", role="operator")
    api_key = manager.check_key(key)
    assert api_key is not None
    assert api_key.last_used > 0
