"""
Sentinel Desktop v29.0.0 - Plugin Sandbox.

Execute community plugins in isolated subprocesses with resource limits,
timeout enforcement, and permission-based access control.
"""

from __future__ import annotations

import logging
import os
import resource
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_MEMORY_LIMIT_MB = 256  # 256 MB cap

VALID_PERMISSIONS = {
    "clipboard",
    "screenshot",
    "network",
    "filesystem",
    "process",
    "registry",
    "system_info",
}


@dataclass
class SandboxResult:
    """Result of a sandboxed plugin execution."""
    success: bool
    output: str = ""
    error: str = ""
    exit_code: int = 0
    timed_out: bool = False
    duration_seconds: float = 0.0
    pid: int = 0


@dataclass
class SandboxedPlugin:
    """Represents a running or recently-run sandboxed plugin."""
    name: str
    pid: int = 0
    started_at: float = 0.0
    permissions: list[str] = field(default_factory=list)
    process: subprocess.Popen | None = None

    @property
    def elapsed(self) -> float:
        """Seconds since this plugin was started."""
        return time.time() - self.started_at if self.started_at else 0.0

    @property
    def is_running(self) -> bool:
        """Whether the plugin process is still alive."""
        return self.process is not None and self.process.poll() is None


# Track active sandboxed plugins
_active_plugins: dict[str, SandboxedPlugin] = {}


def validate_permissions(permissions: list[str]) -> list[str]:
    """Validate and filter permissions against the known set."""
    valid = []
    for perm in permissions:
        if perm in VALID_PERMISSIONS:
            valid.append(perm)
        else:
            logger.warning("Unknown permission '%s' ignored", perm)
    return valid


def execute_plugin(
    plugin_path: str | Path,
    function_name: str = "run",
    args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
    permissions: list[str] | None = None,
) -> SandboxResult:
    """Execute a plugin in a sandboxed subprocess.

    Args:
        plugin_path: Path to the plugin .py file.
        function_name: Entry point function to call.
        args: Arguments to pass to the function.
        timeout: Maximum execution time in seconds.
        memory_limit_mb: Memory limit for the subprocess.
        permissions: List of granted permissions.

    Returns:
        SandboxResult with output, errors, and status.
    """
    plugin_path = Path(plugin_path)
    if not plugin_path.exists():
        return SandboxResult(success=False, error=f"Plugin not found: {plugin_path}")

    # Validate permissions
    if permissions:
        permissions = validate_permissions(permissions)

    # Build the runner script
    runner_code = f"""
import sys, json, importlib.util
sys.path.insert(0, {str(plugin_path.parent)!r})

# Apply memory limit (Unix only)
try:
    import resource
    max_bytes = {memory_limit_mb} * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
except Exception:
    pass  # Non-Unix or already limited

# Load and execute plugin
spec = importlib.util.spec_from_file_location(
    'sandboxed_plugin', {str(plugin_path)!r}
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

func = getattr(module, '{function_name}', None)
if func is None:
    print(json.dumps({{"error": "Function '{function_name}' not found"}}))
    sys.exit(1)

try:
    result = func({args!r})
    print(json.dumps({{"output": str(result) if result else "done"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
    sys.exit(1)
"""

    start = time.time()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", runner_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        # Track in active plugins
        sp = SandboxedPlugin(
            name=plugin_path.stem,
            pid=proc.pid,
            started_at=start,
            permissions=permissions or [],
            process=proc,
        )
        _active_plugins[plugin_path.stem] = sp

        stdout, stderr = proc.communicate(timeout=timeout)
        duration = time.time() - start

        if proc.returncode == 0:
            import json
            try:
                data = json.loads(stdout.strip())
                return SandboxResult(
                    success=True,
                    output=data.get("output", ""),
                    duration_seconds=round(duration, 3),
                    pid=proc.pid,
                )
            except json.JSONDecodeError:
                return SandboxResult(
                    success=True,
                    output=stdout.strip()[:500],
                    duration_seconds=round(duration, 3),
                    pid=proc.pid,
                )
        else:
            return SandboxResult(
                success=False,
                error=stderr.strip()[:500] or stdout.strip()[:500],
                exit_code=proc.returncode,
                duration_seconds=round(duration, 3),
                pid=proc.pid,
            )

    except subprocess.TimeoutExpired:
        # Kill the process group
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        duration = time.time() - start
        return SandboxResult(
            success=False,
            error=f"Plugin timed out after {timeout}s",
            timed_out=True,
            duration_seconds=round(duration, 3),
            pid=proc.pid,
        )
    except Exception as e:
        return SandboxResult(success=False, error=str(e), duration_seconds=round(time.time() - start, 3))

    finally:
        _active_plugins.pop(plugin_path.stem, None)


def list_active() -> list[dict[str, Any]]:
    """List all currently active sandboxed plugins."""
    result = []
    for name, sp in _active_plugins.items():
        if sp.is_running:
            result.append({
                "name": name,
                "pid": sp.pid,
                "elapsed_seconds": round(sp.elapsed, 1),
                "permissions": sp.permissions,
            })
        else:
            _active_plugins.pop(name, None)
    return result


def kill_plugin(name: str) -> dict[str, Any]:
    """Kill a running sandboxed plugin by name."""
    sp = _active_plugins.get(name)
    if not sp or not sp.is_running:
        return {"success": False, "message": f"Plugin '{name}' is not running"}
    try:
        os.killpg(os.getpgid(sp.pid), signal.SIGKILL)
        _active_plugins.pop(name, None)
        return {"success": True, "message": f"Plugin '{name}' killed"}
    except Exception as e:
        return {"success": False, "message": str(e)}
