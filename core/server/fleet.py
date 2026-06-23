"""Sentinel Desktop v10.0 — Fleet Manager.

Track and manage multiple Sentinel machines (nodes) in a fleet.
Each node reports its status, health metrics, and active jobs.

The fleet data is stored locally as JSON — no external database needed.
For a single-machine setup, the fleet has one node (the local machine).
"""

from __future__ import annotations

import json
import logging
import os
import socket
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_FLEET_PATH = Path("config/fleet.json")


class FleetNode:
    """A single machine in the fleet."""

    def __init__(
        self,
        node_id: str,
        hostname: str = "",
        ip_address: str = "",
        role: str = "agent",
        tags: list[str] | None = None,
    ) -> None:
        self.node_id = node_id
        self.hostname = hostname or socket.gethostname()
        self.ip_address = ip_address
        self.role = role
        self.tags = tags or []
        self.status: str = "unknown"
        self.last_seen: str | None = None
        self.jobs_completed: int = 0
        self.jobs_failed: int = 0
        self.health: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "role": self.role,
            "tags": self.tags,
            "status": self.status,
            "last_seen": self.last_seen,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed,
            "health": self.health,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FleetNode:
        node = cls(
            node_id=data["node_id"],
            hostname=data.get("hostname", ""),
            ip_address=data.get("ip_address", ""),
            role=data.get("role", "agent"),
            tags=data.get("tags", []),
        )
        node.status = data.get("status", "unknown")
        node.last_seen = data.get("last_seen")
        node.jobs_completed = data.get("jobs_completed", 0)
        node.jobs_failed = data.get("jobs_failed", 0)
        node.health = data.get("health", {})
        return node


class FleetManager:
    """Manage a fleet of Sentinel nodes.

    Usage::

        fleet = FleetManager()
        fleet.register_node("sentinel-core", hostname="CORE", role="orchestrator")
        fleet.update_heartbeat("sentinel-core")
        nodes = fleet.list_nodes()
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_FLEET_PATH
        self._nodes: dict[str, FleetNode] = {}
        self._load()

    def register_node(
        self,
        node_id: str,
        hostname: str = "",
        ip_address: str = "",
        role: str = "agent",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Register a new node in the fleet."""
        if node_id in self._nodes:
            return {"success": False, "error": f"Node {node_id} already registered"}

        node = FleetNode(
            node_id=node_id,
            hostname=hostname,
            ip_address=ip_address,
            role=role,
            tags=tags,
        )
        node.status = "online"
        node.last_seen = datetime.utcnow().isoformat()
        self._nodes[node_id] = node
        self._save()

        logger.info("Registered fleet node: %s (%s)", node_id, hostname)
        return {"success": True, "node_id": node_id}

    def unregister_node(self, node_id: str) -> dict[str, Any]:
        """Remove a node from the fleet."""
        if node_id not in self._nodes:
            return {"success": False, "error": f"Node {node_id} not found"}
        del self._nodes[node_id]
        self._save()
        return {"success": True}

    def update_heartbeat(
        self,
        node_id: str,
        health: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a node's heartbeat."""
        node = self._nodes.get(node_id)
        if node is None:
            return {"success": False, "error": f"Node {node_id} not found"}
        node.last_seen = datetime.utcnow().isoformat()
        node.status = "online"
        if health:
            node.health = health
        self._save()
        return {"success": True}

    def record_job(self, node_id: str, success: bool) -> dict[str, Any]:
        """Record a completed job on a node."""
        node = self._nodes.get(node_id)
        if node is None:
            return {"success": False, "error": f"Node {node_id} not found"}
        if success:
            node.jobs_completed += 1
        else:
            node.jobs_failed += 1
        self._save()
        return {"success": True}

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get a node's info."""
        node = self._nodes.get(node_id)
        return node.to_dict() if node else None

    def list_nodes(self) -> list[dict[str, Any]]:
        """List all fleet nodes."""
        return [node.to_dict() for node in self._nodes.values()]

    def count(self) -> int:
        """Count registered nodes."""
        return len(self._nodes)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # A truncated/garbled file is unrecoverable as a whole; quarantine it
            # so the next mutation can't silently overwrite the operator's fleet
            # data with an empty file.
            logger.warning("Failed to load fleet data: %s", exc)
            self._quarantine_corrupt_file()
            return
        # The JSON parsed — load each node individually so one malformed record
        # (e.g. a node missing "node_id") is skipped rather than crashing the
        # whole manager and discarding every other valid node in the file.
        for node_data in data.get("nodes", []):
            try:
                node = FleetNode.from_dict(node_data)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping malformed fleet node record: %s", exc)
                continue
            self._nodes[node.node_id] = node

    def _quarantine_corrupt_file(self) -> None:
        backup = self._path.parent / (self._path.name + ".corrupt")
        try:
            self._path.replace(backup)
            logger.warning("Corrupt fleet file moved to %s", backup)
        except OSError as move_exc:
            logger.warning("Could not quarantine corrupt fleet file: %s", move_exc)

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {"nodes": [n.to_dict() for n in self._nodes.values()]}
            # Atomic write: stage in a uniquely-named temp, fsync, then
            # os.replace into place. A crash mid-write leaves the live fleet
            # file intact — the old code wrote it directly with no fsync and a
            # truncated write silently dropped every registered node. The unique
            # temp name means GUI + API saves sharing this dir can't clobber
            # each other on the final rename.
            tmp = self._path.parent / f".fleet-{uuid.uuid4().hex}.tmp"
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps(data, indent=2))
                fh.flush()
                os.fsync(fh.fileno())
            tmp.replace(self._path)
        except OSError as exc:
            logger.warning("Failed to save fleet data: %s", exc)
