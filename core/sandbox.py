"""
Sentinel Desktop v31.0.0 - Plugin Sandbox.

Execute community plugins in isolated subprocesses with resource limits,
timeout enforcement, and permission-based access control.

Platform isolation backends
---------------------------
Two real backends exist, selected by :func:`sandbox_backend`:

``windows-job-object``
    The child is assigned to a Win32 Job Object carrying
    ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` / ``JOB_OBJECT_LIMIT_JOB_MEMORY``
    (the memory cap) plus ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` and
    ``JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION``. ``TerminateJobObject``
    then kills the whole process tree on timeout.

``posix-rlimit``
    The child calls ``setrlimit(RLIMIT_AS, ...)`` on itself and runs in its
    own session (``setsid``), so ``killpg`` reaps the whole group.

If neither backend is available this module **refuses to run plugins** and
raises :class:`SandboxUnavailableError`. It never silently degrades to
unsandboxed execution — a caller that cannot isolate a plugin must not run
it. Prior to v31 the module did the opposite: ``import resource`` at module
scope made the entire module unimportable on Windows, so every caller fell
back to running plugins with no isolation at all.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ``resource`` is Unix-only. Importing it at module scope (pre-v31) raised
# ModuleNotFoundError on Windows and killed the whole sandbox module.
try:  # pragma: no cover - platform dependent
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_MEMORY_LIMIT_MB = 256  # 256 MB cap

# Max processes allowed inside a plugin's job object (the runner itself plus a
# small budget for legitimately shelling out). Bounds fork bombs; the whole
# tree is still reaped via TerminateJobObject / KILL_ON_JOB_CLOSE.
DEFAULT_MAX_PROCESSES = 8

VALID_PERMISSIONS = {
    "clipboard",
    "screenshot",
    "network",
    "filesystem",
    "process",
    "registry",
    "system_info",
}

# A plugin entry point must be a plain Python identifier. ``function_name`` is
# interpolated into the generated runner source, so anything else is code
# injection (pre-v31 it was interpolated raw, unlike plugin_path/args which
# correctly used !r). Dunder/private-mangled names are refused as well: an
# entry point is never ``__init__``/``__builtins__``, and allowing them only
# hands callers a way to poke at module internals.
_FUNCTION_NAME_RE = re.compile(r"^(?!__)[A-Za-z_][A-Za-z0-9_]*$")

BACKEND_WINDOWS_JOB = "windows-job-object"
BACKEND_POSIX_RLIMIT = "posix-rlimit"
BACKEND_NONE = "none"


class SandboxUnavailableError(RuntimeError):
    """No real isolation backend exists on this platform.

    Raised instead of running the plugin. Callers must treat this as fatal
    for that plugin rather than falling back to direct execution.
    """


# ---------------------------------------------------------------------------
# Win32 Job Object plumbing
# ---------------------------------------------------------------------------

_JOB_API_READY = False

if sys.platform == "win32":  # pragma: no cover - exercised only on Windows
    import ctypes
    from ctypes import wintypes

    _JobObjectExtendedLimitInformation = 9
    _JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    _JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    _JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    _JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    try:
        _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _k32.CreateJobObjectW.restype = wintypes.HANDLE
        _k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        _k32.SetInformationJobObject.restype = wintypes.BOOL
        _k32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        _k32.AssignProcessToJobObject.restype = wintypes.BOOL
        _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        _k32.TerminateJobObject.restype = wintypes.BOOL
        _k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        _k32.OpenProcess.restype = wintypes.HANDLE
        _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        _k32.CloseHandle.restype = wintypes.BOOL
        _k32.CloseHandle.argtypes = [wintypes.HANDLE]
        _JOB_API_READY = True
    except (OSError, AttributeError) as _exc:  # pragma: no cover
        logger.error("Win32 job-object API unavailable: %s", _exc)
        _JOB_API_READY = False


def sandbox_backend() -> str:
    """Return the isolation backend name for this platform.

    One of ``windows-job-object``, ``posix-rlimit`` or ``none``. ``none``
    means plugins cannot be isolated and must not be executed.
    """
    if sys.platform == "win32":
        return BACKEND_WINDOWS_JOB if _JOB_API_READY else BACKEND_NONE
    if resource is not None and hasattr(resource, "RLIMIT_AS"):
        return BACKEND_POSIX_RLIMIT
    return BACKEND_NONE


def sandbox_available() -> bool:
    """True when a real isolation backend exists on this platform."""
    return sandbox_backend() != BACKEND_NONE


class _WindowsJob:
    """A Win32 job object holding a memory cap for one plugin run."""

    def __init__(self, memory_limit_mb: int) -> None:
        self.handle = _k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")

        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        max_bytes = int(memory_limit_mb) * 1024 * 1024
        info.ProcessMemoryLimit = max_bytes
        info.JobMemoryLimit = max_bytes
        info.BasicLimitInformation.ActiveProcessLimit = DEFAULT_MAX_PROCESSES
        info.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | _JOB_OBJECT_LIMIT_JOB_MEMORY
            | _JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | _JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
            | _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        ok = _k32.SetInformationJobObject(
            self.handle,
            _JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            err = ctypes.get_last_error()
            self.close()
            raise OSError(err, "SetInformationJobObject failed")

    def assign(self, pid: int) -> None:
        """Assign *pid* to this job. Raises OSError if it cannot be done."""
        hproc = _k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
        if not hproc:
            raise OSError(ctypes.get_last_error(), f"OpenProcess({pid}) failed")
        try:
            if not _k32.AssignProcessToJobObject(self.handle, hproc):
                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        finally:
            _k32.CloseHandle(hproc)

    def terminate(self) -> None:
        """Kill every process in the job."""
        if self.handle:
            _k32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None


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
    backend: str = ""


@dataclass
class SandboxedPlugin:
    """Represents a running or recently-run sandboxed plugin."""
    name: str
    pid: int = 0
    started_at: float = 0.0
    permissions: list[str] = field(default_factory=list)
    process: subprocess.Popen | None = None
    job: Any = None  # _WindowsJob on Windows, else None

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


def _kill_tree(sp: SandboxedPlugin) -> None:
    """Kill the plugin process and everything it spawned."""
    proc = sp.process
    if sp.job is not None:
        sp.job.terminate()
        return
    if proc is None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, AttributeError):
        try:
            proc.kill()
        except OSError:
            pass


def _build_runner_code(
    plugin_path: Path,
    function_name: str,
    args: list[str] | None,
    memory_limit_mb: int,
    apply_rlimit: bool,
) -> str:
    """Generate the child-process runner source.

    Every interpolated value goes through ``!r`` so plugin-controlled or
    caller-controlled strings can never break out into executable code.
    """
    rlimit_block = ""
    if apply_rlimit:
        rlimit_block = f"""
import resource
max_bytes = {int(memory_limit_mb)} * 1024 * 1024
resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
"""
    return f"""
import sys, json, importlib.util
sys.path.insert(0, {str(plugin_path.parent)!r})
{rlimit_block}
spec = importlib.util.spec_from_file_location(
    'sandboxed_plugin', {str(plugin_path)!r}
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

func = getattr(module, {function_name!r}, None)
if func is None:
    print(json.dumps({{"error": "Function " + {function_name!r} + " not found"}}))
    sys.exit(1)

try:
    result = func({args!r})
    print(json.dumps({{"output": str(result) if result else "done"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
    sys.exit(1)
"""


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
        function_name: Entry point function to call. Must be a Python
            identifier; anything else is rejected.
        args: Arguments to pass to the function.
        timeout: Maximum execution time in seconds.
        memory_limit_mb: Memory limit for the subprocess.
        permissions: List of granted permissions.

    Returns:
        SandboxResult with output, errors, and status.

    Raises:
        SandboxUnavailableError: No isolation backend on this platform. The
            plugin is *not* executed.
    """
    backend = sandbox_backend()
    if backend == BACKEND_NONE:
        msg = (
            "Plugin sandbox unavailable on this platform "
            f"({sys.platform}): refusing to execute {plugin_path!r} "
            "because it could not be isolated."
        )
        logger.error(msg)
        raise SandboxUnavailableError(msg)

    if not isinstance(function_name, str) or not _FUNCTION_NAME_RE.match(function_name):
        return SandboxResult(
            success=False,
            error=f"Invalid entry point name: {function_name!r}",
            backend=backend,
        )

    plugin_path = Path(plugin_path)
    if not plugin_path.exists():
        return SandboxResult(
            success=False, error=f"Plugin not found: {plugin_path}", backend=backend
        )

    # Validate permissions
    if permissions:
        permissions = validate_permissions(permissions)

    runner_code = _build_runner_code(
        plugin_path,
        function_name,
        args,
        memory_limit_mb,
        apply_rlimit=(backend == BACKEND_POSIX_RLIMIT),
    )

    job: _WindowsJob | None = None
    proc: subprocess.Popen | None = None
    key = plugin_path.stem
    start = time.time()

    try:
        popen_kwargs: dict[str, Any] = {}
        if backend == BACKEND_WINDOWS_JOB:
            job = _WindowsJob(memory_limit_mb)
            # Own process group so the child can be signalled independently.
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["preexec_fn"] = os.setsid

        proc = subprocess.Popen(
            [sys.executable, "-c", runner_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **popen_kwargs,
        )

        if job is not None:
            # Enforce the cap before the plugin body runs. If the child
            # cannot be confined, kill it — never let it run unconfined.
            try:
                job.assign(proc.pid)
            except OSError as exc:
                with contextlib.suppress(Exception):
                    proc.kill()
                    proc.communicate(timeout=5)
                logger.error("Refusing to run %s unsandboxed: %s", plugin_path, exc)
                return SandboxResult(
                    success=False,
                    error=f"Could not confine plugin to job object: {exc}",
                    backend=backend,
                    duration_seconds=round(time.time() - start, 3),
                )

        sp = SandboxedPlugin(
            name=key,
            pid=proc.pid,
            started_at=start,
            permissions=permissions or [],
            process=proc,
            job=job,
        )
        _active_plugins[key] = sp

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
                    backend=backend,
                )
            except json.JSONDecodeError:
                return SandboxResult(
                    success=True,
                    output=stdout.strip()[:500],
                    duration_seconds=round(duration, 3),
                    pid=proc.pid,
                    backend=backend,
                )
        else:
            return SandboxResult(
                success=False,
                error=stderr.strip()[:500] or stdout.strip()[:500],
                exit_code=proc.returncode,
                duration_seconds=round(duration, 3),
                pid=proc.pid,
                backend=backend,
            )

    except subprocess.TimeoutExpired:
        sp = _active_plugins.get(key)
        if sp is not None:
            _kill_tree(sp)
        elif proc is not None:
            with contextlib.suppress(Exception):
                proc.kill()
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.communicate(timeout=5)
        return SandboxResult(
            success=False,
            error=f"Plugin timed out after {timeout}s",
            timed_out=True,
            duration_seconds=round(time.time() - start, 3),
            pid=proc.pid if proc is not None else 0,
            backend=backend,
        )
    except Exception as e:
        return SandboxResult(
            success=False,
            error=str(e),
            duration_seconds=round(time.time() - start, 3),
            backend=backend,
        )

    finally:
        _active_plugins.pop(key, None)
        if job is not None:
            # Closing the handle triggers KILL_ON_JOB_CLOSE, reaping any
            # grandchildren the plugin left behind.
            job.close()


def list_active() -> list[dict[str, Any]]:
    """List all currently active sandboxed plugins.

    Iterates a snapshot: pre-v31 this popped from ``_active_plugins`` while
    iterating it, raising ``RuntimeError: dictionary changed size during
    iteration`` exactly when a plugin had just finished.
    """
    result = []
    for name, sp in list(_active_plugins.items()):
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
        _kill_tree(sp)
        _active_plugins.pop(name, None)
        return {"success": True, "message": f"Plugin '{name}' killed"}
    except Exception as e:
        return {"success": False, "message": str(e)}
