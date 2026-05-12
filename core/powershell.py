"""
Sentinel Desktop v3.0 — PowerShell Script Execution Module

Provides PowerShellRunner for executing PowerShell scripts, commands,
and inline snippets on Windows with JSON output parsing, timeout
handling, admin elevation support, and built-in diagnostic helpers.

Gracefully degrades on non-Windows platforms.
"""

import subprocess
import json
import os
import sys
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import platform

logger = logging.getLogger(__name__)


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
    objects: list = field(default_factory=list)

    def __str__(self) -> str:
        status = "OK" if self.success else "FAIL"
        return f"PSResult({status}, code={self.exit_code}, stdout={len(self.stdout)}c, objects={len(self.objects)})"


# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return platform.system() == "Windows"


def _non_windows_result() -> PSResult:
    return PSResult(
        success=False, exit_code=-1, stdout="",
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
        working_dir: Optional[str] = None,
        env_vars: Optional[dict] = None,
    ):
        self.timeout = timeout
        self.run_as_admin = run_as_admin
        self.working_dir = working_dir or os.getcwd()
        self.env_vars = env_vars or {}
        self._ps_exe = self._resolve_ps_exe()

    # -- internal -----------------------------------------------------------

    def _resolve_ps_exe(self) -> str:
        if not _is_windows():
            return self.POWERSHELL_EXE
        for candidate in (self.PS_CORE_EXE, self.POWERSHELL_EXE):
            try:
                r = subprocess.run(
                    ["where", candidate], capture_output=True,
                    text=True, timeout=5,
                )
                if r.returncode == 0:
                    return candidate
            except Exception:
                continue
        return self.POWERSHELL_EXE

    def _build_env(self) -> dict:
        env = os.environ.copy()
        env.update({k: str(v) for k, v in self.env_vars.items()})
        return env

    def _base_args(self) -> list:
        return [self._ps_exe, "-NoProfile", "-NonInteractive",
                "-OutputFormat", "JSON"]

    @staticmethod
    def _parse_json_output(stdout: str) -> list:
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
            return []

    def _run(self, command: str) -> PSResult:
        """Core execution: wraps *command* and invokes PowerShell."""
        if not _is_windows():
            return _non_windows_result()

        args = self._base_args()

        if self.run_as_admin:
            tmp_out = os.path.join(
                self.working_dir, f"_ps_elev_{int(time.time())}.tmp"
            )
            wrapped = (
                f'Start-Process -Verb RunAs -FilePath "{self._ps_exe}" '
                f'-ArgumentList "-NoProfile -NonInteractive -Command '
                f'\\"{command} | Out-File -FilePath \\"{tmp_out}\\" '
                f'-Encoding utf8\\"" -Wait'
            )
            args.extend(["-Command", wrapped])
        else:
            json_cmd = f"{command} | ConvertTo-Json -Depth 10 -Compress"
            args.extend(["-Command", json_cmd])

        logger.debug("PS args: %s", args)

        try:
            proc = subprocess.run(
                args, capture_output=True, text=True,
                timeout=self.timeout, cwd=self.working_dir,
                env=self._build_env(),
            )
            exit_code = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            # Elevated mode: read captured output from temp file
            if self.run_as_admin:
                for part in command.split():
                    if part.endswith(".tmp"):
                        tmp_out = part.strip('"').strip("'")
                        break
                else:
                    tmp_out = ""
                if tmp_out and os.path.isfile(tmp_out):
                    with open(tmp_out, "r", encoding="utf-8",
                              errors="replace") as fh:
                        stdout = fh.read()
                    try:
                        os.remove(tmp_out)
                    except OSError:
                        pass

            objects = self._parse_json_output(stdout)
            return PSResult(
                success=(exit_code == 0), exit_code=exit_code,
                stdout=stdout, stderr=stderr, objects=objects,
            )

        except subprocess.TimeoutExpired:
            logger.warning("PowerShell timed out after %ds", self.timeout)
            return PSResult(
                success=False, exit_code=-2, stdout="",
                stderr=f"Process timed out after {self.timeout} seconds.",
                objects=[],
            )
        except FileNotFoundError:
            logger.error("PowerShell not found: %s", self._ps_exe)
            return PSResult(
                success=False, exit_code=-3, stdout="",
                stderr=f"PowerShell executable not found: {self._ps_exe}",
                objects=[],
            )
        except Exception as exc:
            logger.exception("Unexpected error running PowerShell")
            return PSResult(
                success=False, exit_code=-4, stdout="",
                stderr=str(exc), objects=[],
            )

    # -- public API ---------------------------------------------------------

    def run_script(self, script_path: str, args: dict = None) -> PSResult:
        """Execute a .ps1 script file with optional -Key Value args."""
        if not os.path.isfile(script_path):
            return PSResult(
                success=False, exit_code=-1, stdout="",
                stderr=f"Script not found: {script_path}", objects=[],
            )
        params = ""
        if args:
            parts = [f'-{k} "{v}"' for k, v in args.items()]
            params = " " + " ".join(parts)
        return self._run(f'& "{script_path}"{params}')

    def run_command(self, command: str) -> PSResult:
        """Execute an arbitrary PowerShell command string."""
        return self._run(command)

    def run_inline(self, script_body: str) -> PSResult:
        """Execute a multi-line PowerShell script block."""
        escaped = script_body.replace('"', '\\"')
        return self._run(f'{{{escaped}}}')

    # -- built-in helpers ---------------------------------------------------

    def get_event_errors(self, hours: int = 1) -> list:
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

    def get_installed_software(self) -> list:
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

    def get_service_status(self, name: str) -> dict:
        """Check the status of a Windows service."""
        cmd = (
            f"Get-Service -Name '{name}' -ErrorAction Stop "
            "| Select-Object Name,Status,StartType,DisplayName"
        )
        result = self._run(cmd)
        if result.success and result.objects:
            return result.objects[0]
        return {"Name": name, "Status": "Unknown", "StartType": "Unknown",
                "DisplayName": "", "error": result.stderr}

    def restart_service(self, name: str) -> dict:
        """Restart a Windows service safely (stop then start)."""
        cmd = (
            f"try{{"
            f" Restart-Service -Name '{name}' -Force -ErrorAction Stop;"
            f" $s=Get-Service -Name '{name}';"
            f" @{{Name=$s.Name;Status=$s.Status.ToString();"
            f"   Action='Restarted';Success=$true}}"
            f"}}catch{{"
            f" @{{Name='{name}';Status='Error';Action='Restart';"
            f"   Success=$false;Error=$_.Exception.Message}}"
            f"}}"
        )
        result = self._run(cmd)
        if result.success and result.objects:
            return result.objects[0]
        return {"Name": name, "Status": "Error", "Action": "Restart",
                "Success": False, "error": result.stderr}

    def get_disk_usage(self) -> list:
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

    def get_network_config(self) -> list:
        """IP / DNS / adapter info for enabled adapters."""
        cmd = (
            "Get-CimInstance Win32_NetworkAdapterConfiguration "
            "| Where-Object {$_.IPEnabled} "
            "| Select-Object Description,IPAddress,DefaultIPGateway,"
            "DNSServerSearchOrder,DHCPEnabled,MACAddress"
        )
        result = self._run(cmd)
        return result.objects if result.success else []

    def test_connection(self, host: str) -> dict:
        """Ping and traceroute to *host*."""
        cmd = (
            f"$p=Test-Connection -ComputerName '{host}' -Count 4 "
            f"-ErrorAction SilentlyContinue;"
            f"$avg=if($p){{($p|Measure-Object -Property ResponseTime "
            f"-Average).Average}}else{{0}};"
            f"@{{Host='{host}';PingSucceeded=($null -ne $p);"
            f"PingMs=[math]::Round($avg,2);"
            f"Hops=$p|Select-Object Address,ResponseTime,TTL}}"
        )
        result = self._run(cmd)
        if result.success and result.objects:
            return result.objects[0]
        return {"Host": host, "PingSucceeded": False, "PingMs": 0,
                "Hops": [], "error": result.stderr}


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_runner: Optional[PowerShellRunner] = None


def get_default_runner() -> PowerShellRunner:
    """Return a lazily-created default runner (useful for quick calls)."""
    global _default_runner
    if _default_runner is None:
        _default_runner = PowerShellRunner()
    return _default_runner
