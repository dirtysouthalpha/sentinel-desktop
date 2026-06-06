"""Sentinel Desktop v3.0 — Process management utilities.

Provides functions to list, start, and kill system processes.
Integrates with psutil for cross-platform process operations.
"""

import logging
import subprocess
from typing import Any

import psutil

logger = logging.getLogger(__name__)

# Dangerous command patterns that should never be passed to start_process.
_DANGEROUS_CMD_PATTERNS = (
    "rm -rf",
    "del /f /q",
    "format ",
    "diskpart",
    "mkfs.",
    "dd if=/dev",
    "> /dev/sd",
)


def _sanitize_command(path: str, args: list[str] | None = None) -> None:
    """Validate that a command path and arguments are safe to execute.

    Raises ``ValueError`` if dangerous patterns are detected.
    """
    full_cmd = path + " " + " ".join(args or [])
    lower = full_cmd.lower().strip()
    for pattern in _DANGEROUS_CMD_PATTERNS:
        if pattern in lower:
            raise ValueError(f"Command contains potentially dangerous pattern: '{pattern}'")
    # Block shell metacharacters in the path itself
    shell_chars = {"&", "|", ";", "`", "$", ">", "<"}
    if any(c in path for c in shell_chars):
        raise ValueError(f"Executable path contains shell metacharacters: '{path}'")


def list_processes(sort_by: str = "cpu", limit: int = 50) -> list[dict[str, Any]]:
    """List running processes. Returns list of dicts."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            info["memory_mb"] = (
                round(info["memory_info"].rss / (1024 * 1024), 1) if info["memory_info"] else 0
            )
            del info["memory_info"]
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            logger.debug("Skipping vanished/inaccessible process")

    key = "cpu_percent" if sort_by == "cpu" else "memory_mb"
    procs.sort(key=lambda p: p.get(key, 0) or 0, reverse=True)
    return procs[:limit]


def start_process(path: str, args: list[str] | None = None) -> int | None:
    """Start a process. Returns PID or None on failure.

    Validates the command against dangerous patterns before execution.
    """
    try:
        _sanitize_command(path, args)
        cmd = [path] + (args or [])
        # Discard stderr so the pipe never fills and blocks; we only care
        # whether Popen() itself raises (command not found, permission, etc.).
        proc = subprocess.Popen(  # noqa: S603 - Intentional process execution for desktop automation
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return proc.pid
    except (OSError, subprocess.SubprocessError, FileNotFoundError, ValueError):
        logger.exception("start_process(%s) failed", path)
        return None


def kill_process(target: int | str | None) -> bool:
    """Kill a process by PID (int) or name (str). Returns True on success."""
    if target is None or target == "":
        logger.warning("kill_process called with empty target")
        return False
    try:
        if isinstance(target, int):
            p = psutil.Process(target)
            p.kill()
            return True
        # Kill by name (string match)
        name = str(target).lower()
        if not name:
            return False
        killed = False
        for p in psutil.process_iter(["name", "pid"]):
            proc_name = (p.info.get("name") or "").lower()
            if name in proc_name:
                try:
                    p.kill()
                    killed = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    logger.debug("Process %s vanished during kill", p.info.get("name", "?"))
        return killed
    except psutil.NoSuchProcess:
        logger.debug("Process %s no longer exists", target)
        return False
    except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
        logger.exception("kill_process(%s) failed", target)
        return False
