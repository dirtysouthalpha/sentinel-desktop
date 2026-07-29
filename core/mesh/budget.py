"""Task budget enforcement for the fleet mesh."""
from __future__ import annotations

import logging
from typing import Any

from core.mesh.task_graph import Task

logger = logging.getLogger(__name__)


class BudgetEnforcer:
    def check_budget(self, task: Task, api_calls: int = 0, runtime_seconds: float = 0, cost_usd: float = 0) -> bool:
        if task.budget.is_exceeded(api_calls, runtime_seconds, cost_usd):
            logger.warning("Task %s exceeded budget", task.id)
            return False
        return True

    def get_budget_status(self, task: Task, api_calls: int = 0, runtime_seconds: float = 0, cost_usd: float = 0) -> dict[str, Any]:
        return {
            "api_calls_remaining": max(0, task.budget.max_api_calls - api_calls),
            "api_calls_pct": (api_calls / task.budget.max_api_calls * 100) if task.budget.max_api_calls > 0 else 0,
            "runtime_remaining": max(0, task.budget.max_runtime_seconds - runtime_seconds),
            "runtime_pct": (runtime_seconds / task.budget.max_runtime_seconds * 100) if task.budget.max_runtime_seconds > 0 else 0,
            "cost_remaining": max(0, task.budget.max_cost_usd - cost_usd),
            "cost_pct": (cost_usd / task.budget.max_cost_usd * 100) if task.budget.max_cost_usd > 0 else 0,
        }
