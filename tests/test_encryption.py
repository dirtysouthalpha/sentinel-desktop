"""Tests for core/encryption.py — DPAPI credential vault."""

import json
import os

import pytest

from core.encryption import CredentialVault


@pytest.fixture
def vault(tmp_path):
    return CredentialVault(vault_path=str(tmp_path / "vault.json"))


class TestCredentialVaultCRUD:
    def test_store_and_retrieve(self, vault):
        assert vault.store("api_key", "sk-abc123") is True
        assert vault.retrieve("api_key") == "sk-abc123"

    def test_retrieve_nonexistent_returns_none(self, vault):
        assert vault.retrieve("nope") is None

    def test_delete_existing(self, vault):
        vault.store("token", "abc")
        assert vault.delete("token") is True
        assert vault.retrieve("token") is None

    def test_delete_nonexistent_returns_false(self, vault):
        assert vault.delete("nope") is False

    def test_list_keys(self, vault):
        vault.store("key1", "val1")
        vault.store("key2", "val2")
        assert vault.list_keys() == ["key1", "key2"]

    def test_list_keys_empty(self, vault):
        assert vault.list_keys() == []

    def test_has_key(self, vault):
        vault.store("exists", "yes")
        assert vault.has_key("exists") is True
        assert vault.has_key("nope") is False


class TestCredentialVaultValidation:
    def test_store_empty_key_returns_false(self, vault):
        assert vault.store("", "value") is False

    def test_store_non_string_key_returns_false(self, vault):
        assert vault.store(123, "value") is False

    def test_store_non_string_value_returns_false(self, vault):
        assert vault.store("key", 123) is False

    def test_overwrite_existing_key(self, vault):
        vault.store("key", "old")
        vault.store("key", "new")
        assert vault.retrieve("key") == "new"


class TestCredentialVaultPersistence:
    def test_vault_file_created_on_store(self, vault):
        vault.store("k", "v")
        assert os.path.isfile(vault._path)

    def test_vault_file_is_valid_json(self, vault):
        vault.store("k", "v")
        with open(vault._path) as fh:
            data = json.load(fh)
        assert data["version"] == 1
        assert "k" in data["keys"]

    def test_vault_loads_existing_file(self, tmp_path):
        path = str(tmp_path / "existing.json")
        v1 = CredentialVault(vault_path=path)
        v1.store("persistent", "value123")
        v2 = CredentialVault(vault_path=path)
        assert v2.retrieve("persistent") == "value123"


class TestImportFromConfig:
    def test_import_sensitive_keys(self, vault):
        config = {
            "api_key": "sk-test",
            "auth_token": "tok-123",
            "db_password": "hunter2",
            "normal_setting": "safe",
        }
        imported = vault.import_from_config(config)
        assert imported == 3
        assert vault.retrieve("api_key") == "sk-test"
        assert vault.retrieve("auth_token") == "tok-123"
        assert vault.retrieve("db_password") == "hunter2"

    def test_import_specific_keys(self, vault):
        config = {"api_key": "sk-test", "other": "val"}
        imported = vault.import_from_config(config, keys=["api_key"])
        assert imported == 1

    def test_import_skips_existing(self, vault):
        vault.store("api_key", "original")
        config = {"api_key": "new-value"}
        imported = vault.import_from_config(config)
        assert imported == 0
        assert vault.retrieve("api_key") == "original"

    def test_import_with_invalid_config(self, vault):
        assert vault.import_from_config("not a dict") == 0


class TestExportSafeConfig:
    def test_masks_vault_keys(self, vault):
        vault.store("api_key", "secret")
        config = {"api_key": "secret", "debug": True}
        safe = vault.export_safe_config(config)
        assert safe["api_key"] == "********"
        assert safe["debug"] is True

    def test_deep_copies_dicts(self, vault):
        config = {"nested": {"a": 1}}
        safe = vault.export_safe_config(config)
        safe["nested"]["a"] = 999
        assert config["nested"]["a"] == 1
