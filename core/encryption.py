"""Sentinel Desktop v22.0 "Aria" — DPAPI Credential Vault.

Provides encrypted storage of sensitive credentials (API keys, tokens, etc.)
using Windows DPAPI (Data Protection API) on Windows, and a per-entry-nonce
HMAC-CTR stream cipher with an integrity tag on non-Windows platforms
(see the ``_stream_encrypt`` / ``_stream_decrypt`` helpers).

Vault file format (JSON):
{
    "version": 1,
    "keys": {
        "credential_name": {
            "encrypted": "<base64-encoded ciphertext>",
            "created": "<ISO 8601 timestamp>"
        }
    }
}

Thread safety: All public methods are guarded by a reentrant lock.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import platform
import threading
from pathlib import Path
from typing import Any

from core.utils import is_windows, iso_now, restrict_file_perms

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Windows DPAPI ctypes bindings
# ---------------------------------------------------------------------------

_IS_WINDOWS = is_windows()

if _IS_WINDOWS:
    import ctypes
    from ctypes import POINTER, Structure, c_byte, c_uint, c_void_p, c_wchar_p

    class _DATA_BLOB(Structure):  # noqa: N801
        """Wrapper for the Windows DATA_BLOB structure used by DPAPI.

        Name matches Windows API convention for DPAPI structures.
        """

        _fields_ = [
            ("cbData", c_uint),
            ("pbData", POINTER(c_byte)),
        ]

    _crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]

    # CryptProtectData(
    #     DATA_BLOB *pDataIn,        # in  – plaintext
    #     LPCWSTR    szDataDescr,    # in  – optional description
    #     DATA_BLOB *pOptionalEntropy,  # in  – optional extra entropy
    #     PVOID      pvReserved,     # reserved, must be NULL
    #     CRYPTPROTECT_PROMPTSTRUCT *pPromptStruct,  # optional prompt
    #     DWORD      dwFlags,        # CRYPTPROTECT_UI_FORBIDDEN etc.
    #     DATA_BLOB *pDataOut        # out – encrypted blob
    # )
    _CryptProtectData = _crypt32.CryptProtectData
    _CryptProtectData.argtypes = [
        POINTER(_DATA_BLOB),  # pDataIn
        c_wchar_p,  # szDataDescr
        POINTER(_DATA_BLOB),  # pOptionalEntropy
        c_void_p,  # pvReserved
        c_void_p,  # pPromptStruct
        c_uint,  # dwFlags
        POINTER(_DATA_BLOB),  # pDataOut
    ]
    _CryptProtectData.restype = c_uint

    _CryptUnprotectData = _crypt32.CryptUnprotectData
    _CryptUnprotectData.argtypes = [
        POINTER(_DATA_BLOB),  # pDataIn
        POINTER(c_wchar_p),  # ppszDataDescr
        POINTER(_DATA_BLOB),  # pOptionalEntropy
        c_void_p,  # pvReserved
        c_void_p,  # pPromptStruct
        c_uint,  # dwFlags
        POINTER(_DATA_BLOB),  # pDataOut
    ]
    _CryptUnprotectData.restype = c_uint

    # Flags
    CRYPTPROTECT_UI_FORBIDDEN = 0x01

# ---------------------------------------------------------------------------
# Non-Windows credential encryption
# ---------------------------------------------------------------------------
#
# Current format (v2): a self-describing framed blob
#     MAGIC(5) || nonce(16) || ciphertext || tag(32)
# where the keystream is HMAC-SHA256(enc_key, nonce || counter) in counter
# mode (XORed against the plaintext) and `tag` is HMAC-SHA256(mac_key,
# nonce || ciphertext) (encrypt-then-MAC). `enc_key` and `mac_key` are
# domain-separated derivations of the machine identity.
#
# This is a genuine encryption layer — not the obfuscation the legacy
# fixed-keystream XOR provided: a fresh random nonce per entry means
# identical plaintexts no longer share a keystream, and the MAC detects
# tampering/corruption on read (the XOR scheme silently returned garbage).
#
# Threat-model honesty: the keys are derived from hostname + uid, so a
# local attacker who can read the vault AND knows the machine identity
# can still derive them. That residual is only fully closed by OS-managed
# key binding (DPAPI on Windows, which is always preferred; libsecret /
# Keychain on Linux/macOS — a separate design decision, not done here).
# The v2 upgrade's job is to remove the trivial weaknesses (fixed
# keystream, no integrity) without adding a dependency.

_MAGIC_V2 = b"SENT2"
_MAGIC_LEN = len(_MAGIC_V2)
_NONCE_LEN = 16
_TAG_LEN = 32  # HMAC-SHA256


def _machine_identity() -> str:
    """Return the machine+user identity string used to derive vault keys."""
    uid = os.getuid() if hasattr(os, "getuid") else os.getenv("USERNAME", "user")
    return f"{platform.node()}-{uid}"


def _vault_keys() -> tuple[bytes, bytes]:
    """Derive domain-separated (keystream_key, mac_key) from the machine identity."""
    master = hashlib.sha256(_machine_identity().encode("utf-8")).digest()
    enc_key = hmac.new(master, b"sentinel-vault-encryption-key", hashlib.sha256).digest()
    mac_key = hmac.new(master, b"sentinel-vault-integrity-key", hashlib.sha256).digest()
    return enc_key, mac_key


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Generate `length` bytes of HMAC-SHA256 counter-mode keystream."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(key, nonce + counter.to_bytes(8, "little"), hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def _stream_encrypt(plaintext: bytes) -> bytes:
    """Encrypt with a per-entry random nonce + HMAC-CTR keystream + integrity tag."""
    enc_key, mac_key = _vault_keys()
    nonce = os.urandom(_NONCE_LEN)
    ks = _keystream(enc_key, nonce, len(plaintext))
    ciphertext = bytes(p ^ k for p, k in zip(plaintext, ks, strict=True))
    tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    return _MAGIC_V2 + nonce + ciphertext + tag


def _stream_decrypt(blob: bytes) -> bytes | None:
    """Reverse of :func:`_stream_encrypt`. Returns ``None`` on any integrity failure."""
    if len(blob) < _MAGIC_LEN + _NONCE_LEN + _TAG_LEN:
        logger.error("vault entry too short for v2 frame — treating as corrupt")
        return None
    nonce = blob[_MAGIC_LEN:_MAGIC_LEN + _NONCE_LEN]
    tag = blob[-_TAG_LEN:]
    ciphertext = blob[_MAGIC_LEN + _NONCE_LEN : -_TAG_LEN]
    enc_key, mac_key = _vault_keys()
    expected = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        logger.error("vault entry failed integrity check (tampering or corruption)")
        return None
    ks = _keystream(enc_key, nonce, len(ciphertext))
    return bytes(c ^ k for c, k in zip(ciphertext, ks, strict=True))


# --- Legacy v1 path (read-only, for migrating existing vaults) --------------


def _get_machine_key() -> bytes:
    """Legacy v1 key derivation — kept only to read pre-v2 vault entries."""
    return hashlib.sha256(_machine_identity().encode()).digest()


def _xor_encrypt(plaintext: bytes) -> bytes:
    """Legacy v1: XOR with a repeating machine key, then base64-encode."""
    key = _get_machine_key()
    xored = bytes(plaintext[i] ^ key[i % len(key)] for i in range(len(plaintext)))
    return base64.b64encode(xored)


def _xor_decrypt(ciphertext: bytes) -> bytes | None:
    """Legacy v1 reverse: base64-decode then XOR with the machine key."""
    try:
        xored = base64.b64decode(ciphertext)
    except ValueError:
        logger.exception("base64 decode failed for legacy v1 vault entry")
        return None
    key = _get_machine_key()
    return bytes(xored[i] ^ key[i % len(key)] for i in range(len(xored)))


# ---------------------------------------------------------------------------
# Vault constants
# ---------------------------------------------------------------------------

_VAULT_VERSION = 1
_MASK = "********"  # shown by export_safe_config


# ---------------------------------------------------------------------------
# CredentialVault
# ---------------------------------------------------------------------------


class CredentialVault:
    """Thread-safe credential vault backed by Windows DPAPI encryption.

    Parameters
    ----------
    vault_path:
        Filesystem path to the JSON vault file.  Parent directories are
        created automatically when the first key is stored.

    """

    def __init__(self, vault_path: str = "config/vault.json") -> None:
        """Initialize the vault and load any previously persisted keys.

        Args:
            vault_path: Path to the JSON file that stores encrypted keys.

        """
        self._path = Path(vault_path)
        self._lock = threading.RLock()
        self._data: dict[str, Any] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, key: str, value: str) -> bool:
        """Encrypt *value* with DPAPI and store it under *key*.

        Returns ``True`` on success, ``False`` on failure.
        """
        if not key or not isinstance(key, str):
            logger.error("store(): key must be a non-empty string")
            return False
        if not isinstance(value, str):
            logger.error("store(): value must be a string")
            return False

        encrypted = self._encrypt(value.encode("utf-8"))
        if encrypted is None:
            return False

        with self._lock:
            self._data.setdefault("keys", {})[key] = {
                "encrypted": base64.b64encode(encrypted).decode("ascii"),
                "created": iso_now(),
            }
            return self._save()

    def retrieve(self, key: str) -> str | None:
        """Decrypt and return the value stored under *key*.

        Returns ``None`` when the key does not exist or decryption fails.
        """
        with self._lock:
            entry = self._data.get("keys", {}).get(key)
            if entry is None:
                return None

            try:
                encrypted = base64.b64decode(entry["encrypted"])
            except (ValueError, TypeError):
                logger.exception("Corrupt vault entry for key '%s'", key)
                return None
            plain = self._decrypt(encrypted)
            if plain is None:
                return None
            return plain.decode("utf-8")

    def delete(self, key: str) -> bool:
        """Remove *key* from the vault.  Returns ``True`` if the key existed."""
        with self._lock:
            keys = self._data.get("keys", {})
            if key not in keys:
                return False
            del keys[key]
            return self._save()

    def list_keys(self) -> list[str]:
        """Return a sorted list of all key names in the vault."""
        with self._lock:
            return sorted(self._data.get("keys", {}).keys())

    def has_key(self, key: str) -> bool:
        """Return ``True`` if *key* is present in the vault."""
        with self._lock:
            return key in self._data.get("keys", {})

    # ------------------------------------------------------------------
    # Migration helpers
    # ------------------------------------------------------------------

    def import_from_config(
        self,
        config: dict[str, Any],
        keys: list[str] | None = None,
    ) -> int:
        """Migrate plaintext values from *config* into the vault.

        Parameters
        ----------
        config:
            A flat dictionary (typically loaded from a YAML / JSON config
            file) containing sensitive values as plaintext strings.
        keys:
            Optional list of top-level keys to migrate.  When ``None``,
            every string-valued entry whose name ends with ``_key``,
            ``_token``, ``_secret``, or ``_password`` is migrated.

        Returns
        -------
        int
            Number of keys successfully imported.

        """
        if not isinstance(config, dict):
            logger.error("import_from_config(): config must be a dict")
            return 0

        sensitive_suffixes = ("_key", "_token", "_secret", "_password")

        if keys is None:
            keys = [
                k
                for k, v in config.items()
                if isinstance(v, str) and k.endswith(sensitive_suffixes)
            ]

        imported = 0
        for k in keys:
            val = config.get(k)
            if isinstance(val, str) and not self.has_key(k):
                if self.store(k, val):
                    imported += 1
                    logger.info("Imported credential '%s' into vault", k)
                else:
                    logger.warning("Failed to import credential '%s'", k)
        return imported

    def export_safe_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of *config* with vault-managed values masked.

        Any key present in both *config* and the vault is replaced with
        ``"********"`` so that the returned dictionary is safe to log or
        serialise for debugging.
        """
        with self._lock:
            vault_keys = set(self._data.get("keys", {}).keys())

        safe = {}
        for k, v in config.items():
            if k in vault_keys:
                safe[k] = _MASK
            else:
                # Deep-copy dicts / lists, pass primitives through
                safe[k] = json.loads(json.dumps(v)) if isinstance(v, (dict, list)) else v
        return safe

    # ------------------------------------------------------------------
    # DPAPI encrypt / decrypt
    # ------------------------------------------------------------------

    @staticmethod
    def _encrypt(plaintext: bytes) -> bytes | None:
        """Encrypt *plaintext* using DPAPI (CurrentUser scope).

        On non-Windows platforms, uses a per-entry-nonce HMAC-CTR stream
        cipher with an integrity tag (see ``_stream_encrypt``). DPAPI is
        always preferred where available.
        """
        if _IS_WINDOWS:
            blob_in = _DATA_BLOB()
            blob_in.cbData = len(plaintext)
            blob_in.pbData = (ctypes.c_byte * len(plaintext))(*plaintext)

            blob_out = _DATA_BLOB()

            ok = _CryptProtectData(
                ctypes.byref(blob_in),
                "SentinelDesktopCredential",  # description
                None,  # no optional entropy
                None,  # reserved
                None,  # no prompt struct
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(blob_out),
            )
            if not ok:
                logger.error("CryptProtectData failed (HRESULT may indicate data loss)")
                return None

            try:
                length = int(blob_out.cbData)
                result = ctypes.string_at(blob_out.pbData, length)
            finally:
                # DPAPI allocates memory that we must free via LocalFree
                ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]

            return result

        # Non-Windows: v2 stream cipher (per-entry nonce + integrity tag).
        return _stream_encrypt(plaintext)

    @staticmethod
    def _decrypt(ciphertext: bytes) -> bytes | None:
        """Decrypt *ciphertext* that was produced by :meth:`_encrypt`."""
        if _IS_WINDOWS:
            blob_in = _DATA_BLOB()
            blob_in.cbData = len(ciphertext)
            blob_in.pbData = (ctypes.c_byte * len(ciphertext))(*ciphertext)

            blob_out = _DATA_BLOB()

            ok = _CryptUnprotectData(
                ctypes.byref(blob_in),
                None,  # ppszDataDescr – not needed
                None,  # no optional entropy
                None,  # reserved
                None,  # no prompt struct
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(blob_out),
            )
            if not ok:
                logger.error("CryptUnprotectData failed")
                return None

            try:
                length = int(blob_out.cbData)
                result = ctypes.string_at(blob_out.pbData, length)
            finally:
                ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]

            return result

        # Non-Windows: v2 framed blob if the magic prefix is present, else
        # fall through to the legacy v1 XOR path to read existing vaults.
        if ciphertext[:_MAGIC_LEN] == _MAGIC_V2:
            return _stream_decrypt(ciphertext)
        return _xor_decrypt(ciphertext)

    # ------------------------------------------------------------------
    # Vault persistence helpers
    # ------------------------------------------------------------------

    def _validate_vault_structure(self, data: Any) -> None:
        """Validate vault data structure and raise ValueError if invalid."""
        if not isinstance(data, dict) or "keys" not in data:
            raise ValueError("Invalid vault structure")

    def _load(self) -> dict[str, Any]:
        """Read the vault JSON from disk.  Returns an empty vault on error."""
        if not self._path.exists():
            return {"version": _VAULT_VERSION, "keys": {}}

        # Heal permissions on an existing vault left world-readable by an
        # older version, before exposing its contents any further.
        restrict_file_perms(self._path)
        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
            self._validate_vault_structure(data)
            return data
        except (OSError, json.JSONDecodeError, ValueError):
            logger.exception("Failed to load vault from %s — vault data may be lost", self._path)
            return {"version": _VAULT_VERSION, "keys": {}}

    def _save(self) -> bool:
        """Atomically write the vault JSON to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            # Restrict the temp file before the atomic replace so the renamed
            # inode (which becomes vault.json) is owner-only on POSIX.
            restrict_file_perms(tmp)
            tmp.replace(self._path)
            return True
        except OSError:
            logger.exception("Failed to save vault to %s", self._path)
            return False
