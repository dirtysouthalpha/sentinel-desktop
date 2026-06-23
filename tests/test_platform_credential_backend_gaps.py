"""Gap tests for the platform Credentials *file-fallback* backends.

`LinuxCredentialBackend` / `MacOSCredentialBackend` fall back to a JSON file
(`config/vault.json`) when libsecret / the Keychain is unavailable. That file
stores credential values, so its save must be (a) atomic — a crash mid-write
must not truncate it and lose every stored credential — and (b) owner-only on
POSIX. These tests exercise `_store_file` / `_save_file` directly so no
keychain/secretstorage mocking is required.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

from core.platform.linux_backend import LinuxCredentialBackend
from core.platform.macos_backend import MacOSCredentialBackend

_BACKENDS = [LinuxCredentialBackend, MacOSCredentialBackend]


def _fresh(backend_cls, path: Path):
    """A backend whose file-fallback store points at ``path``."""
    backend = backend_cls()
    backend._file_path = path
    backend._file_data = {"version": 1, "keys": {}}
    return backend


@pytest.mark.parametrize("backend_cls", _BACKENDS, ids=["linux", "macos"])
class TestCredentialBackendAtomicSave:
    def test_save_failure_preserves_existing_keys(self, backend_cls, tmp_path, monkeypatch):
        vault = tmp_path / "vault.json"
        seed = _fresh(backend_cls, vault)
        seed._store_file("alpha", "secret-alpha")
        assert vault.exists()

        backend = _fresh(backend_cls, vault)
        # Pick up the seeded alpha so the in-memory state matches disk.
        backend._file_data = backend._load_file()

        def _boom(*args, **kwargs):
            raise OSError("simulated fsync failure")

        monkeypatch.setattr("os.fsync", _boom)
        backend._store_file("bravo", "secret-bravo")

        reloaded = _fresh(backend_cls, vault)
        reloaded._file_data = reloaded._load_file()
        assert reloaded._file_data.get("keys", {}).get("alpha") is not None, (
            "pre-existing credential was lost when the new save failed"
        )
        assert "bravo" not in reloaded._file_data.get("keys", {}), (
            "save() overwrote the live file before atomically replacing it"
        )

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
    def test_credential_file_is_owner_only(self, backend_cls, tmp_path):
        # The fallback vault stores credential values; it must not be readable
        # by group/other on a shared host. The old code honored the umask (0644)
        # and left base64-encoded creds world-readable.
        vault = tmp_path / "vault.json"
        backend = _fresh(backend_cls, vault)
        backend._store_file("alpha", "secret-alpha")
        mode = stat.S_IMODE(vault.stat().st_mode)
        assert (mode & 0o077) == 0, f"credential vault exposed: {oct(mode)}"
