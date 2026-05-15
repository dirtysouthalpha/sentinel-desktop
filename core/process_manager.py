"""Process management: list, start, kill processes."""

import logging
import subprocess
from typing import Any

import psutil

logger = logging.getLogger(__name__)


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
            pass

    key = "cpu_percent" if sort_by == "cpu" else "memory_mb"
    procs.sort(key=lambda p: p.get(key, 0) or 0, reverse=True)
    return procs[:limit]


def start_process(path: str, args: list[str] | None = None) -> int:
    """Start a process. Returns PID or 0 on failure."""
    try:
        cmd = [path] + (args or [])
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc.pid
    except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
        logger.exception("start_process(%s) failed", path)
        return 0


def kill_process(target: int | str) -> bool:
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
                    pass
        return killed
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, OSError) as e:
        logger.exception("kill_process(%s) failed", target)
        return False
