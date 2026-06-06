"""Gap tests for encryption.py — covering corrupt vault entries, DPAPI paths,
import_from_config edge cases, and export_safe_config.

Focuses on lines 156-158, 264-290, 306-331.
"""

import base64
import json
import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from core.encryption import CredentialVault


class TestCorruptVaultEntry:
    """Lines 156-158: Corrupt vault entry with bad base64 data."""

    def test_retrieve_corrupt_base64_returns_none(self, tmp_path: Path) -> None:
        """Corrupt base64 in vault entry returns None."""
        vault_path = tmp_path / "vault.json"
        vault_data = {
            "version": 1,
            "keys": {
                "mykey": {
                    "encrypted": "not-valid-base64!!!",
                    "created": "2025-01-01T00:00:00Z",
                }
            },
        }
        vault_path.write_text(json.dumps(vault_data), encoding="utf-8")
        vault = CredentialVault(str(vault_path))
        result = vault.retrieve("mykey")
        assert result is None

    def test_retrieve_missing_key_returns_none(self, tmp_path: Path) -> None:
        """Retrieving a non-existent key returns None."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.retrieve("nonexistent") is None

    def test_retrieve_with_decrypt_failure(self, tmp_path: Path) -> None:
        """When decrypt returns None, retrieve returns None."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        vault.store("testkey", "testval")
        with patch.object(CredentialVault, "_decrypt", return_value=None):
            assert vault.retrieve("testkey") is None


class TestNonWindowsEncryptDecrypt:
    """Lines 264-290, 306-331: _encrypt/_decrypt non-Windows fallback."""

    @patch("core.encryption._IS_WINDOWS", False)
    def test_encrypt_returns_valid_base64(self) -> None:
        """Non-Windows encrypt produces valid base64 output."""
        data = b"secret data"
        result = CredentialVault._encrypt(data)
        assert result is not None
        base64.b64decode(result)  # Should not raise

    @patch("core.encryption._IS_WINDOWS", False)
    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Non-Windows encrypt/decrypt is a valid roundtrip."""
        data = b"secret data"
        encrypted = CredentialVault._encrypt(data)
        assert encrypted is not None
        decrypted = CredentialVault._decrypt(encrypted)
        assert decrypted == data

    @patch("core.encryption._IS_WINDOWS", False)
    def test_decrypt_xor_roundtrip(self) -> None:
        """Non-Windows decrypt reverses the XOR+base64 encryption."""
        original = b"hello world"
        encrypted = CredentialVault._encrypt(original)
        assert encrypted is not None
        result = CredentialVault._decrypt(encrypted)
        assert result == original

    @patch("core.encryption._IS_WINDOWS", False)
    def test_decrypt_invalid_base64_returns_none(self) -> None:
        """Non-Windows decrypt with invalid base64 returns None."""
        result = CredentialVault._decrypt(b"!!!invalid!!!")
        assert result is None

    @patch("core.encryption._IS_WINDOWS", False)
    def test_full_roundtrip(self, tmp_path: Path) -> None:
        """Full store→retrieve roundtrip on non-Windows."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.store("api_key", "sk-12345") is True
        assert vault.retrieve("api_key") == "sk-12345"


class TestWindowsEncryptPaths:
    """Windows DPAPI encrypt/decrypt paths (skipped on non-Windows)."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only")
    def test_encrypt_dpapi_failure(self) -> None:
        """CryptProtectData failure returns None."""
        with patch("core.encryption._CryptProtectData", return_value=0):
            result = CredentialVault._encrypt(b"test")
        assert result is None

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only")
    def test_decrypt_dpapi_failure(self) -> None:
        """CryptUnprotectData failure returns None."""
        with patch("core.encryption._CryptUnprotectData", return_value=0):
            result = CredentialVault._decrypt(b"test")
        assert result is None


class TestImportFromConfigEdgeCases:
    """Edge cases for import_from_config."""

    def test_import_with_non_dict_config(self, tmp_path: Path) -> None:
        """Non-dict config returns 0."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.import_from_config("not a dict") == 0

    def test_import_with_none_config(self, tmp_path: Path) -> None:
        """None config returns 0."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.import_from_config(None) == 0

    def test_import_auto_detect_sensitive_keys(self, tmp_path: Path) -> None:
        """Auto-detects keys ending with sensitive suffixes."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        config = {
            "api_key": "sk-123",
            "auth_token": "tok-456",
            "db_password": "pass-789",
            "encrypt_secret": "sec-abc",
            "normal_setting": "not-sensitive",
        }
        imported = vault.import_from_config(config)
        assert imported == 4  # api_key, auth_token, db_password, encrypt_secret
        assert vault.has_key("api_key")
        assert vault.has_key("auth_token")
        assert vault.has_key("db_password")
        assert vault.has_key("encrypt_secret")
        assert not vault.has_key("normal_setting")

    def test_import_skips_already_imported(self, tmp_path: Path) -> None:
        """Keys already in vault are not re-imported."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        vault.store("api_key", "old-value")
        imported = vault.import_from_config({"api_key": "new-value"})
        assert imported == 0
        assert vault.retrieve("api_key") == "old-value"

    def test_import_with_explicit_keys(self, tmp_path: Path) -> None:
        """Explicit keys list overrides auto-detection."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        config = {"api_key": "sk-123", "other": "val"}
        imported = vault.import_from_config(config, keys=["other"])
        assert imported == 1
        assert vault.has_key("other")
        assert not vault.has_key("api_key")

    def test_import_skips_non_string_values(self, tmp_path: Path) -> None:
        """Non-string values in config are skipped."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        config = {"api_key": 12345, "token": "real-token"}
        imported = vault.import_from_config(config, keys=["api_key", "token"])
        assert imported == 1
        assert not vault.has_key("api_key")
        assert vault.has_key("token")


class TestExportSafeConfig:
    """Test export_safe_config masking."""

    def test_masks_vault_keys(self, tmp_path: Path) -> None:
        """Vault keys are masked in exported config."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        vault.store("api_key", "super-secret")
        safe = vault.export_safe_config({"api_key": "super-secret", "other": "visible"})
        assert safe["api_key"] == "********"
        assert safe["other"] == "visible"

    def test_deep_copies_dicts(self, tmp_path: Path) -> None:
        """Dict values are deep-copied."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        config = {"nested": {"a": 1}}
        safe = vault.export_safe_config(config)
        assert safe["nested"] == {"a": 1}
        # Modify safe copy shouldn't affect original
        safe["nested"]["a"] = 999
        assert config["nested"]["a"] == 1

    def test_deep_copies_lists(self, tmp_path: Path) -> None:
        """List values are deep-copied."""
        vault = CredentialVault(str(tmp_path / "v.json"))
        config = {"items": [1, 2, 3]}
        safe = vault.export_safe_config(config)
        assert safe["items"] == [1, 2, 3]
        safe["items"].append(4)
        assert config["items"] == [1, 2, 3]


class TestStoreEdgeCases:
    """Test store() validation."""

    def test_store_empty_key(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.store("", "val") is False

    def test_store_non_string_key(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.store(123, "val") is False

    def test_store_non_string_value(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.store("key", 123) is False

    def test_store_none_value(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.store("key", None) is False


class TestDeleteKey:
    """Test delete() edge cases."""

    def test_delete_nonexistent_key(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.delete("nonexistent") is False

    def test_delete_existing_key(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        vault.store("key1", "val1")
        assert vault.delete("key1") is True
        assert not vault.has_key("key1")


class TestListKeys:
    """Test list_keys() ordering."""

    def test_returns_sorted_keys(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        vault.store("zebra", "z")
        vault.store("alpha", "a")
        vault.store("middle", "m")
        assert vault.list_keys() == ["alpha", "middle", "zebra"]


class TestHasKey:
    """Test has_key() behavior."""

    def test_has_key_true(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        vault.store("existing", "val")
        assert vault.has_key("existing") is True

    def test_has_key_false(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        assert vault.has_key("nonexistent") is False


class TestLoadEdgeCases:
    """Test _load() edge cases."""

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "nonexistent.json"))
        assert vault.list_keys() == []

    def test_load_valid_vault(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "v.json"
        vault_data = {"version": 1, "keys": {"k1": {"encrypted": "dGVzdA==", "created": "2025-01-01"}}}
        vault_path.write_text(json.dumps(vault_data), encoding="utf-8")
        vault = CredentialVault(str(vault_path))
        assert "k1" in vault.list_keys()
