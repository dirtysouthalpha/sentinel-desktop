"""Fleet manager — discover, register, and dispatch tasks across remote machines."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .ssh import SSHConfig, SSHExecutor

logger = logging.getLogger(__name__)

_FLEET_FILE = Path.home() / ".sentinel" / "fleet.json"


@dataclass
class MachineInfo:
    """Info about a machine in the fleet."""

    host: str
    user: str = "root"
    port: int = 22
    key_file: str = ""
    label: str = ""
    tags: list[str] = field(default_factory=list)
    last_seen: float = 0.0
    online: bool = False
    capabilities: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MachineInfo:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_ssh_config(self) -> SSHConfig:
        return SSHConfig(
            host=self.host,
            user=self.user,
            port=self.port,
            key_file=self.key_file,
            label=self.label,
            tags=self.tags,
        )


class Fleet:
    """Manage a fleet of Sentinel Desktop machines."""

    def __init__(self, fleet_file: str | Path | None = None) -> None:
        self._fleet_file = Path(fleet_file) if fleet_file else _FLEET_FILE
        self._machines: dict[str, MachineInfo] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if self._fleet_file.exists():
            try:
                data = json.loads(self._fleet_file.read_text(encoding="utf-8"))
                for host, info in data.items():
                    self._machines[host] = MachineInfo.from_dict(info)
            except Exception as exc:
                logger.warning("Failed to load fleet: %s", exc)

    def _save(self) -> None:
        self._fleet_file.parent.mkdir(parents=True, exist_ok=True)
        data = {host: m.to_dict() for host, m in self._machines.items()}
        self._fleet_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def register(self, machine: MachineInfo) -> None:
        """Add or update a machine in the fleet."""
        with self._lock:
            self._machines[machine.host] = machine
            self._save()
        logger.info("Registered machine: %s (%s)", machine.host, machine.label or "unlabeled")

    def unregister(self, host: str) -> bool:
        """Remove a machine from the fleet."""
        with self._lock:
            if host in self._machines:
                del self._machines[host]
                self._save()
                return True
        return False

    def get(self, host: str) -> MachineInfo | None:
        return self._machines.get(host)

    def list(self, tag: str = "", online_only: bool = False) -> list[MachineInfo]:
        """List machines, optionally filtered by tag or online status."""
        result = []
        for m in self._machines.values():
            if tag and tag not in m.tags:
                continue
            if online_only and not m.online:
                continue
            result.append(m)
        return result

    def check_host(self, host: str) -> bool:
        """Check if a specific host is reachable."""
        machine = self._machines.get(host)
        if not machine:
            return False
        executor = SSHExecutor(machine.to_ssh_config())
        online = executor.test_connection()
        machine.online = online
        machine.last_seen = time.time() if online else machine.last_seen
        self._save()
        return online

    def check_all(self) -> dict[str, bool]:
        """Check all machines in parallel."""
        results = {}
        threads = []

        def _check(host: str) -> None:
            results[host] = self.check_host(host)

        for host in self._machines:
            t = threading.Thread(target=_check, args=(host,), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=15)
        return results

    def dispatch(self, host: str, command: str, timeout: int | None = None) -> Any:
        """Run a command on a specific host."""
        machine = self._machines.get(host)
        if not machine:
            return None
        executor = SSHExecutor(machine.to_ssh_config())
        return executor.run(command, timeout=timeout)

    def broadcast(self, command: str, tag: str = "", timeout: int | None = None) -> dict[str, Any]:
        """Run a command on all matching machines in parallel."""
        targets = self.list(tag=tag)
        results: dict[str, Any] = {}
        threads = []

        def _run(host: str, executor: SSHExecutor) -> None:
            results[host] = executor.run(command, timeout=timeout)

        for machine in targets:
            executor = SSHExecutor(machine.to_ssh_config())
            t = threading.Thread(target=_run, args=(machine.host, executor), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=(timeout or 30) + 5)
        return results


__all__ = ["MachineInfo", "Fleet"]
