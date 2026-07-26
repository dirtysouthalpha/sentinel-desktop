"""Crash-safe, owner-only file writes.

The desktop runs as a long-lived service that can be killed at any moment
(NSSM stop, host reboot, OOM). A plain ``open(path, "w")`` followed by a
partial write leaves a truncated or empty file on disk — for the auth user
store or the API-key config that means users locked out or credentials lost.

``atomic_write_text`` writes to a unique temp file in the same directory,
flushes it to disk, then ``os.replace``s it over the target. ``os.replace`` is
atomic on both POSIX and Windows (same-filesystem rename), so a reader or a
crash sees either the old file or the new one — never a half-written one.

Sensitive files are additionally created owner-only where the platform
supports it (POSIX 0600). On Windows the mode is a best-effort no-op — NTFS
ACLs are inherited from the parent directory — so callers that need hard
Windows ACL restriction must set it on the containing directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__ = ["atomic_write_text", "atomic_write_bytes"]


def atomic_write_bytes(path: str | os.PathLike[str], data: bytes, *, mode: int = 0o600) -> None:
    """Atomically write *data* to *path*, creating it owner-only where supported.

    Raises whatever the underlying filesystem raises (``OSError`` subclasses);
    on failure the original file at *path* is left untouched.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Temp file in the SAME directory so os.replace is a same-filesystem
    # (atomic) rename rather than a cross-device copy.
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())  # durability: bytes hit the platter before rename
        # Best-effort owner-only perms before the file becomes visible under
        # its real name. No-op meaningfully on Windows (see module docstring).
        try:
            os.chmod(tmp_name, mode)
        except OSError:
            pass
        os.replace(tmp_name, target)  # atomic on POSIX and Windows
    except BaseException:
        # Never leave the temp file behind on any failure (incl. interrupts).
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_text(
    path: str | os.PathLike[str], text: str, *, encoding: str = "utf-8", mode: int = 0o600
) -> None:
    """Atomically write *text* to *path* (owner-only where supported)."""
    atomic_write_bytes(path, text.encode(encoding), mode=mode)
