"""Fleet observability — system metrics collection and reporting."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.mesh.event_bus import EventBus, FleetEvent

logger = logging.getLogger(__name__)


@dataclass
class NodeMetrics:
    """Snapshot of a node's system state."""

    node_id: str
    timestamp: float = 0.0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    tasks_active: int = 0
    tasks_completed: int = 0
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used_mb": self.memory_used_mb,
            "memory_total_mb": self.memory_total_mb,
            "disk_percent": self.disk_percent,
            "disk_used_gb": self.disk_used_gb,
            "disk_total_gb": self.disk_total_gb,
            "tasks_active": self.tasks_active,
            "tasks_completed": self.tasks_completed,
            "uptime_seconds": self.uptime_seconds,
        }


class MetricsCollector:
    """Collects system metrics for a mesh node."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self._start_time = time.time()

    def collect(self, tasks_active: int = 0, tasks_completed: int = 0) -> NodeMetrics:
        """Collect current system metrics."""
        try:
            import psutil

            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            cpu = psutil.cpu_percent(interval=0.1)
            return NodeMetrics(
                node_id=self.node_id,
                timestamp=time.time(),
                cpu_percent=cpu,
                memory_percent=mem.percent,
                memory_used_mb=mem.used / (1024 * 1024),
                memory_total_mb=mem.total / (1024 * 1024),
                disk_percent=disk.percent,
                disk_used_gb=disk.used / (1024 * 1024 * 1024),
                disk_total_gb=disk.total / (1024 * 1024 * 1024),
                tasks_active=tasks_active,
                tasks_completed=tasks_completed,
                uptime_seconds=time.time() - self._start_time,
            )
        except ImportError:
            return NodeMetrics(
                node_id=self.node_id,
                timestamp=time.time(),
                uptime_seconds=time.time() - self._start_time,
            )


class MetricsReporter:
    """Periodically publishes NODE_METRICS events."""

    def __init__(
        self,
        node_id: str,
        bus: EventBus,
        interval_seconds: float = 30.0,
        task_counter: Callable[[], tuple[int, int]] | None = None,
    ) -> None:
        self.node_id = node_id
        self.bus = bus
        self.interval = interval_seconds
        self._task_counter = task_counter
        self._collector = MetricsCollector(node_id)
        self._running = False

    async def start(self) -> None:
        """Start periodic metrics reporting."""
        self._running = True
        while self._running:
            try:
                active, completed = self._task_counter() if self._task_counter else (0, 0)
                metrics = self._collector.collect(active, completed)
                await self.bus.publish(FleetEvent.NODE_METRICS, metrics.to_dict())
            except Exception as e:
                logger.debug("Metrics publish error: %s", e)
            await asyncio.sleep(self.interval)

    def stop(self) -> None:
        """Stop periodic metrics reporting."""
        self._running = False


class FleetMetricsAggregator:
    """Aggregates metrics from all nodes (runs on any node, typically leader)."""

    def __init__(self) -> None:
        self._node_metrics: dict[str, NodeMetrics] = {}

    def update(self, metrics_dict: dict[str, Any]) -> None:
        """Update metrics for a node."""
        node_id = metrics_dict.get("node_id", "unknown")
        self._node_metrics[node_id] = NodeMetrics(**{
            k: v for k, v in metrics_dict.items() if k in NodeMetrics.__dataclass_fields__
        })

    def get_fleet_summary(self) -> dict[str, Any]:
        """Return aggregated fleet-wide metrics summary."""
        nodes = list(self._node_metrics.values())
        if not nodes:
            return {"total_nodes": 0, "healthy_nodes": 0, "avg_cpu": 0, "avg_memory": 0}
        return {
            "total_nodes": len(nodes),
            "healthy_nodes": sum(1 for n in nodes if n.memory_percent < 90 and n.cpu_percent < 90),
            "avg_cpu": sum(n.cpu_percent for n in nodes) / len(nodes),
            "avg_memory": sum(n.memory_percent for n in nodes) / len(nodes),
            "total_tasks_active": sum(n.tasks_active for n in nodes),
            "total_tasks_completed": sum(n.tasks_completed for n in nodes),
            "nodes": {n.node_id: n.to_dict() for n in nodes},
        }

    def get_stuck_nodes(self, cpu_threshold: float = 95.0, memory_threshold: float = 95.0) -> list[str]:
        """Find nodes that may need intervention."""
        stuck = []
        for node_id, metrics in self._node_metrics.items():
            if metrics.cpu_percent > cpu_threshold or metrics.memory_percent > memory_threshold:
                stuck.append(node_id)
        return stuck
