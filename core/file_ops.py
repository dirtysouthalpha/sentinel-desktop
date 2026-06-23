"""Sentinel Desktop v3.0 — Safe file operations.

When ``tenant_lockdown`` is enabled in the user config (or the
``SENTINEL_SANDBOX_ROOT`` environment variable is set), all paths resolve
through :func:`_resolve_safe` and must land inside the sandbox root. Paths
that escape the root cause the public helpers to return their "failure"
sentinel (``None`` or ``False``) and log a ``PermissionError``.

Sandbox root resolution order:

1. ``SENTINEL_SANDBOX_ROOT`` env var — setting it implies enforcement.
2. Config ``tenant_lockdown`` flag — when ``True`` the default root is
   ``~/SentinelDesktop``.
3. Otherwise the sandbox is inactive and paths are used as-given.
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_lockdown_root() -> Path | None:
    """Return the active sandbox root, or ``None`` when no sandbox is in effect."""
    env_root = os.environ.get("SENTINEL_SANDBOX_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve(strict=False)
    try:
        from config import Config  # local import: config lives at repo root

        cfg = Config()
        cfg.load()
        if not cfg.get("tenant_lockdown"):
            return None
    except (ImportError, OSError) as exc:
        logger.debug("tenant_lockdown probe failed: %s", exc)
        return None
    return (Path.home() / "SentinelDesktop").resolve(strict=False)


def _resolve_safe(path: str) -> Path:
    """Resolve *path* to an absolute :class:`Path` and validate it.

    Raises:
        PermissionError: when a sandbox is active and *path* resolves
            outside it (after ``..`` and symlink resolution).

    """
    resolved = Path(path).expanduser().resolve(strict=False)
    root = _get_lockdown_root()
    if root is None:
        return resolved
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"path {resolved!s} is outside tenant sandbox {root!s}") from exc
    return resolved


def read_file(path: str, encoding: str = "utf-8") -> str | None:
    """Read file contents. Returns string or ``None`` on error."""
    try:
        safe = _resolve_safe(path)
    except PermissionError:
        logger.exception("read_file(%s) blocked", path)
        return None
    try:
        with open(safe, encoding=encoding) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        logger.exception("read_file(%s) failed", path)
        return None


def write_file(path: str, content: str, encoding: str = "utf-8") -> bool:
    """Write file contents. Creates parent dirs. Returns ``True`` on success."""
    try:
        safe = _resolve_safe(path)
    except PermissionError:
        logger.exception("write_file(%s) blocked", path)
        return False
    try:
        safe.parent.mkdir(parents=True, exist_ok=True)
        with open(safe, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except OSError:
        logger.exception("write_file(%s) failed", path)
        return False


def list_directory(path: str = ".") -> list[dict[str, Any]] | None:
    """List directory contents. Returns list of dicts or ``None`` on error."""
    try:
        safe = _resolve_safe(path)
    except PermissionError:
        logger.exception("list_directory(%s) blocked", path)
        return None
    try:
        entries: list[dict[str, Any]] = []
        for entry in os.scandir(safe):
            try:
                entries.append(
                    {
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": entry.stat().st_size if entry.is_file() else 0,
                    },
                )
            except OSError as e:
                logger.debug("Skipping directory entry %s: %s", entry.name, e)
                continue
        return sorted(entries, key=lambda e: (not e["is_dir"], e["name"].lower()))
    except OSError:
        logger.exception("list_directory(%s) failed", path)
        return None


def delete_file(path: str, force: bool = False) -> bool:
    """Delete a file or directory. Returns True on success."""
    try:
        safe = _resolve_safe(path)
    except PermissionError:
        logger.exception("delete_file(%s) blocked", path)
        return False
    try:
        if safe.is_dir():
            import shutil

            shutil.rmtree(safe) if force else safe.rmdir()
        else:
            safe.unlink(missing_ok=True)
        return True
    except OSError:
        logger.exception("delete_file(%s) failed", path)
        return False


def move_file(src: str, dst: str) -> bool:
    """Move/rename a file or directory. Returns True on success."""
    try:
        safe_src = _resolve_safe(src)
        safe_dst = _resolve_safe(dst)
    except PermissionError:
        logger.exception("move_file(%s→%s) blocked", src, dst)
        return False
    try:
        safe_dst.parent.mkdir(parents=True, exist_ok=True)
        safe_src.rename(safe_dst)
        return True
    except OSError:
        logger.exception("move_file(%s→%s) failed", src, dst)
        return False


def copy_file(src: str, dst: str) -> bool:
    """Copy a file. Returns True on success."""
    import shutil

    try:
        safe_src = _resolve_safe(src)
        safe_dst = _resolve_safe(dst)
    except PermissionError:
        logger.exception("copy_file(%s→%s) blocked", src, dst)
        return False
    try:
        safe_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe_src, safe_dst)
        return True
    except OSError:
        logger.exception("copy_file(%s→%s) failed", src, dst)
        return False


def mkdir(path: str, parents: bool = True) -> bool:
    """Create a directory. Returns True on success."""
    try:
        safe = _resolve_safe(path)
    except PermissionError:
        logger.exception("mkdir(%s) blocked", path)
        return False
    try:
        safe.mkdir(parents=parents, exist_ok=True)
        return True
    except OSError:
        logger.exception("mkdir(%s) failed", path)
        return False


def stat_file(path: str) -> dict[str, Any] | None:
    """Get file metadata. Returns dict or None on error."""
    try:
        safe = _resolve_safe(path)
    except PermissionError:
        logger.exception("stat_file(%s) blocked", path)
        return None
    try:
        st = safe.stat()
        return {
            "path": str(safe),
            "name": safe.name,
            "size": st.st_size,
            "is_dir": safe.is_dir(),
            "is_file": safe.is_file(),
            "modified": st.st_mtime,
            "created": st.st_ctime,
            "permissions": oct(st.st_mode)[-3:],
        }
    except OSError:
        logger.exception("stat_file(%s) failed", path)
        return None


def find_files(
    pattern: str,
    root: str = ".",
    max_results: int = 100,
) -> list[str] | None:
    """Search for files matching a glob pattern. Returns list of paths."""
    from glob import glob as _glob

    try:
        safe_root = _resolve_safe(root)
    except PermissionError:
        logger.exception("find_files(%s in %s) blocked", pattern, root)
        return None
    try:
        full_pattern = str(safe_root / "**" / pattern)
        matches = _glob(full_pattern, recursive=True)
        return [str(Path(m).relative_to(safe_root)) for m in matches[:max_results]]
    except OSError:
        logger.exception("find_files(%s in %s) failed", pattern, root)
        return None


def archive_create(
    archive_path: str,
    files: list[str],
    base_dir: str = ".",
) -> bool:
    """Create a zip archive from a list of files. Returns True on success."""
    import zipfile

    try:
        safe_archive = _resolve_safe(archive_path)
        safe_base = _resolve_safe(base_dir)
    except PermissionError:
        logger.exception("archive_create(%s) blocked", archive_path)
        return False
    try:
        safe_archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(safe_archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                full = safe_base / f
                if full.exists():
                    zf.write(full, arcname=f)
        return True
    except (OSError, zipfile.BadZipFile):
        logger.exception("archive_create(%s) failed", archive_path)
        return False


def archive_extract(
    archive_path: str,
    dest_dir: str = ".",
) -> bool:
    """Extract a zip archive to a directory. Returns True on success."""
    import zipfile

    try:
        safe_archive = _resolve_safe(archive_path)
        safe_dest = _resolve_safe(dest_dir)
    except PermissionError:
        logger.exception("archive_extract(%s) blocked", archive_path)
        return False
    try:
        safe_dest.mkdir(parents=True, exist_ok=True)
        dest_root = safe_dest.resolve()
        with zipfile.ZipFile(safe_archive, "r") as zf:
            # Zip-slip guard: validate every member resolves inside dest_root
            # before extracting. A member like "../../etc/cron.d/x" or an
            # absolute "/etc/passwd" would otherwise escape the destination.
            for info in zf.infolist():
                target = (dest_root / info.filename).resolve()
                if target != dest_root and dest_root not in target.parents:
                    logger.warning(
                        "archive_extract(%s): refusing unsafe member %r (escapes dest)",
                        archive_path,
                        info.filename,
                    )
                    return False
            zf.extractall(safe_dest)
        return True
    except (OSError, zipfile.BadZipFile):
        logger.exception("archive_extract(%s) failed", archive_path)
        return False
