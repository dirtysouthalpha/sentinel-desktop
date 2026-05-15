"""Safe file operations.

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
    except PermissionError as exc:
        logger.exception("read_file(%s) blocked", path)
        return None
    try:
        with open(safe, encoding=encoding) as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.exception("read_file(%s) failed", path)
        return None


def write_file(path: str, content: str, encoding: str = "utf-8") -> bool:
    """Write file contents. Creates parent dirs. Returns ``True`` on success."""
    try:
        safe = _resolve_safe(path)
    except PermissionError as exc:
        logger.exception("write_file(%s) blocked", path)
        return False
    try:
        parent = safe.parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)
        with open(safe, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except OSError as exc:
        logger.exception("write_file(%s) failed", path)
        return False


def list_directory(path: str = ".") -> list[dict[str, Any]] | None:
    """List directory contents. Returns list of dicts or ``None`` on error."""
    try:
        safe = _resolve_safe(path)
    except PermissionError as exc:
        logger.exception("list_directory(%s) blocked", path)
        return None
    try:
        entries: list[dict[str, Any]] = []
        for entry in os.scandir(safe):
            entries.append(
                {
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "size": entry.stat().st_size if entry.is_file() else 0,
                }
            )
        return sorted(entries, key=lambda e: (not e["is_dir"], e["name"].lower()))
    except OSError as exc:
        logger.exception("list_directory(%s) failed", path)
        return None
