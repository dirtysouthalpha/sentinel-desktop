"""System information: CPU, memory, disk, network."""

import logging
import os
import platform
import socket
from typing import Any

import psutil

logger = logging.getLogger(__name__)


def brief_system_info() -> str:
    """Return a concise system summary string for the agent prompt."""
    try:
        mem = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        ram_line = (
            f"RAM: {mem.used / (1024**3):.1f}/{mem.total / (1024**3):.1f} GB ({mem.percent}%)"
        )
    except (OSError, RuntimeError) as exc:
        logger.warning("psutil call failed in brief_system_info: %s", exc)
        cpu_pct = 0.0
        cpu_count = 0
        ram_line = "RAM: unavailable"
    try:
        hostname = socket.gethostname()
    except OSError:
        hostname = "unknown"
    return (
        f"OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
        f"Hostname: {hostname}\n"
        f"CPU: {cpu_pct}% used, {cpu_count} cores\n"
        f"{ram_line}\n"
        f"Screen: {_screen_resolution()}"
    )


def system_info() -> dict[str, Any]:
    """Return full system info as a dict."""
    try:
        mem = psutil.virtual_memory()
        mem_total_gb = round(mem.total / (1024**3), 1)
        mem_used_gb = round(mem.used / (1024**3), 1)
        mem_percent = mem.percent
    except (OSError, RuntimeError) as exc:
        logger.warning("psutil memory call failed in system_info: %s", exc)
        mem_total_gb = 0.0
        mem_used_gb = 0.0
        mem_percent = 0.0

    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
    except (OSError, RuntimeError) as exc:
        logger.warning("psutil cpu call failed in system_info: %s", exc)
        cpu_pct = 0.0
        cpu_count = 0

    try:
        hostname = socket.gethostname()
    except OSError as exc:
        logger.warning("socket.gethostname() failed: %s", exc)
        hostname = "unknown"

    # On Windows, "/" is not a valid drive root — use the system drive instead.
    if platform.system() == "Windows":
        root = os.environ.get("SystemDrive", "C:") + "\\"
    else:
        root = "/"
    try:
        disk = psutil.disk_usage(root)
    except (OSError, RuntimeError) as exc:
        logger.warning("disk_usage(%s) failed: %s", root, exc)

        class _ZeroDisk:
            total: int = 0
            used: int = 0
            percent: float = 0.0

        disk = _ZeroDisk()
    return {
        "os": f"{platform.system()} {platform.release()}",
        "hostname": hostname,
        "arch": platform.machine(),
        "cpu_percent": cpu_pct,
        "cpu_count": cpu_count,
        "memory_total_gb": mem_total_gb,
        "memory_used_gb": mem_used_gb,
        "memory_percent": mem_percent,
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_percent": disk.percent,
        "screen_resolution": _screen_resolution(),
    }


def _screen_resolution() -> str:  # noqa: F811 — intentional re-export
    try:
        import pyautogui

        w, h = pyautogui.size()
        return f"{w}x{h}"
    except Exception as exc:
        logger.debug("Failed to detect screen resolution: %s", exc)
        return "unknown"
