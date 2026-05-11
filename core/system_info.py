"""System information: CPU, memory, disk, network."""
import psutil
import platform
import socket
import logging

logger = logging.getLogger(__name__)


def brief_system_info() -> str:
    """Return a concise system summary string for the agent prompt."""
    mem = psutil.virtual_memory()
    cpu_pct = psutil.cpu_percent(interval=0.5)
    return (
        f"OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
        f"Hostname: {socket.gethostname()}\n"
        f"CPU: {cpu_pct}% used, {psutil.cpu_count()} cores\n"
        f"RAM: {mem.used / (1024**3):.1f}/{mem.total / (1024**3):.1f} GB ({mem.percent}%)\n"
        f"Screen: {_screen_resolution()}"
    )


def system_info() -> dict:
    """Return full system info as a dict."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "os": f"{platform.system()} {platform.release()}",
        "hostname": socket.gethostname(),
        "arch": platform.machine(),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "cpu_count": psutil.cpu_count(),
        "memory_total_gb": round(mem.total / (1024**3), 1),
        "memory_used_gb": round(mem.used / (1024**3), 1),
        "memory_percent": mem.percent,
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_percent": disk.percent,
        "screen_resolution": _screen_resolution(),
    }


def _screen_resolution() -> str:
    try:
        import pyautogui
        w, h = pyautogui.size()
        return f"{w}x{h}"
    except Exception:
        return "unknown"
