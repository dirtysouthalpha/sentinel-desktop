"""Sentinel Desktop v3.0 — Process management utilities.

Provides functions to list, start, and kill system processes.
Integrates with psutil for cross-platform process operations.
"""

import logging
import subprocess
import sys
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


def set_priority(pid: int, priority: str) -> bool:
    """Set process priority. Returns True on success.

    Priority values: idle, low, normal, high, realtime.
    """
    try:
        p = psutil.Process(pid)
        priority_map = {
            "idle": psutil.IDLE_PRIORITY_CLASS if hasattr(psutil, "IDLE_PRIORITY_CLASS") else 19,
            "low": psutil.BELOW_NORMAL_PRIORITY_CLASS
            if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS")
            else 10,
            "normal": psutil.NORMAL_PRIORITY_CLASS
            if hasattr(psutil, "NORMAL_PRIORITY_CLASS")
            else 0,
            "high": psutil.ABOVE_NORMAL_PRIORITY_CLASS
            if hasattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS")
            else -5,
            "realtime": psutil.REALTIME_PRIORITY_CLASS
            if hasattr(psutil, "REALTIME_PRIORITY_CLASS")
            else -20,
        }
        pri = priority_map.get(priority.lower())
        if pri is None:
            logger.warning("Unknown priority: %s", priority)
            return False
        p.nice(pri)
        return True
    except psutil.NoSuchProcess:
        logger.debug("Process %d not found", pid)
        return False
    except (psutil.AccessDenied, OSError):
        logger.exception("set_priority(%d) failed", pid)
        return False


def get_env(name: str) -> str | None:
    """Get an environment variable value."""
    import os

    return os.environ.get(name)


def set_env(name: str, value: str, permanent: bool = False) -> bool:
    """Set an environment variable. Returns True on success."""
    import os

    try:
        os.environ[name] = value
        if permanent and sys.platform == "win32":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                winreg.KEY_SET_VALUE,
            )
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            winreg.CloseKey(key)
        return True
    except OSError:
        logger.exception("set_env(%s) failed", name)
        return False


def service_control(
    name: str,
    action: str,
) -> dict[str, Any]:
    """Control a Windows service. Returns result dict.

    Actions: start, stop, restart, query.
    """
    import sys

    if sys.platform != "win32":
        return {"success": False, "error": "Windows services not available on this platform"}

    import ctypes

    if action == "query":
        try:
            advapi = ctypes.windll.advapi32  # type: ignore[attr-defined]
            # Set prototypes so ctypes properly marshals 64-bit HANDLE values.
            advapi.OpenSCManagerW.restype = ctypes.c_void_p
            advapi.OpenSCManagerW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
            advapi.OpenServiceW.restype = ctypes.c_void_p
            advapi.OpenServiceW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
            advapi.CloseServiceHandle.restype = ctypes.c_int
            advapi.CloseServiceHandle.argtypes = [ctypes.c_void_p]
            advapi.QueryServiceStatus.restype = ctypes.c_int
            advapi.QueryServiceStatus.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

            sc = advapi.OpenSCManagerW(None, None, 0x0001)
            if not sc:
                return {"success": False, "error": "Failed to open SCManager (access denied)"}

            svc = advapi.OpenServiceW(sc, name, 0x0004)
            if not svc:
                advapi.CloseServiceHandle(sc)
                return {"success": False, "error": f"Service '{name}' not found"}

            status = ctypes.c_uint32()
            advapi.QueryServiceStatus(svc, ctypes.byref(status))
            advapi.CloseServiceHandle(svc)
            advapi.CloseServiceHandle(sc)
            state_map = {
                1: "stopped",
                2: "start_pending",
                3: "stop_pending",
                4: "running",
                5: "continue_pending",
                6: "pause_pending",
                7: "paused",
            }
            return {
                "success": True,
                "service": name,
                "state": state_map.get(status.value, f"unknown({status.value})"),
            }
        except OSError as exc:
            return {"success": False, "error": str(exc)}

    try:
        import subprocess

        result = subprocess.run(
            ["net", action, name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "service": name,
            "action": action,
            "output": (result.stdout + result.stderr).strip(),
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return {"success": False, "error": str(exc)}
