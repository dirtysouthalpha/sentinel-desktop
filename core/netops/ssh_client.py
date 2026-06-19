"""Sentinel Desktop v9.0 — SSH client for network device access.

Provides a synchronous SSH client using paramiko for connecting to
routers, switches, firewalls, and other network appliances.

Supports:
- Password and key-based authentication
- Executing commands and returning output
- Shell session (interactive) mode
- Connection timeout and retry
- Graceful degradation when paramiko is not installed
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_HAS_PARAMIKO = False
paramiko = None  # Define as None for test patching

try:
    import paramiko as _paramiko

    # Override the None placeholder with the real import
    paramiko = _paramiko
    _HAS_PARAMIKO = True
except ImportError:
    pass


class SSHError(Exception):
    """Raised when SSH operations fail."""


@dataclass
class SSHResult:
    """Result of an SSH command execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int | None = None
    command: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "command": self.command,
            "duration_ms": self.duration_ms,
        }


class SSHClient:
    """SSH client for connecting to network devices.

    Usage::

        client = SSHClient(hostname="192.168.1.1", username="admin", password="secret")
        result = client.run_command("show version")
        print(result.stdout)
        client.close()
    """

    def __init__(
        self,
        hostname: str,
        username: str = "",
        password: str = "",
        port: int = 22,
        key_filename: str | None = None,
        timeout: float = 30.0,
        look_for_keys: bool = True,
        allow_agent: bool = False,
    ) -> None:
        if not _HAS_PARAMIKO:
            raise SSHError("paramiko not installed. Install with: pip install paramiko")

        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.key_filename = key_filename
        self.timeout = timeout
        self.look_for_keys = look_for_keys
        self.allow_agent = allow_agent

        self._client: paramiko.SSHClient | None = None
        self._connected: bool = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def connect(self) -> None:
        """Establish SSH connection to the device."""
        if self.is_connected:
            return

        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs: dict[str, Any] = {
                "hostname": self.hostname,
                "port": self.port,
                "username": self.username,
                "timeout": self.timeout,
                "look_for_keys": self.look_for_keys,
                "allow_agent": self.allow_agent,
            }
            if self.password:
                connect_kwargs["password"] = self.password
            if self.key_filename:
                connect_kwargs["key_filename"] = self.key_filename

            self._client.connect(**connect_kwargs)
            self._connected = True
            logger.info("SSH connected to %s:%d", self.hostname, self.port)

        except Exception as exc:
            self._connected = False
            raise SSHError(f"Failed to connect to {self.hostname}:{self.port}: {exc}") from exc

    def close(self) -> None:
        """Close the SSH connection."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                logger.debug("SSH close raised exception", exc_info=True)
            self._client = None
            self._connected = False
            logger.info("SSH disconnected from %s", self.hostname)

    def run_command(
        self,
        command: str,
        timeout: float | None = None,
    ) -> SSHResult:
        """Execute a command on the remote device.

        Args:
            command: Command string to execute.
            timeout: Optional per-command timeout (seconds).

        Returns:
            SSHResult with stdout, stderr, exit_code.
        """
        if not self.is_connected:
            self.connect()

        start = time.monotonic()
        try:
            assert self._client is not None
            stdin, stdout, stderr = self._client.exec_command(
                command,
                timeout=timeout or self.timeout,
            )
            stdout_str = stdout.read().decode("utf-8", errors="replace")
            stderr_str = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            elapsed = (time.monotonic() - start) * 1000

            logger.info(
                "SSH command on %s: %s (exit=%d, %.0fms)",
                self.hostname,
                command[:60],
                exit_code,
                elapsed,
            )

            return SSHResult(
                success=exit_code == 0,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                command=command,
                duration_ms=elapsed,
            )

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning("SSH command failed on %s: %s", self.hostname, exc)
            return SSHResult(
                success=False,
                stdout="",
                stderr=str(exc),
                exit_code=None,
                command=command,
                duration_ms=elapsed,
            )

    def run_commands(
        self,
        commands: list[str],
        timeout: float | None = None,
    ) -> list[SSHResult]:
        """Execute multiple commands sequentially.

        Args:
            commands: List of command strings.
            timeout: Optional per-command timeout.

        Returns:
            List of SSHResult, one per command.
        """
        return [self.run_command(cmd, timeout=timeout) for cmd in commands]

    def __enter__(self) -> SSHClient:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
