"""
DPAPI Credential Vault for Sentinel Desktop.

Provides encrypted storage of sensitive credentials (API keys, tokens, etc.)
using Windows DPAPI (Data Protection API) with automatic fallback to
base64 encoding on non-Windows platforms.

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
import json
import logging
import os
import platform
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Windows DPAPI ctypes bindings
# ---------------------------------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"

if _IS_WINDOWS:
    import ctypes
    from ctypes import c_byte, c_uint, c_void_p, c_wchar_p, POINTER, Structure

    class _DATA_BLOB(Structure):
        """Wrapper for the Windows DATA_BLOB structure used by DPAPI."""
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
        POINTER(_DATA_BLOB),   # pDataIn
        c_wchar_p,             # szDataDescr
        POINTER(_DATA_BLOB),   # pOptionalEntropy
        c_void_p,              # pvReserved
        c_void_p,              # pPromptStruct
        c_uint,                # dwFlags
        POINTER(_DATA_BLOB),   # pDataOut
    ]
    _CryptProtectData.restype = c_uint

    _CryptUnprotectData = _crypt32.CryptUnprotectData
    _CryptUnprotectData.argtypes = [
        POINTER(_DATA_BLOB),   # pDataIn
        POINTER(c_wchar_p),    # ppszDataDescr
        POINTER(_DATA_BLOB),   # pOptionalEntropy
        c_void_p,              # pvReserved
        c_void_p,              # pPromptStruct
        c_uint,                # dwFlags
        POINTER(_DATA_BLOB),   # pDataOut
    ]
    _CryptUnprotectData.restype = c_uint

    # Flags
    CRYPTPROTECT_UI_FORBIDDEN = 0x01

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
                "created": datetime.now(timezone.utc).isoformat(),
            }
            return self._save()

    def retrieve(self, key: str) -> Optional[str]:
        """Decrypt and return the value stored under *key*.

        Returns ``None`` when the key does not exist or decryption fails.
        """
        with self._lock:
            entry = self._data.get("keys", {}).get(key)
            if entry is None:
                return None

            encrypted = base64.b64decode(entry["encrypted"])
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
            self._save()
            return True

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
        keys: Optional[list[str]] = None,
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
                k for k, v in config.items()
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
    def _encrypt(plaintext: bytes) -> Optional[bytes]:
        """Encrypt *plaintext* using DPAPI (CurrentUser scope).

        On non-Windows platforms the data is merely base64-encoded and a
        warning is emitted.
        """
        if _IS_WINDOWS:
            blob_in = _DATA_BLOB()
            blob_in.cbData = len(plaintext)
            blob_in.pbData = (ctypes.c_byte * len(plaintext))(*plaintext)

            blob_out = _DATA_BLOB()

            ok = _CryptProtectData(
                ctypes.byref(blob_in),
                "SentinelDesktopCredential",  # description
                None,   # no optional entropy
                None,   # reserved
                None,   # no prompt struct
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(blob_out),
            )
            if not ok:
                logger.error(
                    "CryptProtectData failed (HRESULT may indicate data loss)"
                )
                return None

            try:
                result = bytes(
                    (ctypes.c_byte * blob_out.cbData).from_address(blob_out.pbData)
                )
            finally:
                # DPAPI allocates memory that we must free via LocalFree
                ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]

            return result

        else:
            # Non-Windows fallback: base64 only (NOT secure)
            logger.warning(
                "DPAPI unavailable on %s – credentials stored with base64 "
                "encoding only (not encrypted).  Run on Windows for proper "
                "DPAPI protection.",
                platform.system(),
            )
            return base64.b64encode(plaintext)

    @staticmethod
    def _decrypt(ciphertext: bytes) -> Optional[bytes]:
        """Decrypt *ciphertext* that was produced by :meth:`_encrypt`."""
        if _IS_WINDOWS:
            blob_in = _DATA_BLOB()
            blob_in.cbData = len(ciphertext)
            blob_in.pbData = (ctypes.c_byte * len(ciphertext))(*ciphertext)

            blob_out = _DATA_BLOB()

            ok = _CryptUnprotectData(
                ctypes.byref(blob_in),
                None,   # ppszDataDescr – not needed
                None,   # no optional entropy
                None,   # reserved
                None,   # no prompt struct
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(blob_out),
            )
            if not ok:
                logger.error("CryptUnprotectData failed")
                return None

            try:
                result = bytes(
                    (ctypes.c_byte * blob_out.cbData).from_address(blob_out.pbData)
                )
            finally:
                ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]

            return result

        else:
            # Non-Windows fallback
            try:
                return base64.b64decode(ciphertext)
            except Exception:
                logger.error("base64 decode failed for non-Windows vault entry")
                return None

    # ------------------------------------------------------------------
    # Vault persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        """Read the vault JSON from disk.  Returns an empty vault on error."""
        if not self._path.exists():
            return {"version": _VAULT_VERSION, "keys": {}}

        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, dict) or "keys" not in data:
                raise ValueError("Invalid vault structure")
            return data
        except Exception as exc:
            logger.error("Failed to load vault from %s: %s", self._path, exc)
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
            tmp.replace(self._path)
            return True
        except Exception as exc:
            logger.error("Failed to save vault to %s: %s", self._path, exc)
            return False
