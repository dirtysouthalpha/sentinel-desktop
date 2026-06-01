"""Sentinel Desktop — PowerShell Script Execution Module.

Provides PowerShellRunner for executing PowerShell scripts, commands,
and inline snippets on Windows with JSON output parsing, timeout
handling, admin elevation support, and built-in diagnostic helpers.

Gracefully degrades on non-Windows platforms.
"""

import contextlib
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.utils import is_windows as _is_windows

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument escaping
# ---------------------------------------------------------------------------


def _ps_escape_single_quoted(s: str) -> str:
    """Quote *s* as a PowerShell single-quoted literal.

    PowerShell single-quoted strings are verbatim — the only escape is the
    single quote itself, which is doubled (``'foo''bar'`` → ``foo'bar``).
    Control characters (NUL, CR, LF) are rejected with ``ValueError``
    because they could let a caller break out of a quoted context in
    nested command construction.

    Use this whenever a caller-supplied value (service name, host, etc.)
    is interpolated into a command string built by this module.
    """
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")
    for ch in ("\x00", "\r", "\n"):
        if ch in s:
            raise ValueError(f"control character {ch!r} not allowed in PS argument")
    return "'" + s.replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class PSResult:
    """Encapsulates the result of a PowerShell execution."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    objects: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        status = "OK" if self.success else "FAIL"
        return (
            f"PSResult({status}, code={self.exit_code}, "
            f"stdout={len(self.stdout)}c, objects={len(self.objects)})"
        )


# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------


def _non_windows_result() -> PSResult:
    """Return a failure result indicating PowerShell is Windows-only."""
    return PSResult(
        success=False,
        exit_code=-1,
        stdout="",
        stderr="PowerShell execution is only supported on Windows.",
        objects=[],
    )


# ---------------------------------------------------------------------------
# PowerShellRunner
# ---------------------------------------------------------------------------


class PowerShellRunner:
    """Execute PowerShell scripts, commands, and inline snippets.

    Args:
        timeout: Maximum seconds to wait for a PS process.
        run_as_admin: If True, launch with UAC elevation.
        working_dir: Working directory for spawned processes.
        env_vars: Extra environment variables for the child process.

    """

    POWERSHELL_EXE = "powershell.exe"
    PS_CORE_EXE = "pwsh.exe"

    def __init__(
        self,
        timeout: int = 300,
        run_as_admin: bool = False,
        working_dir: str | None = None,
        env_vars: dict[str, str] | None = None,
        allow_raw: bool = True,
    ) -> None:
        """Configure a PowerShell runner.

        Args:
            timeout: Maximum seconds to wait for the child process.
            run_as_admin: Launch with UAC elevation. The elevated path
                builds a wrapping ``Start-Process -Verb RunAs`` command;
                keep this behind an approval gate when callers can be
                influenced by an LLM.
            working_dir: cwd for the spawned process.
            env_vars: extra environment variables.
            allow_raw: When ``False``, :meth:`run_command` and
                :meth:`run_inline` refuse to execute (they expose a
                surface that takes arbitrary PowerShell). Set to
                ``False`` whenever the input may have come from an LLM
                tool call or unauthenticated API user; built-in helpers
                like :meth:`get_service_status` continue to work.

        """
        self.timeout = timeout
        self.run_as_admin = run_as_admin
        self.working_dir = working_dir or str(Path.cwd())
        self.env_vars = env_vars or {}
        self.allow_raw = allow_raw
        self._ps_exe = self._resolve_ps_exe()

    # -- internal -----------------------------------------------------------

    def _resolve_ps_exe(self) -> str:
        """Pick the best PowerShell executable (pwsh > powershell) on Windows."""
        if not _is_windows():
            return self.POWERSHELL_EXE
        for candidate in (self.PS_CORE_EXE, self.POWERSHELL_EXE):
            try:
                r = subprocess.run(
                    ["where", candidate],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return candidate
            except (OSError, subprocess.SubprocessError) as exc:
                logger.debug("PowerShell candidate %s failed validation: %s", candidate, exc)
                continue
        return self.POWERSHELL_EXE

    def _build_env(self) -> dict[str, str]:
        """Merge ``os.environ`` with any custom env vars configured on the runner."""
        env = os.environ.copy()
        env.update({k: str(v) for k, v in self.env_vars.items()})
        return env

    def _base_args(self) -> list[str]:
        """Return the common PowerShell invocation flags (no profile, JSON output)."""
        return [self._ps_exe, "-NoProfile", "-NonInteractive", "-OutputFormat", "JSON"]

    @staticmethod
    def _parse_json_output(stdout: str) -> list[dict[str, Any]]:
        """Parse stdout from a PowerShell JSON-format command into a list of dicts.

        A single JSON object is wrapped in a list; bare scalars become ``{value: …}``.
        Returns an empty list on empty or unparseable output.
        """
        stdout = stdout.strip()
        if not stdout:
            return []
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                return [data]
            if isinstance(data, list):
                return data
            return [{"value": data}]
        except json.JSONDecodeError:
            logger.debug("Non-JSON PowerShell stdout, returning empty objects list")
            return []

    def _run(self, command: str) -> PSResult:
        """Core execution: wraps *command* and invokes PowerShell."""
        if not _is_windows():
            return _non_windows_result()

        args = self._base_args()
        if self.run_as_admin:
            tmp_out = str(Path(self.working_dir) / f"_ps_elev_{int(time.time())}.tmp")
            wrapped = (
                f'Start-Process -Verb RunAs -FilePath "{self._ps_exe}" '
                f'-ArgumentList "-NoProfile -NonInteractive -Command '
                f'\\"{command} | Out-File -FilePath \\"{tmp_out}\\" '
                f'-Encoding utf8\\"" -Wait'
            )
            args.extend(["-Command", wrapped])
        else:
            args.extend(["-Command", f"{command} | ConvertTo-Json -Depth 10 -Compress"])

        logger.debug("PS args: %s", args)
        return self._invoke_subprocess(args, command)

    def _invoke_subprocess(self, args: list[str], command: str) -> PSResult:
        """Run PowerShell subprocess and convert output to :class:`PSResult`.

        Handles TimeoutExpired, FileNotFoundError, and other process errors.
        """
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.working_dir,
                env=self._build_env(),
            )
            exit_code = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            if self.run_as_admin:
                stdout = self._read_elevated_output(command, stdout)

            objects = self._parse_json_output(stdout)
            return PSResult(success=(exit_code == 0), exit_code=exit_code,
                            stdout=stdout, stderr=stderr, objects=objects)

        except subprocess.TimeoutExpired:
            logger.warning("PowerShell timed out after %ds", self.timeout)
            return PSResult(success=False, exit_code=-2, stdout="",
                            stderr=f"Process timed out after {self.timeout} seconds.", objects=[])
        except FileNotFoundError:
            logger.error("PowerShell not found: %s", self._ps_exe)
            return PSResult(success=False, exit_code=-3, stdout="",
                            stderr=f"PowerShell executable not found: {self._ps_exe}", objects=[])
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            logger.exception("Unexpected error running PowerShell")
            return PSResult(success=False, exit_code=-4, stdout="", stderr=str(exc), objects=[])

    def _read_elevated_output(self, command: str, stdout: str) -> str:
        """Read elevated-process output from temp file and clean it up.

        Searches *command* tokens for a ``.tmp`` path written by the elevated
        wrapper; reads the file if found, then deletes it unconditionally.
        """
        for part in command.split():
            if part.endswith(".tmp"):
                tmp_out = part.strip('"').strip("'")
                break
        else:
            tmp_out = ""
        if tmp_out and Path(tmp_out).is_file():
            try:
                with Path(tmp_out).open(encoding="utf-8", errors="replace") as fh:
                    stdout = fh.read()
            except OSError as exc:
                logger.warning("Failed to read elevated output from %s: %s", tmp_out, exc)
            with contextlib.suppress(OSError):
                Path(tmp_out).unlink()
        return stdout

    # -- public API ---------------------------------------------------------

    def run_script(self, script_path: str, args: dict[str, Any] | None = None) -> PSResult:
        """Execute a .ps1 script file with optional -Key Value args."""
        if not Path(script_path).is_file():
            return PSResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Script not found: {script_path}",
                objects=[],
            )
        params = ""
        if args:
            parts: list[str] = []
            for k, v in args.items():
                try:
                    escaped_val = _ps_escape_single_quoted(str(v))
                except (TypeError, ValueError):
                    escaped_val = "''"
                parts.append(f"-{k} {escaped_val}")
            params = " " + " ".join(parts)
        return self._run(f'& "{script_path}"{params}')

    def run_command(self, command: str) -> PSResult:
        """Execute an arbitrary PowerShell command string.

        This is a power-user surface: the caller is fully responsible for
        sanitising *command*. When the runner was created with
        ``allow_raw=False`` this method refuses to execute.
        """
        if not self.allow_raw:
            return PSResult(
                success=False,
                exit_code=-5,
                stdout="",
                stderr="run_command refused: allow_raw=False on this runner.",
                objects=[],
            )
        return self._run(command)

    def run_inline(self, script_body: str) -> PSResult:
        """Execute a multi-line PowerShell script block.

        Same caveat as :meth:`run_command` — the caller owns the safety
        of *script_body*. Refuses to execute when ``allow_raw=False``.
        """
        if not self.allow_raw:
            return PSResult(
                success=False,
                exit_code=-5,
                stdout="",
                stderr="run_inline refused: allow_raw=False on this runner.",
                objects=[],
            )
        escaped = script_body.replace("'", "''")
        return self._run(f"& {{ {escaped} }}")

    # -- built-in helpers ---------------------------------------------------

    def get_event_errors(self, hours: int = 1) -> list[dict[str, Any]]:
        """Scan System + Application event logs for errors in the last *hours*."""
        cmd = (
            "Get-WinEvent -FilterHashtable "
            "@{LogName='System','Application';Level=2;"
            f"StartTime=(Get-Date).AddHours(-{hours})}} "
            "| Select-Object TimeCreated,Id,LevelDisplayName,"
            "Message,ProviderName,LogName"
        )
        result = self._run(cmd)
        return result.objects if result.success else []

    def get_installed_software(self) -> list[dict[str, Any]]:
        """List installed programs from the registry (32- and 64-bit)."""
        cmd = (
            "$paths=@("
            "'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
            "'HKLM:\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'"
            ");"
            "Get-ItemProperty $paths -ErrorAction SilentlyContinue "
            "| Where-Object {$_.DisplayName} "
            "| Select-Object DisplayName,DisplayVersion,Publisher,InstallDate"
        )
        result = self._run(cmd)
        return result.objects if result.success else []

    def get_service_status(self, name: str) -> dict[str, Any]:
        """Check the status of a Windows service."""
        try:
            ps_name = _ps_escape_single_quoted(name)
        except (TypeError, ValueError) as exc:
            return {
                "Name": name,
                "Status": "Unknown",
                "StartType": "Unknown",
                "DisplayName": "",
                "error": f"invalid service name: {exc}",
            }
        cmd = (
            f"Get-Service -Name {ps_name} -ErrorAction Stop "
            "| Select-Object Name,Status,StartType,DisplayName"
        )
        result = self._run(cmd)
        if result.success and result.objects:
            return result.objects[0]
        return {
            "Name": name,
            "Status": "Unknown",
            "StartType": "Unknown",
            "DisplayName": "",
            "error": result.stderr,
        }

    def restart_service(self, name: str) -> dict[str, Any]:
        """Restart a Windows service safely (stop then start)."""
        try:
            ps_name = _ps_escape_single_quoted(name)
        except (TypeError, ValueError) as exc:
            return {
                "Name": name,
                "Status": "Error",
                "Action": "Restart",
                "Success": False,
                "error": f"invalid service name: {exc}",
            }
        cmd = (
            f"try{{"
            f" Restart-Service -Name {ps_name} -Force -ErrorAction Stop;"
            f" $s=Get-Service -Name {ps_name};"
            f" @{{Name=$s.Name;Status=$s.Status.ToString();"
            f"   Action='Restarted';Success=$true}}"
            f"}}catch{{"
            f" @{{Name={ps_name};Status='Error';Action='Restart';"
            f"   Success=$false;Error=$_.Exception.Message}}"
            f"}}"
        )
        result = self._run(cmd)
        if result.success and result.objects:
            return result.objects[0]
        return {
            "Name": name,
            "Status": "Error",
            "Action": "Restart",
            "Success": False,
            "error": result.stderr,
        }

    def get_disk_usage(self) -> list[dict[str, Any]]:
        """Disk space info for all local drives."""
        cmd = (
            "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' "
            "| Select-Object DeviceID,VolumeName,"
            "@{N='TotalGB';E={[math]::Round($_.Size/1GB,2)}},"
            "@{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,2)}},"
            "@{N='UsedGB';E={[math]::Round(($_.Size-$_.FreeSpace)/1GB,2)}},"
            "@{N='PercentFree';E={[math]::Round(($_.FreeSpace/$_.Size)*100,1)}}"
        )
        result = self._run(cmd)
        return result.objects if result.success else []

    def get_network_config(self) -> list[dict[str, Any]]:
        """IP / DNS / adapter info for enabled adapters."""
        cmd = (
            "Get-CimInstance Win32_NetworkAdapterConfiguration "
            "| Where-Object {$_.IPEnabled} "
            "| Select-Object Description,IPAddress,DefaultIPGateway,"
            "DNSServerSearchOrder,DHCPEnabled,MACAddress"
        )
        result = self._run(cmd)
        return result.objects if result.success else []

    def test_connection(self, host: str) -> dict[str, Any]:
        """Ping and traceroute to *host*."""
        try:
            ps_host = _ps_escape_single_quoted(host)
        except (TypeError, ValueError) as exc:
            return {
                "Host": host,
                "PingSucceeded": False,
                "PingMs": 0,
                "Hops": [],
                "error": f"invalid host: {exc}",
            }
        cmd = (
            f"$p=Test-Connection -ComputerName {ps_host} -Count 4 "
            f"-ErrorAction SilentlyContinue;"
            f"$avg=if($p){{($p|Measure-Object -Property ResponseTime "
            f"-Average).Average}}else{{0}};"
            f"@{{Host={ps_host};PingSucceeded=($null -ne $p);"
            f"PingMs=[math]::Round($avg,2);"
            f"Hops=$p|Select-Object Address,ResponseTime,TTL}}"
        )
        result = self._run(cmd)
        if result.success and result.objects:
            return result.objects[0]
        return {
            "Host": host,
            "PingSucceeded": False,
            "PingMs": 0,
            "Hops": [],
            "error": result.stderr,
        }


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_runner: PowerShellRunner | None = None


def get_default_runner() -> PowerShellRunner:
    """Return a lazily-created default runner (useful for quick calls)."""
    global _default_runner
    if _default_runner is None:
        _default_runner = PowerShellRunner()
    return _default_runner
