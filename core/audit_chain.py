"""Sentinel Desktop v19 — Tamper-Evident Hash-Chained Audit Log.

Each appended entry includes a SHA-256 hash that covers the *previous* entry's
hash plus the new entry's content.  Any modification to a stored entry (or
insertion/deletion) breaks the hash chain, which is detectable by
``AuditChain.verify()``.

The chain is persisted as a newline-delimited JSON file (one JSON object per
line).  The first entry has ``prev_hash`` equal to ``GENESIS_HASH``.

Format (each line)::

    {
        "seq": 1,
        "timestamp": "2026-06-19T14:30:00.000000",
        "event_type": "action",
        "actor": "admin",
        "data": { ... arbitrary payload ... },
        "prev_hash": "0000...0000",
        "entry_hash": "sha256(prev_hash + canonical_json(entry_without_entry_hash))"
    }

Thread safety
-------------
All public methods are guarded by a ``threading.Lock``.  Concurrent writers
are serialised; concurrent readers that call ``verify()`` hold the lock for
the duration of the full scan.

Usage::

    chain = AuditChain("logs/audit.jsonl")
    chain.append("login", actor="admin", data={"ip": "10.0.0.1"})
    chain.append("action", actor="admin", data={"action": "write_file", "path": "/tmp/x"})

    ok, bad_seqs = chain.verify()
    if not ok:
        print("Chain tampered! Bad entries:", bad_seqs)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from core.utils import iso_now

logger = logging.getLogger(__name__)

GENESIS_HASH: str = "0" * 64
_ENCODING = "utf-8"


def _canonical(obj: Any) -> bytes:
    """Return a stable, canonical JSON byte encoding of *obj*.

    Uses ``sort_keys=True`` and no extra whitespace so that the same object
    always produces the same bytes regardless of insertion order.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode(_ENCODING)


def _sha256(data: bytes) -> str:
    """Return the hex-encoded SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def _compute_entry_hash(entry: dict[str, Any]) -> str:
    """Compute the hash of *entry*.

    The hash covers ``entry["prev_hash"]`` concatenated with the canonical
    JSON of *entry* **without** the ``entry_hash`` field.
    """
    without_hash = {k: v for k, v in entry.items() if k != "entry_hash"}
    raw = entry["prev_hash"].encode(_ENCODING) + _canonical(without_hash)
    return _sha256(raw)


class AuditChainError(Exception):
    """Raised on verification failure or structural errors."""


class AuditChain:
    """Append-only hash-chained audit log.

    Args:
        path: Filesystem path for the ``.jsonl`` file.  Parent directories
            are created automatically on first append.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialise the audit chain.

        Args:
            path: Path to the newline-delimited JSON log file.
        """
        self._path = Path(path)
        self._lock = threading.Lock()
        self._last_hash: str = GENESIS_HASH
        self._seq: int = 0
        self._loaded: bool = False
        self._load_tail()

    # ------------------------------------------------------------------
    # Internal: load last entry to establish chain tip
    # ------------------------------------------------------------------

    def _load_tail(self) -> None:
        """Read the last entry of an existing log to establish chain state.

        This is O(n) in file size but called only once at init.  For
        production usage consider keeping a separate "tip" file if the log
        is expected to be very large.
        """
        if not self._path.exists():
            return

        last_entry: dict[str, Any] | None = None
        try:
            with open(self._path, encoding=_ENCODING) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        last_entry = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed line in %s", self._path)

        except OSError as exc:
            logger.error("Failed to read audit chain %s: %s", self._path, exc)
            return

        if last_entry is not None:
            self._last_hash = last_entry.get("entry_hash", GENESIS_HASH)
            self._seq = last_entry.get("seq", 0)
            self._loaded = True
            logger.debug(
                "Audit chain loaded from %s: %d entries, tip=%s",
                self._path,
                self._seq,
                self._last_hash[:16],
            )

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    def append(
        self,
        event_type: str,
        actor: str = "",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a new entry to the chain.

        Args:
            event_type: Short string identifying the event kind
                (e.g. ``"action"``, ``"login"``, ``"policy_violation"``).
            actor: Who/what triggered the event (username, ``"system"``, etc.).
            data: Arbitrary payload dict (must be JSON-serialisable).

        Returns:
            The full entry dict that was written, including ``entry_hash``.
        """
        with self._lock:
            self._seq += 1
            entry: dict[str, Any] = {
                "seq": self._seq,
                "timestamp": iso_now(),
                "event_type": event_type,
                "actor": actor,
                "data": data or {},
                "prev_hash": self._last_hash,
            }
            entry["entry_hash"] = _compute_entry_hash(entry)
            self._last_hash = entry["entry_hash"]

            self._write_entry(entry)
            return dict(entry)

    def _write_entry(self, entry: dict[str, Any]) -> None:
        """Serialise *entry* and append it to the log file."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding=_ENCODING) as fh:
                fh.write(json.dumps(entry, sort_keys=True, default=str))
                fh.write("\n")
        except OSError as exc:
            logger.error("Failed to write audit entry: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def entries(self) -> list[dict[str, Any]]:
        """Return all entries in chain order (oldest first).

        Returns:
            List of entry dicts.  Returns empty list if the file does not
            exist or is empty.
        """
        with self._lock:
            return self._read_all()

    def _read_all(self) -> list[dict[str, Any]]:
        """Read every line from the log file (must be called under lock)."""
        if not self._path.exists():
            return []
        result: list[dict[str, Any]] = []
        try:
            with open(self._path, encoding=_ENCODING) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        result.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Malformed line skipped during read")
        except OSError as exc:
            logger.error("Failed to read audit chain: %s", exc)
        return result

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def verify(self) -> tuple[bool, list[int]]:
        """Walk the entire chain and verify integrity.

        Each entry's ``entry_hash`` is recomputed and compared against the
        stored value.  The ``prev_hash`` of each entry is checked against the
        ``entry_hash`` of the previous entry (or ``GENESIS_HASH`` for the
        first entry).

        Returns:
            ``(ok: bool, bad_seqs: list[int])`` where *bad_seqs* contains the
            sequence numbers of any entries that failed verification.  *ok* is
            ``True`` only when *bad_seqs* is empty.
        """
        with self._lock:
            all_entries = self._read_all()

        if not all_entries:
            return True, []

        bad_seqs: list[int] = []
        expected_prev = GENESIS_HASH

        for entry in all_entries:
            seq = entry.get("seq", "?")

            # Recompute hash
            recomputed = _compute_entry_hash(entry)
            stored = entry.get("entry_hash", "")

            if recomputed != stored:
                logger.warning("Audit chain broken at seq=%s (hash mismatch)", seq)
                bad_seqs.append(seq)
            elif entry.get("prev_hash") != expected_prev:
                logger.warning("Audit chain broken at seq=%s (prev_hash mismatch)", seq)
                bad_seqs.append(seq)

            expected_prev = entry.get("entry_hash", "")

        return len(bad_seqs) == 0, bad_seqs

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def length(self) -> int:
        """Number of entries appended in the current session (since init).

        For the total count including pre-existing entries, call
        ``len(chain.entries())``.
        """
        with self._lock:
            return self._seq

    @property
    def tip_hash(self) -> str:
        """Hash of the last appended entry (or ``GENESIS_HASH`` if empty)."""
        with self._lock:
            return self._last_hash

    def summary(self) -> str:
        """Return a brief human-readable summary."""
        entries = self.entries()
        return f"AuditChain({self._path}): {len(entries)} entries, tip={self._last_hash[:16]}..."
