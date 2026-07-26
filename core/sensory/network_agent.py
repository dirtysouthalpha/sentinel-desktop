"""Network sensory agent — watches the Tailscale mesh and network topology.

Discovers which peers are online, what services they expose, and
tracks network health metrics.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Info about a Tailscale peer."""

    hostname: str
    ip: str
    os: str = ""
    online: bool = False
    last_seen: float = 0.0
    tags: list[str] = field(default_factory=list)
    services: dict[str, int] = field(default_factory=dict)


@dataclass
class NetworkEvent:
    """Emitted when network topology changes."""

    timestamp: float
    event_type: str  # "peer_online", "peer_offline", "service_up", "service_down"
    hostname: str
    details: str = ""


@dataclass
class NetworkConfig:
    check_interval_seconds: float = 30.0
    ping_timeout: int = 5
    enabled: bool = True


class NetworkAgent:
    """Monitors the Tailscale mesh for peer health and service availability."""

    def __init__(self, config: NetworkConfig | None = None) -> None:
        self._config = config or NetworkConfig()
        self._running = False
        self._thread: threading.Thread | None = None
        self._peers: dict[str, PeerInfo] = {}
        self._callbacks: list[Callable[[NetworkEvent], None]] = []

    def on_change(self, callback: Callable[[NetworkEvent], None]) -> None:
        self._callbacks.append(callback)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="sensory-network")
        self._thread.start()
        logger.info("Network agent started (interval=%ss)", self._config.check_interval_seconds)

    def stop(self) -> None:
        self._running = False

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._check_peers()
            except Exception as exc:
                logger.debug("Network check failed: %s", exc)
            time.sleep(self._config.check_interval_seconds)

    def _check_peers(self) -> None:
        peers = self._discover_peers()
        current_hostnames = {p.hostname for p in peers}

        # Detect newly online peers
        for peer in peers:
            prev = self._peers.get(peer.hostname)
            if prev and not prev.online and peer.online:
                self._emit(NetworkEvent(
                    timestamp=time.time(),
                    event_type="peer_online",
                    hostname=peer.hostname,
                    details=f"{peer.hostname} ({peer.ip}) is online",
                ))
            # Detect services
            if peer.services:
                for svc, port in peer.services.items():
                    prev_svc = (prev.services if prev else {}).get(svc)
                    if prev_svc is None:
                        self._emit(NetworkEvent(
                            timestamp=time.time(),
                            event_type="service_up",
                            hostname=peer.hostname,
                            details=f"Service {svc} on {peer.hostname}:{port}",
                        ))

        # Detect offline peers
        for hostname, prev in self._peers.items():
            if prev.online and hostname not in current_hostnames:
                self._emit(NetworkEvent(
                    timestamp=time.time(),
                    event_type="peer_offline",
                    hostname=hostname,
                    details=f"{hostname} went offline",
                ))

        self._peers = {p.hostname: p for p in peers}

    def _discover_peers(self) -> list[PeerInfo]:
        """Use Tailscale status to discover peers."""
        peers: list[PeerInfo] = []
        tailscale = shutil.which("tailscale")
        if not tailscale:
            return peers

        try:
            result = subprocess.run(
                [tailscale, "status", "--json"],
                capture_output=True, text=True, timeout=self._config.ping_timeout,
            )
            if result.returncode != 0:
                return peers

            data = json.loads(result.stdout)
            for hostname, peer_data in data.get("Peer", {}).items():
                ip = peer_data.get("TailscaleIPs", [""])[0] if peer_data.get("TailscaleIPs") else ""
                online = peer_data.get("Online", False)
                os_name = peer_data.get("OS", "")
                tags = peer_data.get("Tags", []) or []
                # Extract services from services field if present
                services: dict[str, int] = {}
                for svc in peer_data.get("Services", []):
                    if isinstance(svc, dict):
                        name = svc.get("Name", "")
                        port = svc.get("Port", 0)
                        if name and port:
                            services[name] = port

                peers.append(PeerInfo(
                    hostname=hostname,
                    ip=ip,
                    os=os_name,
                    online=online,
                    last_seen=time.time() if online else 0.0,
                    tags=tags,
                    services=services,
                ))
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
            pass
        return peers

    def _emit(self, event: NetworkEvent) -> None:
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as exc:
                logger.error("Network callback failed: %s", exc)

    @property
    def is_running(self) -> bool:
        return self._running

    def get_peers(self) -> dict[str, PeerInfo]:
        return dict(self._peers)

    def get_online_peers(self) -> list[PeerInfo]:
        return [p for p in self._peers.values() if p.online]


__all__ = ["PeerInfo", "NetworkEvent", "NetworkConfig", "NetworkAgent"]
