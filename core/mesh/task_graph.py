"""Task graph with dependency tracking and checkpointing."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class TaskBudget:
    max_api_calls: int = 100
    max_runtime_seconds: int = 3600
    max_cost_usd: float = 5.0

    def is_exceeded(self, api_calls: int = 0, runtime_seconds: float = 0, cost_usd: float = 0) -> bool:
        return (api_calls > self.max_api_calls or runtime_seconds > self.max_runtime_seconds or cost_usd > self.max_cost_usd)


@dataclass
class Task:
    id: str
    type: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_node: str = ""
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 3
    retry_count: int = 0
    budget: TaskBudget = field(default_factory=TaskBudget)
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    checkpoint_data: dict[str, Any] = field(default_factory=dict)

    def is_ready(self, graph: TaskGraph) -> bool:
        if self.status != TaskStatus.PENDING:
            return False
        for dep_id in self.depends_on:
            dep = graph.get_task(dep_id)
            if dep is None or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


class TaskGraph:
    def __init__(self, checkpoint_dir: str | os.PathLike[str] | None = None) -> None:
        self.tasks: dict[str, Task] = {}
        self.checkpoint_dir = str(checkpoint_dir) if checkpoint_dir else ""
        if self.checkpoint_dir:
            Path(self.checkpoint_dir).mkdir(parents=True, exist_ok=True)

    def add_task(self, task: Task) -> None:
        # Check for self-dependency
        if task.id in task.depends_on:
            raise ValueError(f"Task {task.id} cannot depend on itself")
        # Temporarily add and check for cycles
        existing = task.id in self.tasks
        self.tasks[task.id] = task
        if self._has_cycle():
            if not existing:
                del self.tasks[task.id]
            raise ValueError(f"Adding task {task.id} would create a dependency cycle")

    def _has_cycle(self) -> bool:
        """Detect cycles in the task dependency graph using DFS."""
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            node_task = self.tasks.get(node_id)
            if node_task:
                for dep_id in node_task.depends_on:
                    if dep_id not in self.tasks:
                        continue  # Missing dependency — handled by is_ready
                    if dep_id not in visited:
                        if dfs(dep_id):
                            return True
                    elif dep_id in rec_stack:
                        return True
            rec_stack.discard(node_id)
            return False

        for task_id in self.tasks:
            if task_id not in visited:
                if dfs(task_id):
                    return True
        return False

    def get_task(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def get_ready_tasks(self) -> list[Task]:
        return [t for t in self.tasks.values() if t.is_ready(self)]

    def get_pending_tasks(self) -> list[Task]:
        return [t for t in self.tasks.values() if t.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED)]

    def is_complete(self) -> bool:
        return all(t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ROLLED_BACK) for t in self.tasks.values())

    def checkpoint(self, task_id: str) -> None:
        if not self.checkpoint_dir:
            return
        task = self.tasks.get(task_id)
        if task is None:
            return
        data = {
            "id": task.id, "type": task.type, "goal": task.goal,
            "status": task.status.value, "assigned_node": task.assigned_node,
            "retry_count": task.retry_count, "result": task.result,
            "error": task.error, "checkpoint_data": task.checkpoint_data,
        }
        path = os.path.join(self.checkpoint_dir, f"checkpoint_{task_id}.json")
        atomic_write_text(path, json.dumps(data, indent=2))

    def load_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        if not self.checkpoint_dir:
            return None
        path = os.path.join(self.checkpoint_dir, f"checkpoint_{task_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)
