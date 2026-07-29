"""Plan->delegate->execute->remember orchestration loop."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from core.mesh.cache import StateCache
from core.mesh.event_bus import EventBus
from core.mesh.leader_election import LeaderElection
from core.mesh.task_graph import Task, TaskGraph, TaskStatus

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, event_bus: EventBus, cache: StateCache, leader_election: LeaderElection, node_id: str) -> None:
        self.bus = event_bus
        self.cache = cache
        self.election = leader_election
        self.node_id = node_id
        self._plans: dict[str, TaskGraph] = {}

    def create_plan(self, name: str, tasks: list[Task]) -> str:
        plan_id = str(uuid.uuid4())[:8]
        graph = TaskGraph()
        for task in tasks:
            graph.add_task(task)
        self._plans[plan_id] = graph
        self.cache.put("plan", plan_id, {"name": name, "status": "active", "task_count": len(tasks)})
        logger.info("Plan created: %s (%s) with %d tasks", plan_id, name, len(tasks))
        return plan_id

    def get_plan(self, plan_id: str) -> TaskGraph | None:
        return self._plans.get(plan_id)

    def assign_task(self, plan_id: str, task_id: str, node_id: str) -> bool:
        graph = self._plans.get(plan_id)
        if graph is None:
            return False
        task = graph.get_task(task_id)
        if task is None:
            return False
        task.status = TaskStatus.ASSIGNED
        task.assigned_node = node_id
        logger.info("Task %s assigned to node %s", task_id, node_id)
        return True

    def complete_task(self, plan_id: str, task_id: str, result: dict[str, Any]) -> None:
        graph = self._plans.get(plan_id)
        if graph is None:
            return
        task = graph.get_task(task_id)
        if task is None:
            return
        task.status = TaskStatus.COMPLETED
        task.result = result
        graph.checkpoint(task_id)
        logger.info("Task %s completed by node %s", task_id, task.assigned_node)

    def fail_task(self, plan_id: str, task_id: str, error: str) -> None:
        graph = self._plans.get(plan_id)
        if graph is None:
            return
        task = graph.get_task(task_id)
        if task is None:
            return
        task.error = error
        if task.can_retry():
            task.retry_count += 1
            task.status = TaskStatus.PENDING
            task.assigned_node = ""
            logger.warning("Task %s failed (retry %d/%d): %s", task_id, task.retry_count, task.max_retries, error)
        else:
            task.status = TaskStatus.FAILED
            logger.error("Task %s permanently failed: %s", task_id, error)
        graph.checkpoint(task_id)

    def get_plan_status(self, plan_id: str) -> dict[str, Any] | None:
        graph = self._plans.get(plan_id)
        if graph is None:
            return None
        tasks = list(graph.tasks.values())
        return {
            "plan_id": plan_id,
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in tasks if t.status == TaskStatus.FAILED),
            "pending": sum(1 for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED)),
            "is_complete": graph.is_complete(),
        }
