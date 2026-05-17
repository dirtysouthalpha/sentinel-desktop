"""
Sentinel Desktop — System Dashboard API.
Real-time system health metrics endpoint.
"""

from __future__ import annotations

import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ─── System Metrics ───────────────────────────────────────────────────────

_start_time = time.time()
_health_checks: list[dict[str, Any]] = []


def _get_cpu_info() -> dict[str, Any]:
    """Get CPU information."""
    try:
        import psutil
        return {
            "percent": psutil.cpu_percent(interval=0.5),
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
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    gpus.append({
                        "name": parts[0],
                        "memory_used_mb": float(parts[1]),
                        "memory_total_mb": float(parts[2]),
                        "temperature_c": float(parts[3]),
                        "utilization_pct": float(parts[4]),
                        "power_draw_w": float(parts[5]),
                    })
    except Exception:
        pass
    return gpus


def _count_log_entries() -> dict[str, int]:
    """Count entries in forensic log."""
    try:
        log_dir = Path.home() / ".sentinel" / "logs"
        if log_dir.exists():
            return {"total_logs": len(list(log_dir.glob("*.json")))}
    except Exception:
        pass
    return {"total_logs": 0}


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/overview")
async def dashboard_overview() -> dict[str, Any]:
    """Full system dashboard overview."""
    uptime_seconds = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "hostname": platform.node(),
            "python_version": platform.python_version(),
            "uptime": f"{hours}h {minutes}m {seconds}s",
            "uptime_seconds": uptime_seconds,
        },
        "cpu": _get_cpu_info(),
        "memory": _get_memory_info(),
        "disks": _get_disk_info(),
        "gpus": _get_gpu_info(),
        "logs": _count_log_entries(),
        "health_checks": _health_checks[-20:],
    }


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """No-auth health check for monitoring."""
    mem = _get_memory_info()
    cpu = _get_cpu_info()
    status = "healthy"
    issues = []

    if mem.get("percent", 0) > 90:
        status = "warning"
        issues.append(f"Memory at {mem['percent']}%")
    if cpu.get("percent", 0) > 90:
        status = "warning"
        issues.append(f"CPU at {cpu['percent']}%")

    result = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "issues": issues,
    }

    _health_checks.append(result)
    if len(_health_checks) > 100:
        _health_checks[:] = _health_checks[-50:]

    return result


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Lightweight metrics for monitoring dashboards."""
    mem = _get_memory_info()
    cpu = _get_cpu_info()
    return {
        "cpu_percent": cpu.get("percent", 0),
        "memory_percent": mem.get("percent", 0),
        "memory_used_gb": mem.get("used_gb", 0),
    }
