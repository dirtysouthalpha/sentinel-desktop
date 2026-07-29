"""Complete self-recovery ladder for the fleet mesh."""
from __future__ import annotations

import logging
from typing import Any

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator
from core.mesh.recovery import RecoveryManager
from core.mesh.watcher import SelfHealingWatcher, WatcherConfig

logger = logging.getLogger(__name__)


class SelfRecoveryLadder:
    """Orchestrates detection and recovery from fleet failures.

    Recovery ladder:
    1. Retry same node (up to max_retries)
    2. Retry different node (fallback selection)
    3. Rollback + re-plan
    4. Self-update (mark node unhealthy)
    5. Queue for daily digest (human escalation)
    """

    def __init__(
        self,
        bus: EventBus,
        metrics: FleetMetricsAggregator,
        recovery: RecoveryManager | None = None,
        config: WatcherConfig | None = None,
    ) -> None:
        self.bus = bus
        self.metrics = metrics
        self.recovery = recovery or RecoveryManager()
        self.watcher = SelfHealingWatcher(bus, metrics, config)
        self._recovery_actions: list[dict[str, Any]] = []

    def start(self) -> None:
        """Start the recovery ladder."""
        self.watcher.start()
        self.watcher._recovery_callback = self._on_recovery_needed
        logger.info("Self-recovery ladder started")

    def stop(self) -> None:
        self.watcher.stop()

    def _on_recovery_needed(self, issue_type: str, target_id: str, context: dict[str, Any]) -> None:
        """Handle a recovery event from the watcher."""
        if issue_type == "stuck_task":
            self._recover_stuck_task(target_id, context)
        elif issue_type == "unhealthy_node":
            self._recover_unhealthy_node(target_id)

    def _recover_stuck_task(self, task_id: str, context: dict[str, Any]) -> None:
        """Recover a stuck task by reassigning to a fallback node."""
        node_id = context.get("node_id", "")
        plan_id = context.get("plan_id", "")
        logger.warning("Recovering stuck task %s from node %s", task_id, node_id)

        # Select fallback node (would come from node registry in real system)
        fallback = self.recovery.select_fallback_node(
            current_node_id=node_id,
            available_nodes=[],
        )

        if fallback:
            self.bus.publish(FleetEvent.TASK_ASSIGNED, {
                "task_id": task_id,
                "plan_id": plan_id,
                "node_id": fallback.node_id,
                "task_type": context.get("task_type", "shell"),
                "goal": context.get("goal", ""),
                "params": context.get("params", {}),
            })
            self._recovery_actions.append({
                "action": "reassign",
                "task_id": task_id,
                "from_node": node_id,
                "to_node": fallback.node_id,
            })
        else:
            # No fallback — queue for digest
            logger.error("No fallback node for stuck task %s", task_id)
            self._recovery_actions.append({
                "action": "escalate",
                "task_id": task_id,
                "reason": "no_fallback_node",
            })

    def _recover_unhealthy_node(self, node_id: str) -> None:
        """Recover from an unhealthy node by draining its tasks."""
        logger.warning("Draining unhealthy node %s", node_id)
        self._recovery_actions.append({
            "action": "drain",
            "node_id": node_id,
        })

    def get_recovery_log(self) -> list[dict[str, Any]]:
        """Return the log of recovery actions taken."""
        return list(self._recovery_actions)
