"""Sentinel Desktop — System Dashboard API.

Real-time system health metrics endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from core.utils import iso_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ─── Constants ───────────────────────────────────────────────────────────────

GPU_QUERY_TIMEOUT = 5
DASHBOARD_OVERVIEW_TIMEOUT = 10.0
HEALTH_CHECK_TIMEOUT = 5.0
METRICS_TIMEOUT = 3.0

# Dashboard thresholds and limits
GPU_DATA_FIELD_COUNT = 6
CPU_MEMORY_WARNING_THRESHOLD = 90
HEALTH_CHECK_HISTORY_MAX_SIZE = 100
HEALTH_CHECK_HISTORY_RETENTION = 50

# ─── System Metrics ───────────────────────────────────────────────────────

_start_time = time.time()
_health_checks: list[dict[str, Any]] = []


def _get_cpu_info() -> dict[str, Any]:
    """Get CPU information."""
    try:
        import psutil
        return {
            # interval=None is non-blocking; returns usage since last call (0.0 on first call).
            "percent": psutil.cpu_percent(interval=None),
            "count_physical": psutil.cpu_count(logical=False),
            "count_logical": psutil.cpu_count(logical=True),
            "freq_current": round(psutil.cpu_freq().current, 0) if psutil.cpu_freq() else None,
        }
    except ImportError:
        return {"percent": 0, "count_logical": platform.processor() or "unknown"}


def _get_memory_info() -> dict[str, Any]:
    """Get memory information."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 1),
            "used_gb": round(mem.used / (1024**3), 1),
            "available_gb": round(mem.available / (1024**3), 1),
            "percent": mem.percent,
        }
    except ImportError:
        return {"total_gb": 0, "percent": 0}


def _get_disk_info() -> list[dict[str, Any]]:
    """Get disk information."""
    try:
        import psutil
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    "mount": partition.mountpoint,
                    "total_gb": round(usage.total / (1024**3), 1),
                    "used_gb": round(usage.used / (1024**3), 1),
                    "free_gb": round(usage.free / (1024**3), 1),
                    "percent": usage.percent,
                })
            except (PermissionError, OSError):
                continue
        return disks
    except ImportError:
        return []


def _get_gpu_info() -> list[dict[str, Any]]:
    """Get GPU information (Windows only, uses nvidia-smi)."""
    gpus = []
    nvidia_smi_path = shutil.which("nvidia-smi")
    if not nvidia_smi_path:
        logger.debug("nvidia-smi not found in PATH")
        return []
    try:
        result = subprocess.run(  # noqa: S603 - nvidia-smi is a trusted system utility for GPU monitoring
            [
                nvidia_smi_path,
                "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=GPU_QUERY_TIMEOUT,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= GPU_DATA_FIELD_COUNT:
                    gpus.append({
                        "name": parts[0],
                        "memory_used_mb": float(parts[1]),
                        "memory_total_mb": float(parts[2]),
                        "temperature_c": float(parts[3]),
                        "utilization_pct": float(parts[4]),
                        "power_draw_w": float(parts[5]),
                    })
    except (FileNotFoundError, OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.debug("GPU info unavailable: %s", exc)
    return gpus


def _count_log_entries() -> dict[str, int]:
    """Count entries in forensic log."""
    try:
        log_dir = Path.home() / ".sentinel" / "logs"
        if log_dir.exists():
            return {"total_logs": len(list(log_dir.glob("*.json")))}
    except OSError as exc:
        logger.debug("Log entry count unavailable: %s", exc)
    return {"total_logs": 0}


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/overview")
async def dashboard_overview() -> dict[str, Any]:
    """Full system dashboard overview."""
    uptime_seconds = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Run potentially blocking I/O helpers in the thread pool so the event
    # loop stays responsive. _get_gpu_info() spawns nvidia-smi (up to 5s);
    # disk/memory calls are typically fast but still use blocking syscalls.
    # Use timeout to ensure the API remains responsive.
    try:
        cpu, memory, disks, gpus, logs = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(_get_cpu_info),
                asyncio.to_thread(_get_memory_info),
                asyncio.to_thread(_get_disk_info),
                asyncio.to_thread(_get_gpu_info),
                asyncio.to_thread(_count_log_entries),
            ),
            timeout=DASHBOARD_OVERVIEW_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Dashboard overview timed out after %s seconds", DASHBOARD_OVERVIEW_TIMEOUT)
        # Return partial data with default values
        cpu = {"percent": 0, "cores": 0}
        memory = {"percent": 0, "used_gb": 0, "total_gb": 0}
        disks = []
        gpus = []
        logs = {"total": 0}

    return {
        "timestamp": iso_now(),
        "system": {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "hostname": platform.node(),
            "python_version": platform.python_version(),
            "uptime": f"{hours}h {minutes}m {seconds}s",
            "uptime_seconds": uptime_seconds,
        },
        "cpu": cpu,
        "memory": memory,
        "disks": disks,
        "gpus": gpus,
        "logs": logs,
        "health_checks": _health_checks[-20:],
    }


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """No-auth health check for monitoring."""
    try:
        mem, cpu = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(_get_memory_info),
                asyncio.to_thread(_get_cpu_info),
            ),
            timeout=HEALTH_CHECK_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Health check timed out after %s seconds", HEALTH_CHECK_TIMEOUT)
        mem = {"percent": 0}
        cpu = {"percent": 0}

    status = "healthy"
    issues = []

    if mem.get("percent", 0) > CPU_MEMORY_WARNING_THRESHOLD:
        status = "warning"
        issues.append(f"Memory at {mem['percent']}%")
    if cpu.get("percent", 0) > CPU_MEMORY_WARNING_THRESHOLD:
        status = "warning"
        issues.append(f"CPU at {cpu['percent']}%")

    result = {
        "status": status,
        "timestamp": iso_now(),
        "issues": issues,
    }

    _health_checks.append(result)
    if len(_health_checks) > HEALTH_CHECK_HISTORY_MAX_SIZE:
        _health_checks[:] = _health_checks[-HEALTH_CHECK_HISTORY_RETENTION:]

    return result


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Lightweight metrics for monitoring dashboards."""
    try:
        mem, cpu = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(_get_memory_info),
                asyncio.to_thread(_get_cpu_info),
            ),
            timeout=METRICS_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Metrics endpoint timed out after %s seconds", METRICS_TIMEOUT)
        mem = {"percent": 0, "used_gb": 0}
        cpu = {"percent": 0}

    return {
        "cpu_percent": cpu.get("percent", 0),
        "memory_percent": mem.get("percent", 0),
        "memory_used_gb": mem.get("used_gb", 0),
    }
