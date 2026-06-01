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
        cpu_pct = psutil.cpu_percent(interval=None)  # non-blocking
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


def _memory_stats() -> tuple[float, float, float]:
    """Return (total_gb, used_gb, percent) or zeros on failure."""
    try:
        mem = psutil.virtual_memory()
        return round(mem.total / (1024**3), 1), round(mem.used / (1024**3), 1), mem.percent
    except (OSError, RuntimeError) as exc:
        logger.warning("psutil memory call failed: %s", exc)
        return 0.0, 0.0, 0.0


def _cpu_stats() -> tuple[float, int]:
    """Return (cpu_percent, cpu_count) or zeros on failure."""
    try:
        return psutil.cpu_percent(interval=None), psutil.cpu_count() or 0
    except (OSError, RuntimeError) as exc:
        logger.warning("psutil cpu call failed: %s", exc)
        return 0.0, 0


def _disk_stats() -> tuple[float, float, float]:
    """Return (total_gb, used_gb, percent) for the system root or zeros on failure."""
    root = (os.environ.get("SystemDrive", "C:") + "\\") if platform.system() == "Windows" else "/"
    try:
        disk = psutil.disk_usage(root)
        return round(disk.total / (1024**3), 1), round(disk.used / (1024**3), 1), disk.percent
    except (OSError, RuntimeError) as exc:
        logger.warning("disk_usage(%s) failed: %s", root, exc)
        return 0.0, 0.0, 0.0


def system_info() -> dict[str, Any]:
    """Return full system info as a dict."""
    mem_total_gb, mem_used_gb, mem_percent = _memory_stats()
    cpu_pct, cpu_count = _cpu_stats()
    disk_total_gb, disk_used_gb, disk_percent = _disk_stats()

    try:
        hostname = socket.gethostname()
    except OSError as exc:
        logger.warning("socket.gethostname() failed: %s", exc)
        hostname = "unknown"

    return {
        "os": f"{platform.system()} {platform.release()}",
        "hostname": hostname,
        "arch": platform.machine(),
        "cpu_percent": cpu_pct,
        "cpu_count": cpu_count,
        "memory_total_gb": mem_total_gb,
        "memory_used_gb": mem_used_gb,
        "memory_percent": mem_percent,
        "disk_total_gb": disk_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_percent": disk_percent,
        "screen_resolution": _screen_resolution(),
    }


def _screen_resolution() -> str:  # noqa: F811 — intentional re-export
    """Detect the primary screen resolution via pyautogui, falling back to ``'unknown'``."""
    try:
        import pyautogui

        w, h = pyautogui.size()
        return f"{w}x{h}"
    except (ImportError, OSError, RuntimeError) as exc:
        logger.debug("Failed to detect screen resolution: %s", exc)
        return "unknown"
