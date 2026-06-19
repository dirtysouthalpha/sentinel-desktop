"""Sentinel Desktop v12.0 — Conductor Coordinator.

Top-level coordinator that ties together the task planner,
parallel executor, and result synthesizer. This is the main
entry point for multi-agent orchestration.

Usage::

    conductor = Conductor()
    result = await conductor.run("Login to firewall, check ARP, and export config")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from core.conductor.parallel import ParallelExecutor
from core.conductor.planner import Subtask, TaskPlanner
from core.conductor.synthesizer import ResultSynthesizer

logger = logging.getLogger(__name__)


class Conductor:
    """Coordinates multi-agent task execution.

    Decomposes goals → plans subtasks → executes in parallel → synthesizes results.

    Usage::

        conductor = Conductor()
        result = await conductor.run("Check all firewalls and generate report")
        print(result["status"])  # "success", "partial", "failed"
    """

    def __init__(
        self,
        executor_fn: Callable[[Subtask], Any] | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.planner = TaskPlanner()
        self.executor = ParallelExecutor(executor_fn=executor_fn, max_concurrency=max_concurrency)
        self.synthesizer = ResultSynthesizer()

    async def run(
        self,
        goal: str,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Execute a goal through multi-agent orchestration.

        Args:
            goal: The user's goal in plain English.
            timeout: Maximum total execution time.

        Returns:
            Synthesized result dict with status, summary, and per-task details.
        """
        logger.info("Conductor: processing goal — %s", goal[:80])

        # Step 1: Decompose into subtasks
        subtasks = self.planner.decompose(goal)
        if not subtasks:
            return {
                "goal": goal,
                "status": "no_tasks",
                "success": False,
                "summary": "Could not decompose goal into tasks",
                "tasks_total": 0,
                "tasks_succeeded": 0,
                "tasks_failed": 0,
                "results": [],
            }

        # Step 2: Execute subtasks in parallel (respecting dependencies)
        results = await self.executor.execute_all(subtasks, timeout=timeout)

        # Step 3: Synthesize into final result
        final = self.synthesizer.synthesize(goal, results)

        logger.info(
            "Conductor: %s — %d/%d tasks succeeded",
            final["status"],
            final["tasks_succeeded"],
            final["tasks_total"],
        )

        return final

    def plan(self, goal: str) -> list[dict[str, Any]]:
        """Preview the decomposition plan without executing.

        Args:
            goal: The goal to plan for.

        Returns:
            List of subtask dicts.
        """
        subtasks = self.planner.decompose(goal)
        return [s.to_dict() for s in subtasks]
