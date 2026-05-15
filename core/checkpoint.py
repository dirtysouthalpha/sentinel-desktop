"""
Sentinel Desktop v2 — Checkpoint save/restore for the agent loop.

Provides crash-resume capability: if the app crashes, the user closes it,
or the agent times out, they can resume exactly where they left off. This
is the desktop equivalent of Sentinel Override's "Resume from checkpoint"
feature.

Thread-safe. Uses only stdlib modules.
"""

import glob
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Checkpoint directory — mirrors config.py AppData resolution
# ---------------------------------------------------------------------------

if os.name == "nt":
    _BASE_DIR = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "SentinelDesktop",
    )
else:
    _BASE_DIR = os.path.join(os.path.expanduser("~"), ".sentinel-desktop")

_CHECKPOINT_DIR = os.path.join(_BASE_DIR, "checkpoints")

# Age-out threshold — checkpoints older than this are considered stale.
_STALE_THRESHOLD = timedelta(hours=1)

# Valid status values.
_VALID_STATUSES = {"running", "paused", "interrupted", "error"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _checkpoint_path(checkpoint_id: str) -> str:
    """Return the file path for a given checkpoint id."""
    return os.path.join(_CHECKPOINT_DIR, f"{checkpoint_id}.json")


def _discover_checkpoint_files(directory: str | None = None) -> list[str]:
    """Return all checkpoint JSON files sorted newest-first by mtime."""
    target = directory or _CHECKPOINT_DIR
    if not os.path.isdir(target):
        return []
    pattern = os.path.join(target, "*.json")
    files = glob.glob(pattern)
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return files


def _parse_timestamp(ts: str) -> datetime | None:
    """Safely parse an ISO-8601 timestamp string."""
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------


class CheckpointManager:
    """Manages checkpoint save/restore for the agent loop.

    Checkpoints are stored as individual JSON files under the AppData
    ``checkpoints/`` directory.  Each file is named ``<uuid>.json`` and
    contains the full agent state needed to resume a run.

    Typical usage::

        cm = CheckpointManager()

        # After each agent step (engine calls this):
        if step_num % 5 == 0:
            cm.save(goal, step_num, memory, screenshot, config, "running",
                    messages=messages)

        # On startup, offer to resume:
        cp = cm.load_latest()
        if cp:
            resume_from(cp)

    All public methods are thread-safe.
    """

    def __init__(self, checkpoint_dir: str | None = None) -> None:
        self._lock = threading.Lock()
        self._dir = checkpoint_dir or _CHECKPOINT_DIR
        os.makedirs(self._dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(
        self,
        goal: str,
        step_num: int,
        agent_memory: list[Any],
        last_screenshot_path: str | None,
        config: dict[str, Any],
        status: str = "running",
        messages: list[dict[str, Any]] | None = None,
    ) -> str | None:
        """Persist a checkpoint to disk.

        Args:
            goal: The original user goal text.
            step_num: Current 1-based step counter.
            agent_memory: The full agent memory state list.
            last_screenshot_path: Path to the most recent screenshot, or
                ``None``.
            config: Provider/model/feature configuration dict.
            status: One of ``"running"``, ``"paused"``, ``"interrupted"``,
                ``"error"``.
            messages: The LLM conversation history so far (for context
                resume).  Defaults to an empty list.

        Returns:
            The checkpoint ``id`` (UUID string).
        """
        if status not in _VALID_STATUSES:
            logger.warning("Invalid checkpoint status %r — defaulting to 'running'", status)
            status = "running"

        checkpoint_id = str(uuid.uuid4())
        timestamp = _iso_now()
        goal_preview = goal[:200] if goal else ""

        record: dict[str, Any] = {
            "id": checkpoint_id,
            "timestamp": timestamp,
            "goal": goal,
            "goal_preview": goal_preview,
            "step_num": step_num,
            "status": status,
            "agent_memory": agent_memory,
            "last_screenshot_path": last_screenshot_path,
            "config": config,
            "messages": messages or [],
            "provider": config.get("provider", ""),
            "model": config.get("model", ""),
        }

        dest = os.path.join(self._dir, f"{checkpoint_id}.json")
        saved = False
        with self._lock:
            try:
                with open(dest, "w", encoding="utf-8") as fh:
                    json.dump(record, fh, indent=2, default=str, ensure_ascii=False)
                saved = True
                logger.info(
                    "Checkpoint saved: %s  step=%d  status=%s",
                    checkpoint_id[:8],
                    step_num,
                    status,
                )
            except Exception as exc:
                logger.error("Failed to save checkpoint %s: %s", checkpoint_id[:8], exc)

        return checkpoint_id if saved else None

    # ------------------------------------------------------------------
    # Load helpers
    # ------------------------------------------------------------------

    def load_latest(self) -> dict[str, Any] | None:
        """Load the most recent **non-stale** checkpoint.

        Returns ``None`` when there are no checkpoints, all are stale
        (older than 1 hour), or all are corrupt.  Stale checkpoints
        trigger a warning log but are **not** deleted — the caller can
        still load them explicitly via :meth:`load`.
        """
        files = _discover_checkpoint_files(self._dir)
        if not files:
            return None

        now = datetime.now(timezone.utc)

        for fpath in files:
            try:
                with open(fpath, encoding="utf-8") as fh:
                    record = json.load(fh)
            except Exception as exc:
                logger.warning("Skipping corrupt checkpoint %s: %s", fpath, exc)
                continue

            # Basic shape validation.
            if not isinstance(record, dict) or "id" not in record:
                logger.warning("Skipping malformed checkpoint %s", fpath)
                continue

            # Age-out check.
            ts = _parse_timestamp(record.get("timestamp", ""))
            if ts is not None:
                age = now - ts
                if age > _STALE_THRESHOLD:
                    logger.warning(
                        "Latest checkpoint %s is stale (age=%s, threshold=%s) — skipping. "
                        "Use load('%s') to force-load.",
                        record["id"][:8],
                        age,
                        _STALE_THRESHOLD,
                        record["id"],
                    )
                    # Continue checking older files — there might be a
                    # non-stale one further down.  In practice the list is
                    # sorted newest-first so we'd break here, but being
                    # thorough costs nothing.
                    continue

            return record

        return None

    # ------------------------------------------------------------------
    # List / load / delete
    # ------------------------------------------------------------------

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """Return a summary list of all checkpoints, newest-first.

        Each element is a dict with keys:
        ``id``, ``goal_preview``, ``step_num``, ``timestamp``, ``status``.
        """
        files = _discover_checkpoint_files(self._dir)
        result: list[dict[str, Any]] = []

        for fpath in files:
            try:
                with open(fpath, encoding="utf-8") as fh:
                    record = json.load(fh)
            except Exception as exc:
                logger.debug("Skipping corrupt checkpoint %s: %s", fpath, exc)
                continue

            if not isinstance(record, dict) or "id" not in record:
                continue

            result.append(
                {
                    "id": record["id"],
                    "goal_preview": record.get("goal_preview", ""),
                    "step_num": record.get("step_num", 0),
                    "timestamp": record.get("timestamp", ""),
                    "status": record.get("status", "unknown"),
                }
            )

        return result

    def load(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load a full checkpoint by its ``id``.

        Returns the checkpoint dict, or ``None`` if not found or corrupt.
        """
        # Sanitise — prevent directory traversal.
        safe_id = os.path.basename(checkpoint_id)
        fpath = os.path.join(self._dir, f"{safe_id}.json")

        if not os.path.isfile(fpath):
            logger.warning("Checkpoint not found: %s", safe_id)
            return None

        try:
            with open(fpath, encoding="utf-8") as fh:
                record = json.load(fh)
            logger.info("Checkpoint loaded: %s", safe_id[:8])
            return record
        except Exception as exc:
            logger.error("Failed to load checkpoint %s: %s", safe_id[:8], exc)
            return None

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a single checkpoint by ``id``.

        Returns ``True`` on success (including when the file didn't exist).
        """
        safe_id = os.path.basename(checkpoint_id)
        fpath = os.path.join(self._dir, f"{safe_id}.json")

        with self._lock:
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    logger.info("Checkpoint deleted: %s", safe_id[:8])
                return True
            except Exception as exc:
                logger.error("Failed to delete checkpoint %s: %s", safe_id[:8], exc)
                return False

    def clear_all(self) -> int:
        """Delete **all** checkpoint files.

        Returns the number of files removed.
        """
        files = _discover_checkpoint_files(self._dir)
        removed = 0

        with self._lock:
            for fpath in files:
                try:
                    os.remove(fpath)
                    removed += 1
                except Exception as exc:
                    logger.warning("Failed to remove %s: %s", fpath, exc)

        logger.info("Cleared %d checkpoint(s)", removed)
        return removed

    # ------------------------------------------------------------------
    # Convenience: auto-save gate
    # ------------------------------------------------------------------

    @staticmethod
    def should_auto_save(step_num: int) -> bool:
        """Return ``True`` if the engine should auto-save at *step_num*.

        The convention is to save every 5th step to avoid excessive disk
        I/O while still keeping a reasonably fresh checkpoint::

            if CheckpointManager.should_auto_save(step_num):
                cm.save(...)
        """
        return step_num > 0 and step_num % 5 == 0
