"""Regression tests for the v31 bootstrap-password fix.

``core/auth.py`` shipped a hardcoded ``DEFAULT_ADMIN_PASSWORD`` constant and
auto-provisioned an ADMIN account with it on first run, so every deployment
had the same known administrator credentials baked into the source tree.

It is now either supplied by the operator via ``SENTINEL_BOOTSTRAP_PASSWORD``
or randomly generated per process and surfaced exactly once.
"""

from __future__ import annotations

import re

import pytest

import core.auth as auth_mod
from core.auth import (
    BOOTSTRAP_PASSWORD_ENV,
    DEFAULT_ADMIN_USERNAME,
    AuthManager,
    Role,
    _make_bootstrap_password,
)


def bootstrap_password() -> str:
    """Read the live module attribute, not an import-time copy."""
    return auth_mod.DEFAULT_ADMIN_PASSWORD


# ---------------------------------------------------------------------------
# The constant is no longer a source-level secret
# ---------------------------------------------------------------------------


def test_bootstrap_password_is_not_hardcoded_in_source():
    source = open(auth_mod.__file__, encoding="utf-8").read()
    # The literal must not appear as an assigned string anywhere in the module.
    assert f'"{bootstrap_password()}"' not in source
    assert f"'{bootstrap_password()}'" not in source
    assert re.search(r'DEFAULT_ADMIN_PASSWORD\s*:\s*str\s*=\s*["\']', source) is None


def test_generated_password_is_long_and_random():
    a = _make_bootstrap_password()
    b = _make_bootstrap_password()
    assert a != b, "bootstrap password is not random"
    assert len(a) >= 24
    assert a.isascii()


def test_env_var_overrides_the_generated_password(monkeypatch):
    monkeypatch.setenv(BOOTSTRAP_PASSWORD_ENV, "operator-chosen-pw")
    assert _make_bootstrap_password() == "operator-chosen-pw"


def test_blank_env_var_falls_back_to_generation(monkeypatch):
    monkeypatch.setenv(BOOTSTRAP_PASSWORD_ENV, "   ")
    generated = _make_bootstrap_password()
    assert generated.strip() == generated
    assert len(generated) >= 24


def test_independent_installs_get_different_passwords(monkeypatch):
    """Two installs must not share a bootstrap password.

    Asserted through the factory rather than by reloading the module: a reload
    would rebind ``core.auth.DEFAULT_ADMIN_PASSWORD`` for every other test in
    the session.
    """
    monkeypatch.delenv(BOOTSTRAP_PASSWORD_ENV, raising=False)
    generated = {_make_bootstrap_password() for _ in range(25)}
    assert len(generated) == 25


# ---------------------------------------------------------------------------
# Bootstrap behaviour
# ---------------------------------------------------------------------------


def test_bootstrap_creates_admin_and_requires_rotation(tmp_path):
    manager = AuthManager(config_path=str(tmp_path / "users.json"))
    admin = manager.get_user(DEFAULT_ADMIN_USERNAME)
    assert admin is not None
    assert admin.role == Role.ADMIN.value
    assert manager.requires_password_rotation(DEFAULT_ADMIN_USERNAME) is True


def test_bootstrap_password_is_surfaced_once(tmp_path, capsys, caplog):
    with caplog.at_level("WARNING"):
        AuthManager(config_path=str(tmp_path / "users.json"))
    captured = capsys.readouterr()
    # It must be recoverable by the operator...
    assert bootstrap_password() in captured.err
    assert bootstrap_password() in caplog.text
    assert DEFAULT_ADMIN_USERNAME in captured.err


def test_bootstrap_password_is_not_stored_in_plaintext(tmp_path):
    store = tmp_path / "users.json"
    AuthManager(config_path=str(store))
    contents = store.read_text(encoding="utf-8")
    assert bootstrap_password() not in contents
    assert "$2b$" in contents  # bcrypt hash


def test_no_banner_when_users_already_exist(tmp_path, capsys):
    store = tmp_path / "users.json"
    AuthManager(config_path=str(store))
    capsys.readouterr()  # discard the first-run banner

    AuthManager(config_path=str(store))  # second load, users present
    second = capsys.readouterr()
    assert bootstrap_password() not in second.err


def test_rotation_clears_the_requirement(tmp_path):
    manager = AuthManager(config_path=str(tmp_path / "users.json"))
    assert manager.requires_password_rotation(DEFAULT_ADMIN_USERNAME) is True
    manager.update_user(DEFAULT_ADMIN_USERNAME, password="a-real-operator-password")
    assert manager.requires_password_rotation(DEFAULT_ADMIN_USERNAME) is False
    assert manager.get_users_requiring_rotation() == []


def test_bootstrap_password_actually_authenticates(tmp_path):
    manager = AuthManager(config_path=str(tmp_path / "users.json"))
    user = manager.authenticate(DEFAULT_ADMIN_USERNAME, bootstrap_password())
    assert user is not None
    assert user.username == DEFAULT_ADMIN_USERNAME


@pytest.mark.parametrize("wrong", ["admin", "password", "changeme", "sentinel", ""])
def test_common_default_passwords_do_not_authenticate(tmp_path, wrong):
    """Guards against the old well-known-constant class of bug."""
    manager = AuthManager(config_path=str(tmp_path / "users.json"))
    assert manager.authenticate(DEFAULT_ADMIN_USERNAME, wrong) is None
