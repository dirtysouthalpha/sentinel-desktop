"""Self-healing watcher for the fleet mesh."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator

logger = logging.getLogger(__name__)


@dataclass
class TaskTracker:
    """Tracks a running task for stuck detection."""
    task_id: str
    plan_id: str
    node_id: str
    assigned_at: float = field(default_factory=time.time)
    task_type: str = ""

    @property
    def runtime_seconds(self) -> float:
        return time.time() - self.assigned_at


@dataclass
class WatcherConfig:
    """Configuration for the self-healing watcher."""
    task_timeout_seconds: float = 300.0  # 5 minutes
    cpu_threshold: float = 95.0
    memory_threshold: float = 95.0
    check_interval_seconds: float = 30.0
    max_retries: int = 3


class SelfHealingWatcher:
    """Monitors fleet health and triggers recovery actions."""

    def __init__(
        self,
        bus: EventBus,
        metrics: FleetMetricsAggregator,
        config: WatcherConfig | None = None,
        recovery_callback: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.bus = bus
        self.metrics = metrics
        self.config = config or WatcherConfig()
        self._recovery_callback = recovery_callback
        self._running = False
        self._task_trackers: dict[str, TaskTracker] = {}
        self._retry_counts: dict[str, int] = {}

    def start(self) -> None:
        """Start watching for failures."""
        self._running = True
        self.bus.subscribe(FleetEvent.TASK_ASSIGNED, self._on_task_assigned)
        self.bus.subscribe(FleetEvent.TASK_COMPLETED, self._on_task_completed)
        self.bus.subscribe(FleetEvent.TASK_FAILED, self._on_task_failed)
        self.bus.subscribe(FleetEvent.NODE_METRICS, self._on_node_metrics)
        logger.info("Self-healing watcher started")

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        self.bus.unsubscribe(FleetEvent.TASK_ASSIGNED, self._on_task_assigned)
        self.bus.unsubscribe(FleetEvent.TASK_COMPLETED, self._on_task_completed)
        self.bus.unsubscribe(FleetEvent.TASK_FAILED, self._on_task_failed)
        self.bus.unsubscribe(FleetEvent.NODE_METRICS, self._on_node_metrics)

    async def _on_task_assigned(self, envelope: dict[str, Any]) -> None:
        """Track newly assigned tasks."""
        data = envelope.get("data", {})
        task_id = data.get("task_id", "")
        if task_id:
            self._task_trackers[task_id] = TaskTracker(
                task_id=task_id,
                plan_id=data.get("plan_id", ""),
                node_id=data.get("node_id", ""),
                task_type=data.get("task_type", ""),
            )

    async def _on_task_completed(self, envelope: dict[str, Any]) -> None:
        """Remove completed tasks from tracking."""
        data = envelope.get("data", {})
        task_id = data.get("task_id", "")
        self._task_trackers.pop(task_id, None)
        self._retry_counts.pop(task_id, None)

    async def _on_task_failed(self, envelope: dict[str, Any]) -> None:
        """Handle task failure — may trigger retry."""
        data = envelope.get("data", {})
        task_id = data.get("task_id", "")
        error = data.get("error", "")
        plan_id = data.get("plan_id", "")

        retries = self._retry_counts.get(task_id, 0)
        if retries < self.config.max_retries:
            self._retry_counts[task_id] = retries + 1
            logger.warning("Task %s failed (retry %d/%d): %s", task_id, retries + 1, self.config.max_retries, error)
            # Publish retry event
            await self.bus.publish(FleetEvent.TASK_RETRY, {
                "task_id": task_id,
                "plan_id": plan_id,
                "retry_count": retries + 1,
                "error": error,
            })
        else:
            logger.error("Task %s exhausted retries: %s", task_id, error)

    async def _on_node_metrics(self, envelope: dict[str, Any]) -> None:
        """Process node metrics for stuck detection."""
        data = envelope.get("data", {})
        self.metrics.update(data)

    async def check_health(self) -> list[dict[str, Any]]:
        """Run a health check cycle. Returns list of recovery actions taken."""
        if not self._running:
            return []

        actions = []

        # Check for stuck tasks
        for task_id, tracker in list(self._task_trackers.items()):
            if tracker.runtime_seconds > self.config.task_timeout_seconds:
                logger.warning("Stuck task detected: %s (%.0fs)", task_id, tracker.runtime_seconds)
                actions.append({
                    "action": "stuck_task",
                    "task_id": task_id,
                    "node_id": tracker.node_id,
                    "runtime": tracker.runtime_seconds,
                })
                if self._recovery_callback:
                    self._recovery_callback("stuck_task", task_id, {
                        "node_id": tracker.node_id,
                        "plan_id": tracker.plan_id,
                    })

        # Check for unhealthy nodes
        stuck_nodes = self.metrics.get_stuck_nodes(
            cpu_threshold=self.config.cpu_threshold,
            memory_threshold=self.config.memory_threshold,
        )
        for node_id in stuck_nodes:
            logger.warning("Unhealthy node detected: %s", node_id)
            actions.append({
                "action": "unhealthy_node",
                "node_id": node_id,
            })
            if self._recovery_callback:
                self._recovery_callback("unhealthy_node", node_id, {})

        return actions

    async def run(self) -> None:
        """Run the watcher loop (blocking)."""
        self._running = True
        while self._running:
            try:
                await self.check_health()
            except Exception:
                logger.exception("Health check error")
            await asyncio.sleep(self.config.check_interval_seconds)
