"""Tests for encryption.py — covering DPAPI failure, non-Windows fallback, load/save errors."""

import base64
import json
import platform
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.encryption import CredentialVault


class TestEncryptReturnsNone:
    """store() returns False when _encrypt returns None."""

    def test_encrypt_failure_returns_false(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        with patch.object(CredentialVault, "_encrypt", return_value=None):
            assert vault.store("key", "val") is False


class TestDecryptReturnsNone:
    """retrieve() returns None when _decrypt returns None."""

    def test_decrypt_failure_returns_none(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        vault.store("key", "val")
        with patch.object(CredentialVault, "_decrypt", return_value=None):
            assert vault.retrieve("key") is None


class TestImportStoreFailure:
    """import_from_config handles store failure gracefully."""

    def test_import_store_failure_logs_warning(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        with patch.object(vault, "store", return_value=False):
            imported = vault.import_from_config({"api_key": "secret"}, keys=["api_key"])
        assert imported == 0


class TestNonWindowsEncryptFallback:
    """_encrypt falls back to XOR+base64 on non-Windows."""

    @patch("core.encryption._IS_WINDOWS", False)
    def test_non_windows_encrypt_returns_bytes(self) -> None:
        data = b"hello world"
        result = CredentialVault._encrypt(data)
        assert result is not None
        # Should be base64-encoded (valid b64 characters)
        base64.b64decode(result)  # Should not raise

    @patch("core.encryption._IS_WINDOWS", False)
    def test_non_windows_encrypt_decrypt_roundtrip(self) -> None:
        data = b"hello world"
        encrypted = CredentialVault._encrypt(data)
        assert encrypted is not None
        decrypted = CredentialVault._decrypt(encrypted)
        assert decrypted == data


class TestNonWindowsDecryptFallback:
    """_decrypt falls back to XOR+base64 on non-Windows."""

    @patch("core.encryption._IS_WINDOWS", False)
    def test_non_windows_decrypt_roundtrip(self) -> None:
        data = b"hello world"
        encrypted = CredentialVault._encrypt(data)
        assert encrypted is not None
        result = CredentialVault._decrypt(encrypted)
        assert result == b"hello world"

    @patch("core.encryption._IS_WINDOWS", False)
    def test_non_windows_decrypt_invalid_base64(self) -> None:
        result = CredentialVault._decrypt(b"not-valid-base64!!!")
        assert result is None


class TestInvalidVaultStructure:
    """_load handles invalid vault structure."""

    def test_load_non_dict_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "v.json"
        bad.write_text("[1, 2, 3]", encoding="utf-8")
        vault = CredentialVault(str(bad))
        # Should create empty vault structure
        assert vault.list_keys() == []

    def test_load_missing_keys_field(self, tmp_path: Path) -> None:
        bad = tmp_path / "v.json"
        bad.write_text(json.dumps({"version": 1}), encoding="utf-8")
        vault = CredentialVault(str(bad))
        assert vault.list_keys() == []

    def test_load_corrupt_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "v.json"
        bad.write_text("{bad json", encoding="utf-8")
        vault = CredentialVault(str(bad))
        assert vault.list_keys() == []


class TestSaveOSError:
    """_save handles OSError gracefully."""

    def test_save_failure_returns_false(self, tmp_path: Path) -> None:
        vault = CredentialVault(str(tmp_path / "v.json"))
        vault.store("k", "v")
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            assert vault._save() is False


class TestDpapiEncryptFailure:
    """CryptProtectData failure path on Windows."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="DPAPI only on Windows")
    @patch("core.encryption._CryptProtectData", return_value=0)
    def test_crypt_protect_failure(self, mock_crypt: MagicMock) -> None:
        result = CredentialVault._encrypt(b"test")
        assert result is None


class TestDpapiDecryptFailure:
    """CryptUnprotectData failure path on Windows."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="DPAPI only on Windows")
    @patch("core.encryption._CryptUnprotectData", return_value=0)
    def test_crypt_unprotect_failure(self, mock_crypt: MagicMock) -> None:
        result = CredentialVault._decrypt(b"test")
        assert result is None
