"""Gap tests for encryption.py — Windows DPAPI encrypt/decrypt paths.

Mocks Windows-only ctypes structures and DPAPI functions to exercise
the encrypt/decrypt Windows branches (lines 264-290, 306-331) on Linux.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

import core.encryption as enc_mod
from core.encryption import CredentialVault


class TestDpapiEncryptWindowsPath:
    """Lines 264-290: _encrypt Windows DPAPI branch."""

    @pytest.fixture(autouse=True)
    def _cleanup_module_attrs(self):
        """Ensure no leftover module attributes between tests."""
        yield
        for attr in (
            "ctypes",
            "_DATA_BLOB",
            "_CryptProtectData",
            "_CryptUnprotectData",
            "CRYPTPROTECT_UI_FORBIDDEN",
        ):
            if hasattr(enc_mod, attr) and attr not in ("ctypes",):
                try:
                    delattr(enc_mod, attr)
                except AttributeError:
                    pass

    def _make_mock_ctypes(self, string_at_return=b"encrypted_output"):
        """Create a mock ctypes module with needed attributes."""
        mock_ctypes = MagicMock()
        mock_ctypes.c_byte = MagicMock()
        mock_ctypes.byref = MagicMock(return_value="ref_ptr")
        mock_ctypes.string_at = MagicMock(return_value=string_at_return)
        mock_ctypes.windll = MagicMock()
        return mock_ctypes

    def _make_mock_blob(self):
        """Create a mock _DATA_BLOB class."""
        mock_blob = MagicMock()
        instance = MagicMock()
        instance.cbData = 16
        instance.pbData = 0xDEADBEEF
        mock_blob.return_value = instance
        return mock_blob

    def test_encrypt_dpapi_success(self):
        """CryptProtectData returns non-zero → encrypted bytes returned."""
        mock_blob = self._make_mock_blob()
        mock_crypt = MagicMock(return_value=1)  # non-zero = success
        mock_ctypes = self._make_mock_ctypes(b"encrypted_result")

        with (
            patch.object(enc_mod, "_IS_WINDOWS", True),
            patch.object(enc_mod, "_DATA_BLOB", mock_blob, create=True),
            patch.object(enc_mod, "_CryptProtectData", mock_crypt, create=True),
            patch.object(enc_mod, "CRYPTPROTECT_UI_FORBIDDEN", 0x01, create=True),
            patch.object(enc_mod, "ctypes", mock_ctypes, create=True),
        ):
            result = CredentialVault._encrypt(b"secret_data")

        assert result == b"encrypted_result"
        mock_crypt.assert_called_once()

    def test_encrypt_dpapi_failure_returns_none(self):
        """CryptProtectData returns 0 → returns None."""
        mock_blob = self._make_mock_blob()
        mock_crypt = MagicMock(return_value=0)  # failure
        mock_ctypes = self._make_mock_ctypes()

        with (
            patch.object(enc_mod, "_IS_WINDOWS", True),
            patch.object(enc_mod, "_DATA_BLOB", mock_blob, create=True),
            patch.object(enc_mod, "_CryptProtectData", mock_crypt, create=True),
            patch.object(enc_mod, "CRYPTPROTECT_UI_FORBIDDEN", 0x01, create=True),
            patch.object(enc_mod, "ctypes", mock_ctypes, create=True),
        ):
            result = CredentialVault._encrypt(b"secret_data")

        assert result is None

    def test_encrypt_dpapi_success_with_empty_data(self):
        """Encrypt empty bytes via DPAPI returns result."""
        mock_blob = self._make_mock_blob()
        mock_crypt = MagicMock(return_value=1)
        mock_ctypes = self._make_mock_ctypes(b"")

        with (
            patch.object(enc_mod, "_IS_WINDOWS", True),
            patch.object(enc_mod, "_DATA_BLOB", mock_blob, create=True),
            patch.object(enc_mod, "_CryptProtectData", mock_crypt, create=True),
            patch.object(enc_mod, "CRYPTPROTECT_UI_FORBIDDEN", 0x01, create=True),
            patch.object(enc_mod, "ctypes", mock_ctypes, create=True),
        ):
            result = CredentialVault._encrypt(b"")

        assert result == b""

    def test_encrypt_finally_block_calls_localfree(self):
        """On success, LocalFree is called to free DPAPI-allocated memory."""
        mock_blob = self._make_mock_blob()
        mock_crypt = MagicMock(return_value=1)
        mock_ctypes = self._make_mock_ctypes(b"data")

        with (
            patch.object(enc_mod, "_IS_WINDOWS", True),
            patch.object(enc_mod, "_DATA_BLOB", mock_blob, create=True),
            patch.object(enc_mod, "_CryptProtectData", mock_crypt, create=True),
            patch.object(enc_mod, "CRYPTPROTECT_UI_FORBIDDEN", 0x01, create=True),
            patch.object(enc_mod, "ctypes", mock_ctypes, create=True),
        ):
            CredentialVault._encrypt(b"test")

        # LocalFree is called in the finally block to release blob_out.pbData
        mock_ctypes.windll.kernel32.LocalFree.assert_called_once()


class TestDpapiDecryptWindowsPath:
    """Lines 306-331: _decrypt Windows DPAPI branch."""

    @pytest.fixture(autouse=True)
    def _cleanup_module_attrs(self):
        yield
        for attr in (
            "ctypes",
            "_DATA_BLOB",
            "_CryptProtectData",
            "_CryptUnprotectData",
            "CRYPTPROTECT_UI_FORBIDDEN",
        ):
            if hasattr(enc_mod, attr) and attr not in ("ctypes",):
                try:
                    delattr(enc_mod, attr)
                except AttributeError:
                    pass

    def _make_mock_ctypes(self, string_at_return=b"decrypted_output"):
        mock_ctypes = MagicMock()
        mock_ctypes.c_byte = MagicMock()
        mock_ctypes.byref = MagicMock(return_value="ref_ptr")
        mock_ctypes.string_at = MagicMock(return_value=string_at_return)
        mock_ctypes.windll = MagicMock()
        return mock_ctypes

    def _make_mock_blob(self):
        mock_blob = MagicMock()
        instance = MagicMock()
        instance.cbData = 12
        instance.pbData = 0xBAADF00D
        mock_blob.return_value = instance
        return mock_blob

    def test_decrypt_dpapi_success(self):
        """CryptUnprotectData returns non-zero → decrypted bytes returned."""
        mock_blob = self._make_mock_blob()
        mock_crypt = MagicMock(return_value=1)
        mock_ctypes = self._make_mock_ctypes(b"decrypted_result")

        with (
            patch.object(enc_mod, "_IS_WINDOWS", True),
            patch.object(enc_mod, "_DATA_BLOB", mock_blob, create=True),
            patch.object(enc_mod, "_CryptUnprotectData", mock_crypt, create=True),
            patch.object(enc_mod, "CRYPTPROTECT_UI_FORBIDDEN", 0x01, create=True),
            patch.object(enc_mod, "ctypes", mock_ctypes, create=True),
        ):
            result = CredentialVault._decrypt(b"ciphertext")

        assert result == b"decrypted_result"
        mock_crypt.assert_called_once()

    def test_decrypt_dpapi_failure_returns_none(self):
        """CryptUnprotectData returns 0 → returns None."""
        mock_blob = self._make_mock_blob()
        mock_crypt = MagicMock(return_value=0)
        mock_ctypes = self._make_mock_ctypes()

        with (
            patch.object(enc_mod, "_IS_WINDOWS", True),
            patch.object(enc_mod, "_DATA_BLOB", mock_blob, create=True),
            patch.object(enc_mod, "_CryptUnprotectData", mock_crypt, create=True),
            patch.object(enc_mod, "CRYPTPROTECT_UI_FORBIDDEN", 0x01, create=True),
            patch.object(enc_mod, "ctypes", mock_ctypes, create=True),
        ):
            result = CredentialVault._decrypt(b"ciphertext")

        assert result is None

    def test_decrypt_finally_block_calls_localfree(self):
        """On success, LocalFree is called to free DPAPI-allocated memory."""
        mock_blob = self._make_mock_blob()
        mock_crypt = MagicMock(return_value=1)
        mock_ctypes = self._make_mock_ctypes(b"data")

        with (
            patch.object(enc_mod, "_IS_WINDOWS", True),
            patch.object(enc_mod, "_DATA_BLOB", mock_blob, create=True),
            patch.object(enc_mod, "_CryptUnprotectData", mock_crypt, create=True),
            patch.object(enc_mod, "CRYPTPROTECT_UI_FORBIDDEN", 0x01, create=True),
            patch.object(enc_mod, "ctypes", mock_ctypes, create=True),
        ):
            CredentialVault._decrypt(b"ciphertext")

        mock_ctypes.windll.kernel32.LocalFree.assert_called_once()


class TestRoundTripWindowsDPAPI:
    """Full store → retrieve roundtrip via mocked DPAPI."""

    def test_store_and_retrieve_with_dpapi_mock(self, tmp_path):
        """Store a credential and retrieve it using mocked DPAPI."""
        mock_blob = MagicMock()
        blob_instance = MagicMock()
        blob_instance.cbData = 16
        blob_instance.pbData = 0x1234
        mock_blob.return_value = blob_instance

        # For encrypt: return some "encrypted" data
        mock_crypt_protect = MagicMock(return_value=1)
        # For decrypt: return some "decrypted" data
        mock_crypt_unprotect = MagicMock(return_value=1)

        mock_ctypes_encrypt = MagicMock()
        mock_ctypes_encrypt.c_byte = MagicMock()
        mock_ctypes_encrypt.byref = MagicMock(return_value="ref")
        mock_ctypes_encrypt.string_at = MagicMock(return_value=b"encrypted_blob")
        mock_ctypes_encrypt.windll = MagicMock()

        mock_ctypes_decrypt = MagicMock()
        mock_ctypes_decrypt.c_byte = MagicMock()
        mock_ctypes_decrypt.byref = MagicMock(return_value="ref")
        mock_ctypes_decrypt.string_at = MagicMock(return_value=b"my_secret_value")
        mock_ctypes_decrypt.windll = MagicMock()

        vault_path = str(tmp_path / "vault.json")

        # Store
        with (
            patch.object(enc_mod, "_IS_WINDOWS", True),
            patch.object(enc_mod, "_DATA_BLOB", mock_blob, create=True),
            patch.object(enc_mod, "_CryptProtectData", mock_crypt_protect, create=True),
            patch.object(enc_mod, "CRYPTPROTECT_UI_FORBIDDEN", 0x01, create=True),
            patch.object(enc_mod, "ctypes", mock_ctypes_encrypt, create=True),
        ):
            vault = CredentialVault(vault_path)
            assert vault.store("test_key", "my_secret_value") is True

        # Retrieve (need same _DATA_BLOB since file has encrypted data)
        with (
            patch.object(enc_mod, "_IS_WINDOWS", True),
            patch.object(enc_mod, "_DATA_BLOB", mock_blob, create=True),
            patch.object(enc_mod, "_CryptUnprotectData", mock_crypt_unprotect, create=True),
            patch.object(enc_mod, "CRYPTPROTECT_UI_FORBIDDEN", 0x01, create=True),
            patch.object(enc_mod, "ctypes", mock_ctypes_decrypt, create=True),
        ):
            vault2 = CredentialVault(vault_path)
            result = vault2.retrieve("test_key")

        assert result == "my_secret_value"


class TestWindowsDpapiBindingsImport:
    """Lines 40-87: the module-level Windows DPAPI ctypes bindings.

    These only execute at import time on Windows. We reimport the module with
    ``platform.system()`` faked to ``"Windows"`` and ``ctypes.windll`` created
    (the real ctypes on Linux has no ``windll``), so the binding block runs.
    The module is reloaded again afterwards to restore the Linux state.
    """

    def test_windows_bindings_are_set_up_on_import(self):
        with patch("ctypes.windll", MagicMock(), create=True):
            try:
                with patch("platform.system", return_value="Windows"):
                    reloaded = importlib.reload(enc_mod)
                    assert reloaded._IS_WINDOWS is True
                    # The DPAPI Structure and function bindings exist.
                    assert hasattr(reloaded, "_DATA_BLOB")
                    assert hasattr(reloaded, "_CryptProtectData")
                    assert hasattr(reloaded, "_CryptUnprotectData")
                    assert reloaded.CRYPTPROTECT_UI_FORBIDDEN == 0x01
                    # The DATA_BLOB layout carries the two documented fields.
                    field_names = [name for name, _ in reloaded._DATA_BLOB._fields_]
                    assert field_names == ["cbData", "pbData"]
            finally:
                importlib.reload(enc_mod)
        # Back to the Linux defaults for the rest of the session.
        assert enc_mod._IS_WINDOWS is False
