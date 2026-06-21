"""Sentinel Desktop v16.0 — File and process watcher.

Provides watch_file (polling-based) and watch_process that notify when a
file changes or a process starts/stops. Uses stdlib + psutil (already
required). No new dependencies.

Usage::

    from core.file_watcher import watch_file, watch_process

    # Block until file changes or timeout
    changed = watch_file("/tmp/output.log", timeout=30)

    # Block until process named 'notepad' starts
    pid = watch_process("notepad", event="start", timeout=60)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import psutil

logger = logging.getLogger(__name__)

# ── File watcher ─────────────────────────────────────────────────────────────


def watch_file(
    path: str,
    timeout: float = 60.0,
    poll_interval: float = 0.5,
    event: str = "modify",
) -> dict[str, Any]:
    """Watch a file for changes and return when the event occurs.

    Args:
        path:          File path to watch.
        timeout:       Maximum seconds to wait. Default 60.
        poll_interval: Polling frequency in seconds. Default 0.5.
        event:         ``"modify"`` (mtime change), ``"create"`` (file
                       appears), or ``"delete"`` (file removed).

    Returns:
        Dict with ``success``, ``event``, ``path``, ``elapsed_s``,
        and ``output``.
    """
    p = Path(path)
    start = time.monotonic()
    deadline = start + timeout
    event = event.lower()

    # Get initial state
    initial_exists = p.exists()
    initial_mtime = p.stat().st_mtime if initial_exists else None

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - start
        try:
            now_mtime = p.stat().st_mtime
            now_exists = True
        except FileNotFoundError:
            now_exists = False
            now_mtime = None

        triggered = False
        if event == "modify" and initial_exists and now_exists:
            triggered = now_mtime != initial_mtime
        elif event == "create":
            triggered = now_exists and not initial_exists
        elif event == "delete":
            triggered = not now_exists and initial_exists

        if triggered:
            return {
                "success": True,
                "event": event,
                "path": str(p),
                "elapsed_s": round(elapsed, 2),
                "output": f"File {event} event detected on {path!r} after {elapsed:.1f}s",
            }
        time.sleep(poll_interval)

    return {
        "success": False,
        "event": event,
        "path": str(p),
        "elapsed_s": round(timeout, 2),
        "output": f"Timeout after {timeout}s waiting for {event} on {path!r}",
        "error": "timeout",
    }


def watch_file_content(
    path: str,
    contains: str,
    timeout: float = 60.0,
    poll_interval: float = 1.0,
) -> dict[str, Any]:
    """Wait until a text file contains *contains*.

    Useful for watching log files for a specific message.

    Args:
        path:          File to watch.
        contains:      Substring to search for.
        timeout:       Max seconds. Default 60.
        poll_interval: Check interval in seconds.
    """
    p = Path(path)
    start = time.monotonic()
    deadline = start + timeout
    last_size = 0

    while time.monotonic() < deadline:
        if p.exists():
            try:
                size = p.stat().st_size
                if size != last_size:
                    text = p.read_text(encoding="utf-8", errors="replace")
                    last_size = size
                    if contains in text:
                        return {
                            "success": True,
                            "path": str(p),
                            "found": contains,
                            "elapsed_s": round(time.monotonic() - start, 2),
                            "output": f"Found {contains!r} in {path!r}",
                        }
            except OSError:
                pass
        time.sleep(poll_interval)

    return {
        "success": False,
        "path": str(p),
        "error": "timeout",
        "output": f"Timeout after {timeout}s — {contains!r} not found in {path!r}",
    }


# ── Process watcher ──────────────────────────────────────────────────────────


def watch_process(
    name: str,
    event: str = "start",
    pid: int | None = None,
    timeout: float = 60.0,
    poll_interval: float = 1.0,
) -> dict[str, Any]:
    """Wait for a process event (start, stop, or cpu_spike).

    Args:
        name:          Process name (partial match, case-insensitive).
        event:         ``"start"``, ``"stop"``, or ``"cpu_spike"``.
        pid:           Match a specific PID instead of name.
        timeout:       Max seconds to wait. Default 60.
        poll_interval: Check interval. Default 1s.

    Returns:
        Dict with ``success``, ``event``, ``pid`` (if found), ``name``.
    """
    start = time.monotonic()
    deadline = start + timeout
    event = event.lower()

    def _find_proc() -> psutil.Process | None:
        if pid is not None:
            try:
                p = psutil.Process(pid)
                return p if p.is_running() else None
            except psutil.NoSuchProcess:
                return None
        for p in psutil.process_iter(["name", "pid"]):
            try:
                if name.lower() in (p.info.get("name") or "").lower():
                    return p
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return None

    initial_proc = _find_proc()

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - start
        proc = _find_proc()

        triggered = False
        result_pid = None

        if event == "start":
            triggered = proc is not None and initial_proc is None
            if triggered:
                result_pid = proc.pid
        elif event == "stop":
            triggered = proc is None and initial_proc is not None
            result_pid = initial_proc.pid if initial_proc else None
        elif event == "cpu_spike":
            if proc is not None:
                try:
                    cpu = proc.cpu_percent(interval=poll_interval)
                    if cpu > 80:
                        triggered = True
                        result_pid = proc.pid
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        if triggered:
            return {
                "success": True,
                "event": event,
                "name": name,
                "pid": result_pid,
                "elapsed_s": round(elapsed, 2),
                "output": (
                    f"Process {event!r} event for {name!r} (PID {result_pid}) after {elapsed:.1f}s"
                ),
            }
        time.sleep(poll_interval)

    return {
        "success": False,
        "event": event,
        "name": name,
        "error": "timeout",
        "output": f"Timeout after {timeout}s waiting for {event!r} on {name!r}",
    }
