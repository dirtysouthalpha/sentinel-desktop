"""Tunnel and session management for remote control.

Establishes secure tunnels (via SSH port-forward or Tailscale) and
manages interactive sessions to remote Sentinel Desktop agents.
"""

from __future__ import annotations

import logging
import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from .ssh import SSHConfig, SSHExecutor

logger = logging.getLogger(__name__)


@dataclass
class Tunnel:
    """An active SSH tunnel."""

    local_port: int
    remote_host: str
    remote_port: int
    ssh_host: str
    ssh_user: str
    process: subprocess.Popen | None = None
    created_at: float = field(default_factory=time.time)

    @property
    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def close(self) -> None:
        if self.process and self.is_alive:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


@dataclass
class Session:
    """An active control session to a remote agent."""

    session_id: str
    target_host: str
    tunnel: Tunnel | None = None
    start_time: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    status: str = "active"  # active, paused, closed
    notes: list[str] = field(default_factory=list)


class TunnelManager:
    """Manage SSH port-forward tunnels to remote agents."""

    def __init__(self) -> None:
        self._tunnels: dict[str, Tunnel] = {}

    @staticmethod
    def find_free_port() -> int:
        """Find a free local port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def create_tunnel(
        self,
        local_port: int,
        remote_host: str,
        remote_port: int,
        ssh_config: SSHConfig,
        key_file: str = "",
    ) -> Tunnel | None:
        """Create an SSH local port-forward tunnel."""
        key_args = ["-i", key_file] if key_file else []
        cmd = [
            "ssh", "-N", "-L",
            f"{local_port}:{remote_host}:{remote_port}",
            "-p", str(ssh_config.port),
            f"{ssh_config.user}@{ssh_config.host}",
            *key_args,
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Wait briefly to confirm tunnel is established
            time.sleep(1)
            if proc.poll() is not None:
                logger.error("Tunnel to %s failed to start", ssh_config.host)
                return None
            tunnel = Tunnel(
                local_port=local_port,
                remote_host=remote_host,
                remote_port=remote_port,
                ssh_host=ssh_config.host,
                ssh_user=ssh_config.user,
                process=proc,
            )
            self._tunnels[f"{ssh_config.host}:{remote_port}"] = tunnel
            logger.info("Tunnel %s:%d -> %s:%d established", "localhost", local_port, remote_host, remote_port)
            return tunnel
        except Exception as exc:
            logger.error("Failed to create tunnel: %s", exc)
            return None

    def get_tunnel(self, ssh_host: str, remote_port: int = 8091) -> Tunnel | None:
        return self._tunnels.get(f"{ssh_host}:{remote_port}")

    def close_tunnel(self, ssh_host: str, remote_port: int = 8091) -> None:
        tunnel = self._tunnels.pop(f"{ssh_host}:{remote_port}", None)
        if tunnel:
            tunnel.close()

    def close_all(self) -> None:
        for tunnel in self._tunnels.values():
            tunnel.close()
        self._tunnels.clear()


class SessionManager:
    """Manage interactive remote control sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._tunnel_mgr = TunnelManager()

    def connect(self, target_host: str, tunnel_key_file: str = "") -> Session | None:
        """Establish a session to a remote agent via tunnel."""
        session_id = f"{target_host}-{int(time.time())}"
        local_port = TunnelManager.find_free_port()
        tunnel = self._tunnel_mgr.create_tunnel(
            local_port=local_port,
            remote_host="127.0.0.1",
            remote_port=8091,
            ssh_config=SSHConfig(host=target_host, key_file=tunnel_key_file),
            key_file=tunnel_key_file,
        )
        if not tunnel:
            return None
        session = Session(session_id=session_id, target_host=target_host, tunnel=tunnel)
        self._sessions[session_id] = session
        return session

    def disconnect(self, session_id: str) -> None:
        """Close a session and its tunnel."""
        session = self._sessions.pop(session_id, None)
        if session and session.tunnel:
            self._tunnel_mgr.close_tunnel(session.tunnel.ssh_host, 8091)

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def close_all(self) -> None:
        for sid in list(self._sessions):
            self.disconnect(sid)


__all__ = ["Tunnel", "Session", "TunnelManager", "SessionManager"]
