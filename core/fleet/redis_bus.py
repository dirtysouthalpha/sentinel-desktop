"""
Sentinel Desktop v29.0.0 - Distributed Fleet Bus.

Redis-backed message bus for coordinating agents across multiple machines.
Falls back to in-memory pub/sub when Redis is unavailable.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class FleetNode:
    """A node in the distributed fleet."""
    id: str
    hostname: str = ""
    ip: str = ""
    status: str = "online"  # online, offline, busy
    agents_running: int = 0
    last_heartbeat: float = 0.0
    capabilities: list[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        """True if heartbeat received within last 60 seconds."""
        return time.time() - self.last_heartbeat < 60.0 if self.last_heartbeat else False


class InMemoryBus:
    """Simple in-memory pub/sub fallback when Redis is not available."""

    def __init__(self) -> None:
        self._channels: dict[str, list[Callable]] = defaultdict(list)
        self._messages: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def publish(self, channel: str, message: dict[str, Any]) -> None:
        """Publish a message to a channel."""
        msg = {"channel": channel, "data": message, "timestamp": time.time()}
        with self._lock:
            self._messages.append(msg)
            for callback in self._channels.get(channel, []):
                try:
                    callback(message)
                except Exception as e:
                    logger.debug("Bus callback error: %s", e)

    def subscribe(self, channel: str, callback: Callable) -> None:
        """Subscribe to a channel."""
        with self._lock:
            self._channels[channel].append(callback)

    def get_messages(self, channel: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent messages, optionally filtered by channel."""
        with self._lock:
            msgs = list(self._messages)
        if channel:
            msgs = [m for m in msgs if m["channel"] == channel]
        return msgs[-limit:]


class FleetManager:
    """Manages a distributed fleet of Sentinel Desktop nodes."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or os.environ.get("SENTINEL_REDIS_URL", "")
        self._redis = None
        self._bus = InMemoryBus()
        self._nodes: dict[str, FleetNode] = {}
        self._local_node_id = f"node-{int(time.time())}"
        self._lock = threading.Lock()

        # Try Redis connection
        if self.redis_url:
            try:
                import redis
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("Connected to Redis at %s", self.redis_url)
            except Exception as e:
                logger.warning("Redis unavailable (%s), using in-memory bus", e)
                self._redis = None

        # Register local node
        self.register_node(self._local_node_id, hostname="localhost", ip="127.0.0.1")

    def register_node(self, node_id: str, hostname: str = "", ip: str = "", capabilities: list[str] | None = None) -> FleetNode:
        """Register or update a fleet node."""
        with self._lock:
            node = FleetNode(
                id=node_id,
                hostname=hostname,
                ip=ip,
                last_heartbeat=time.time(),
                capabilities=capabilities or [],
            )
            self._nodes[node_id] = node
            self._bus.publish("fleet", {"event": "node_registered", "node_id": node_id})
            return node

    def heartbeat(self, node_id: str) -> None:
        """Update heartbeat for a node."""
        with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].last_heartbeat = time.time()

    def list_nodes(self) -> list[dict[str, Any]]:
        """List all fleet nodes with health status."""
        with self._lock:
            return [
                {
                    "id": n.id,
                    "hostname": n.hostname,
                    "ip": n.ip,
                    "status": "online" if n.is_healthy else "offline",
                    "agents_running": n.agents_running,
                    "last_heartbeat": round(time.time() - n.last_heartbeat, 1) if n.last_heartbeat else 0,
                    "capabilities": n.capabilities,
                }
                for n in self._nodes.values()
            ]

    def deploy_agent(self, node_id: str, goal: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Deploy an agent task to a specific node."""
        node = self._nodes.get(node_id)
        if not node:
            return {"success": False, "message": f"Node '{node_id}' not found"}
        if not node.is_healthy:
            return {"success": False, "message": f"Node '{node_id}' is offline"}

        task = {
            "node_id": node_id,
            "goal": goal,
            "config": config or {},
            "deployed_at": time.time(),
        }
        self._bus.publish("deploy", task)
        node.agents_running += 1

        if self._redis:
            try:
                self._redis.publish(f"sentinel:deploy:{node_id}", json.dumps(task))
            except Exception:
                pass

        return {"success": True, "message": f"Agent deployed to node '{node_id}'", "task": task}

    def get_fleet_health(self) -> dict[str, Any]:
        """Get aggregate fleet health."""
        nodes = self.list_nodes()
        total = len(nodes)
        healthy = sum(1 for n in nodes if n["status"] == "online")
        total_agents = sum(n["agents_running"] for n in nodes)
        return {
            "total_nodes": total,
            "healthy_nodes": healthy,
            "unhealthy_nodes": total - healthy,
            "total_agents_running": total_agents,
            "bus_type": "redis" if self._redis else "in-memory",
        }

    def publish_event(self, channel: str, event: dict[str, Any]) -> None:
        """Publish an event on the fleet bus."""
        self._bus.publish(channel, event)
        if self._redis:
            try:
                self._redis.publish(f"sentinel:{channel}", json.dumps(event))
            except Exception:
                pass

    def get_events(self, channel: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent events from the bus."""
        return self._bus.get_messages(channel, limit)


import os

_fleet: FleetManager | None = None


def get_fleet() -> FleetManager:
    """Get or create the singleton fleet manager."""
    global _fleet
    if _fleet is None:
        _fleet = FleetManager()
    return _fleet
