"""SSH-based remote execution engine.

Run commands and transfer files on remote machines over SSH.
Used by the fleet manager and agent installer.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Host keys for fleet hosts are pinned here by default.
DEFAULT_KNOWN_HOSTS = Path(
    os.environ.get("SENTINEL_SSH_KNOWN_HOSTS", "")
    or (Path.home() / ".sentinel" / "known_hosts")
).expanduser()

_VALID_HOST_KEY_POLICIES = frozenset({"yes", "accept-new", "no"})


@dataclass
class SSHConfig:
    """Connection parameters for a remote host."""

    host: str
    user: str = "root"
    port: int = 22
    key_file: str = ""
    password: str = ""  # prefer key-based auth
    timeout: int = 30
    label: str = ""  # friendly name for fleet display
    tags: list[str] = field(default_factory=list)
    # Host-key policy. "yes" (default) requires the host to already be in
    # known_hosts, so a first-contact MITM cannot silently become trusted.
    # "accept-new" restores the pre-v31 trust-on-first-use behaviour and must
    # be opted into per host.
    strict_host_key_checking: str = "yes"
    # Where to persist host keys. Defaults to a Sentinel-managed file so fleet
    # hosts are pinned explicitly rather than inheriting the user's global
    # known_hosts (or nothing at all).
    known_hosts_file: str = ""


@dataclass
class SSHResult:
    """Result of a remote command."""

    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class SSHExecutor:
    """Run commands on a remote host via SSH."""

    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self._base_cmd = self._build_base_cmd()

    def _build_base_cmd(self) -> list[str]:
        cmd = ["ssh"]
        if self.config.key_file and os.path.isfile(self.config.key_file):
            cmd += ["-i", self.config.key_file]

        policy = (self.config.strict_host_key_checking or "yes").strip().lower()
        if policy not in _VALID_HOST_KEY_POLICIES:
            raise ValueError(
                f"invalid strict_host_key_checking {self.config.strict_host_key_checking!r}; "
                f"expected one of {sorted(_VALID_HOST_KEY_POLICIES)}"
            )
        if policy == "accept-new":
            logger.warning(
                "SSH to %s uses StrictHostKeyChecking=accept-new: the first key "
                "seen is trusted, so a first-contact MITM would go undetected.",
                self.config.host,
            )

        cmd += [
            "-o",
            f"StrictHostKeyChecking={policy}",
            "-o",
            f"UserKnownHostsFile={self._known_hosts_path()}",
            "-o",
            "ConnectTimeout=" + str(self.config.timeout),
            "-o",
            "BatchMode=yes",
            "-p",
            str(self.config.port),
        ]
        cmd.append(f"{self.config.user}@{self.config.host}")
        return cmd

    def _known_hosts_path(self) -> str:
        """Return the known_hosts file to pin host keys in, creating its dir."""
        if self.config.known_hosts_file:
            path = Path(self.config.known_hosts_file).expanduser()
        else:
            path = DEFAULT_KNOWN_HOSTS
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def run(self, command: str, timeout: int | None = None) -> SSHResult:
        """Run a command on the remote host and return the result."""
        import time

        full_cmd = self._base_cmd + [command]
        logger.debug("SSH [%s]: %s", self.config.host, command)
        start = time.time()
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self.config.timeout,
            )
            return SSHResult(
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=time.time() - start,
            )
        except subprocess.TimeoutExpired:
            return SSHResult(command=command, returncode=-1, stdout="", stderr="timeout")
        except FileNotFoundError:
            return SSHResult(command=command, returncode=-1, stdout="", stderr="ssh not found")
        except Exception as exc:
            return SSHResult(command=command, returncode=-1, stdout="", stderr=str(exc))

    def run_script(
        self, script_body: str, remote_path: str = "/tmp/sentinel_cmd.sh", timeout: int | None = None  # noqa: S108  # remote temp path
    ) -> SSHResult:
        """Upload a script and run it on the remote host."""
        # Copy the script via stdin to avoid tempfile on remote
        cmd = f"cat > {shlex.quote(remote_path)} && chmod +x {shlex.quote(remote_path)} && bash {shlex.quote(remote_path)}"
        full_cmd = self._base_cmd + [cmd]
        try:
            result = subprocess.run(
                full_cmd,
                input=script_body,
                capture_output=True,
                text=True,
                timeout=timeout or self.config.timeout,
            )
            # Clean up the script
            self.run(f"rm -f {shlex.quote(remote_path)}", timeout=5)
            return SSHResult(
                command=f"script at {remote_path}",
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except Exception as exc:
            return SSHResult(command="script upload", returncode=-1, stdout="", stderr=str(exc))

    def upload(self, local_path: str, remote_path: str) -> bool:
        """Copy a file to the remote host via SCP."""
        cmd = ["scp"]
        if self.config.key_file and os.path.isfile(self.config.key_file):
            cmd += ["-i", self.config.key_file]
        cmd += [
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=" + str(self.config.timeout),
            "-P",
            str(self.config.port),
            local_path,
            f"{self.config.user}@{self.config.host}:{remote_path}",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.config.timeout)
            return result.returncode == 0
        except Exception as exc:
            logger.error("scp upload failed: %s", exc)
            return False

    def download(self, remote_path: str, local_path: str) -> bool:
        """Copy a file from the remote host via SCP."""
        cmd = ["scp"]
        if self.config.key_file and os.path.isfile(self.config.key_file):
            cmd += ["-i", self.config.key_file]
        cmd += [
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=" + str(self.config.timeout),
            "-P",
            str(self.config.port),
            f"{self.config.user}@{self.config.host}:{remote_path}",
            local_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.config.timeout)
            return result.returncode == 0
        except Exception as exc:
            logger.error("scp download failed: %s", exc)
            return False

    def test_connection(self) -> bool:
        """Test if the SSH connection works."""
        result = self.run("echo sentinel-ping", timeout=10)
        return result.ok and "sentinel-ping" in result.stdout


__all__ = ["SSHConfig", "SSHResult", "SSHExecutor"]
