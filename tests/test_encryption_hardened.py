"""Tests for the non-Windows credential-vault stream cipher (core/encryption.py).

Covers the v2 framed format: per-entry random nonce, HMAC-SHA256 counter-mode
keystream, and encrypt-then-MAC integrity tag — plus read-migration of legacy
v1 (XOR+base64) vault entries.
"""

from unittest.mock import patch

import pytest

from core.encryption import (
    _MAGIC_LEN,
    _MAGIC_V2,
    _NONCE_LEN,
    _TAG_LEN,
    CredentialVault,
    _xor_encrypt,
)


@pytest.fixture
def vault(tmp_path):
    return CredentialVault(vault_path=str(tmp_path / "vault.json"))


class TestStreamCipherRoundTrip:
    @patch("core.encryption._IS_WINDOWS", False)
    def test_encrypt_decrypt_roundtrip(self):
        data = b"sk-super-secret-api-key-12345"
        blob = CredentialVault._encrypt(data)
        assert blob is not None
        assert CredentialVault._decrypt(blob) == data

    @patch("core.encryption._IS_WINDOWS", False)
    def test_empty_plaintext_roundtrip(self):
        blob = CredentialVault._encrypt(b"")
        assert blob is not None
        assert CredentialVault._decrypt(blob) == b""

    def test_store_retrieve_roundtrip(self, vault):
        assert vault.store("api_key", "sk-abc123") is True
        assert vault.retrieve("api_key") == "sk-abc123"


class TestV2Frame:
    @patch("core.encryption._IS_WINDOWS", False)
    def test_output_carries_magic_prefix(self):
        assert CredentialVault._encrypt(b"x")[:_MAGIC_LEN] == _MAGIC_V2

    @patch("core.encryption._IS_WINDOWS", False)
    def test_frame_is_minimum_length(self):
        # MAGIC + nonce + tag even when ciphertext is empty.
        blob = CredentialVault._encrypt(b"")
        assert len(blob) == _MAGIC_LEN + _NONCE_LEN + _TAG_LEN

    @patch("core.encryption._IS_WINDOWS", False)
    def test_output_is_not_plaintext(self):
        data = b"never store me in the clear"
        blob = CredentialVault._encrypt(data)
        assert blob is not None
        assert data not in blob


class TestPerEntryNonce:
    @patch("core.encryption._IS_WINDOWS", False)
    def test_identical_plaintext_yields_distinct_blobs(self):
        data = b"same secret"
        a = CredentialVault._encrypt(data)
        b = CredentialVault._encrypt(data)
        assert a != b  # fresh random nonce per entry

    def test_identical_values_stored_under_different_keys_differ_on_disk(self, vault):
        vault.store("k1", "duplicate")
        vault.store("k2", "duplicate")
        raw = vault._data["keys"]
        assert raw["k1"]["encrypted"] != raw["k2"]["encrypted"]


class TestIntegrityAndTamperRejection:
    @patch("core.encryption._IS_WINDOWS", False)
    def test_flipped_ciphertext_byte_rejected(self):
        blob = bytearray(CredentialVault._encrypt(b"sensitive"))
        ct_start = _MAGIC_LEN + _NONCE_LEN
        blob[ct_start] ^= 0xFF
        assert CredentialVault._decrypt(bytes(blob)) is None

    @patch("core.encryption._IS_WINDOWS", False)
    def test_flipped_tag_byte_rejected(self):
        blob = bytearray(CredentialVault._encrypt(b"sensitive"))
        blob[-1] ^= 0xFF
        assert CredentialVault._decrypt(bytes(blob)) is None

    @patch("core.encryption._IS_WINDOWS", False)
    def test_flipped_nonce_byte_rejected(self):
        blob = bytearray(CredentialVault._encrypt(b"sensitive"))
        blob[_MAGIC_LEN] ^= 0xFF
        assert CredentialVault._decrypt(bytes(blob)) is None

    @patch("core.encryption._IS_WINDOWS", False)
    def test_truncated_blob_rejected(self):
        blob = CredentialVault._encrypt(b"sensitive")
        assert CredentialVault._decrypt(blob[:-5]) is None


class TestLegacyV1Migration:
    """Vault entries written by the old XOR scheme must still decrypt."""

    @patch("core.encryption._IS_WINDOWS", False)
    def test_legacy_xor_entry_decrypts_via_dispatcher(self):
        legacy_blob = _xor_encrypt(b"old-school secret")
        assert CredentialVault._decrypt(legacy_blob) == b"old-school secret"

    @patch("core.encryption._IS_WINDOWS", False)
    def test_rewriting_legacy_entry_upgrades_to_v2(self, vault):
        # Seed the vault with a legacy v1 entry (raw XOR blob, base64'd by store
        # convention the same way store() would).
        import base64

        legacy_blob = _xor_encrypt(b"legacy value")
        vault._data.setdefault("keys", {})["migrate_me"] = {
            "encrypted": base64.b64encode(legacy_blob).decode("ascii"),
            "created": "2025-01-01T00:00:00Z",
        }
        # Reading the legacy entry still works.
        assert vault.retrieve("migrate_me") == "legacy value"
        # Re-storing it writes a v2 framed blob.
        vault.store("migrate_me", "legacy value")
        stored = vault._data["keys"]["migrate_me"]["encrypted"]
        decoded = base64.b64decode(stored)
        assert decoded[:_MAGIC_LEN] == _MAGIC_V2
