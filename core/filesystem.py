"""Root-jailed filesystem browsing for the Sentinel Command Center.

The dashboard has shipped a file explorer since v8. It called ``/api/files``,
``/api/files/content`` and ``/api/files/download`` — none of which had ever
existed, so the panel showed "Cannot list directory" on every load and the
careful XSS hardening around it guarded a code path that could not run.

This module is the missing half. It is deliberately small and deliberately
paranoid, because of what it is: **arbitrary file read over HTTP**, on a host
reachable across Tailscale, gated only by a bearer token. If the jail leaks, a
leaked token becomes "read anything on this machine" — starting with the token
store itself.

Three rules hold everything up:

1. **Resolve, then verify.** Never test the string the caller sent.
   ``C:\\AgentLink\\..\\Windows`` passes any ``startswith`` check and lands
   outside the jail, and a directory junction passes every string test that
   exists. ``Path.resolve()`` collapses ``..`` *and* follows reparse points, so
   checking containment afterwards handles both with one mechanism.
2. **Containment is a path-component comparison,** via ``is_relative_to`` — not
   ``startswith``. ``C:\\AgentLink-evil`` starts with ``C:\\AgentLink``.
3. **Credentials stay unreadable even inside the jail.** A root is a working
   tree, not a promise that everything in it is safe to publish.

Configure the jail with ``SENTINEL_FS_ROOTS`` (``os.pathsep``-separated). The
default is the fleet's working trees, **not** ``C:\\`` — a jail whose root is
the drive is not a jail. Widening it is one environment variable; leaving it
open by default is a permanent liability.
"""

from __future__ import annotations

import base64
import os
import stat
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOTS_ENV = "SENTINEL_FS_ROOTS"

#: Roots used when ``SENTINEL_FS_ROOTS`` is unset. Non-existent entries are
#: dropped silently, so this list can name paths that only exist on some hosts.
DEFAULT_ROOTS = (
    r"C:\AgentLink",
    r"C:\Sentinel",
    r"C:\SentinelDesktop",
    r"C:\Code",
    r"C:\Sites",
)

#: Hard ceiling on a single read, regardless of what the caller asks for.
MAX_READ_BYTES = 1_048_576

#: A larger file than this is never base64-encoded into a data URI, because the
#: encoded form is ~1.34x the bytes and it all sits in one JSON string.
MAX_IMAGE_BYTES = 4_194_304

#: Directory listings are bounded. ``C:\\Windows\\WinSxS`` has ~100k entries and
#: would otherwise serialise into a response nothing can render.
MAX_ENTRIES = 2000

#: Filenames and directory names that are refused everywhere, jail or not.
#: Matched case-insensitively against each path component.
DENIED_NAMES = frozenset(
    {
        ".ssh",
        ".gnupg",
        ".aws",
        ".azure",
        ".kube",
        ".docker",
        ".env",
        ".netrc",
        "_netrc",
        ".npmrc",
        ".pypirc",
        ".git-credentials",
        "credentials",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "shadow",
        "sam",
    }
)

#: Extensions that are refused everywhere. Private key material has no reason
#: to travel over this API.
DENIED_SUFFIXES = frozenset({".pem", ".key", ".pfx", ".p12", ".jks", ".keystore"})

#: Raster image magic numbers. The extension is never trusted — a file named
#: ``x.png`` containing ``<svg onload=…>`` must not come back as an image, and
#: ``image/svg+xml`` is absent on purpose: an SVG can carry <script>.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"\x00\x00\x01\x00", "x-icon"),
)


class FilesystemError(Exception):
    """A refusal, carrying the HTTP status the API should answer with.

    ``code`` is a stable machine-readable reason. The dashboard renders
    ``message``; nothing about the host's layout goes into it beyond what the
    caller already supplied.
    """

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@lru_cache(maxsize=1)
def allowed_roots() -> tuple[Path, ...]:
    """Resolved, existing directories that browsing is confined to.

    Cached because it is consulted on every request. Tests and any future
    config-reload path must call ``allowed_roots.cache_clear()``.
    """
    raw = os.environ.get(ROOTS_ENV, "")
    candidates = [p for p in raw.split(os.pathsep) if p.strip()] if raw.strip() else list(DEFAULT_ROOTS)

    roots: list[Path] = []
    for candidate in candidates:
        try:
            resolved = Path(candidate).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            continue  # a root that isn't on this host is not an error
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _reject_before_resolving(raw: str) -> None:
    """Refusals that must happen on the literal string, before ``resolve()``.

    ``resolve()`` would normalise a UNC or device path into something that then
    has to be argued about. These forms have no legitimate use here, so they are
    refused by shape.
    """
    if "\x00" in raw:
        raise FilesystemError("nul", "Path contains a NUL byte")

    head = raw[:4].replace("/", "\\")
    if head.startswith("\\\\"):
        # Covers \\server\share, \\?\C:\..., \\.\PhysicalDrive0
        raise FilesystemError("unc", "UNC and device paths are not browsable")

    if os.name == "nt":
        # An NTFS alternate data stream (``file.txt:$DATA``) is a different
        # stream on the same path, so containment alone would let it through.
        tail = raw[2:] if len(raw) > 1 and raw[1] == ":" else raw
        if ":" in tail:
            raise FilesystemError("ads", "Alternate data streams are not browsable")


def _reject_denied_names(path: Path) -> None:
    """Refuse credential files and directories anywhere in the resolved path."""
    for part in path.parts:
        lowered = part.lower()
        if lowered in DENIED_NAMES:
            raise FilesystemError("denied_name", f"Refused: {part!r} is a credential path", 403)
        if Path(lowered).suffix in DENIED_SUFFIXES:
            raise FilesystemError("denied_name", f"Refused: {part!r} looks like key material", 403)


def is_denied_name(name: str) -> bool:
    """True if a single directory entry should be hidden from listings."""
    lowered = name.lower()
    return lowered in DENIED_NAMES or Path(lowered).suffix in DENIED_SUFFIXES


def resolve_within_roots(raw: str | None, *, must_exist: bool = False) -> Path:
    """Resolve *raw* and prove it lands inside an allowed root.

    Args:
        raw: The caller-supplied path. Untrusted.
        must_exist: Also require the resolved path to exist.

    Returns:
        The fully resolved path.

    Raises:
        FilesystemError: On any refusal. ``.code`` says which.
    """
    if raw is None or not str(raw).strip():
        raise FilesystemError("empty", "No path given")

    raw = str(raw).strip()
    _reject_before_resolving(raw)

    roots = allowed_roots()
    if not roots:
        # 503, not 400: the request was fine, the service is misconfigured. The
        # dashboard renders 'degraded' distinctly from 'rejected'.
        raise FilesystemError(
            "no_roots",
            f"No browsable roots are configured or present (set {ROOTS_ENV})",
            503,
        )

    try:
        # strict=False so a missing leaf still normalises; existence is a
        # separate question answered below.
        resolved = Path(raw).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise FilesystemError("unresolvable", f"Path could not be resolved: {exc}") from exc

    # Component-wise containment. `startswith` would accept C:\AgentLink-evil.
    if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
        raise FilesystemError("outside_root", "Path is outside the browsable roots", 403)

    _reject_denied_names(resolved)

    if must_exist and not resolved.exists():
        raise FilesystemError("not_found", "No such file or directory", 404)

    return resolved


def _entry_type(entry: os.DirEntry[str]) -> str:
    try:
        return "dir" if entry.is_dir() else "file"
    except OSError:
        return "file"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def list_directory(raw: str | None) -> dict[str, Any]:
    """List a directory, bounded and with credential entries removed."""
    target = resolve_within_roots(raw, must_exist=True)
    if not target.is_dir():
        raise FilesystemError("not_a_directory", "Not a directory", 400)

    entries: list[dict[str, Any]] = []
    truncated = False
    try:
        with os.scandir(target) as it:
            for entry in it:
                if is_denied_name(entry.name):
                    continue
                if len(entries) >= MAX_ENTRIES:
                    truncated = True
                    break
                row: dict[str, Any] = {
                    "name": entry.name,
                    "path": str(target / entry.name),
                    "type": _entry_type(entry),
                }
                try:
                    st = entry.stat(follow_symlinks=False)
                    if row["type"] != "dir":
                        row["size"] = st.st_size
                    row["modified"] = _iso(st.st_mtime)
                    row["link"] = stat.S_ISLNK(st.st_mode)
                except OSError:
                    pass  # a file we cannot stat is still worth naming
                entries.append(row)
    except PermissionError as exc:
        raise FilesystemError("denied", "Permission denied", 403) from exc
    except OSError as exc:
        raise FilesystemError("io_error", f"Could not read directory: {exc}", 400) from exc

    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    return {"path": str(target), "entries": entries, "truncated": truncated}


def _sniff_image(head: bytes) -> str | None:
    """Return an image subtype from magic bytes, or None.

    WEBP and AVIF need a second look: both are RIFF/ISO-BMFF containers whose
    first four bytes do not identify them on their own.
    """
    for signature, subtype in _IMAGE_SIGNATURES:
        if head.startswith(signature):
            return subtype
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"):
        return "avif"
    return None


def read_file(raw: str | None, max_bytes: int | None = None) -> dict[str, Any]:
    """Read a file for display.

    Images come back as a base64 raster ``data:`` URI, matching exactly what
    the dashboard's ``isSafeImageDataUri()`` accepts. SVG is never treated as an
    image — it comes back as inert text — because an SVG can carry ``<script>``.
    """
    target = resolve_within_roots(raw, must_exist=True)
    if target.is_dir():
        raise FilesystemError("is_a_directory", "Path is a directory", 400)

    # Read the module global at call time so the ceiling stays patchable and a
    # caller can never raise it, only lower it.
    ceiling = MAX_READ_BYTES
    cap = ceiling if max_bytes is None else max(0, min(int(max_bytes), ceiling))

    try:
        size = target.stat().st_size
        with open(target, "rb") as fh:
            payload = fh.read(cap)
    except PermissionError as exc:
        raise FilesystemError("denied", "Permission denied", 403) from exc
    except OSError as exc:
        raise FilesystemError("io_error", f"Could not read file: {exc}", 400) from exc

    truncated = size > len(payload)
    out: dict[str, Any] = {
        "path": str(target),
        "name": target.name,
        "size": size,
        "bytes_read": len(payload),
        "truncated": truncated,
    }

    subtype = _sniff_image(payload[:16])
    if subtype and not truncated and size <= MAX_IMAGE_BYTES:
        out["is_image"] = True
        out["data_uri"] = f"data:image/{subtype};base64," + base64.b64encode(payload).decode("ascii")
        out["content"] = ""
        return out

    out["is_image"] = False
    # errors='replace' rather than a decode failure: a binary file should render
    # as visible mojibake, not as a 500.
    out["content"] = payload.decode("utf-8", errors="replace")
    return out


def safe_download_name(name: str | None) -> str:
    """Reduce a filename to something safe for a ``Content-Disposition`` header.

    Quotes, semicolons, backslashes and newlines all let a filename break out of
    the header value and inject directives. Windows permits every one of them in
    a real filename, and these names come from the filesystem, so this is a
    reachable surface rather than a theoretical one.
    """
    cleaned = "".join(c if (c.isalnum() or c in "._-") else "_" for c in (name or ""))
    cleaned = cleaned.strip("._-")
    return cleaned or "download"


def open_for_download(raw: str | None) -> tuple[Path, str]:
    """Validate a download target and return it with a header-safe filename."""
    target = resolve_within_roots(raw, must_exist=True)
    if target.is_dir():
        raise FilesystemError("is_a_directory", "Path is a directory", 400)
    return target, safe_download_name(target.name)
