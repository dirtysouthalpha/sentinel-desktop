"""Sentinel Desktop v12.0 — Parallel Executor.

Runs independent subtasks concurrently using asyncio.
Respects dependency ordering — a subtask only starts when all
its dependencies are complete.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from core.conductor.planner import Subtask

logger = logging.getLogger(__name__)

# Maximum concurrent tasks
MAX_CONCURRENCY = 4


class ParallelExecutor:
    """Execute subtasks with dependency awareness and concurrency control.

    Usage::

        executor = ParallelExecutor(executor_fn=my_handler)
        results = await executor.execute_all(subtasks)
    """

    def __init__(
        self,
        executor_fn: Callable[[Subtask], Any] | None = None,
        max_concurrency: int = MAX_CONCURRENCY,
    ) -> None:
        self._executor_fn = executor_fn
        self._max_concurrency = max_concurrency

    async def execute_all(
        self,
        subtasks: list[Subtask],
        timeout: float = 120.0,
    ) -> list[dict[str, Any]]:
        """Execute all subtasks respecting dependencies.

        Args:
            subtasks: List of Subtask to execute.
            timeout: Maximum total execution time.

        Returns:
            List of result dicts, one per subtask.
        """
        start = time.monotonic()
        results: dict[str, dict[str, Any]] = {}
        completed_ids: set[str] = set()
        remaining = list(subtasks)

        while remaining and (time.monotonic() - start) < timeout:
            # Find tasks ready to execute (all deps satisfied)
            ready = [t for t in remaining if all(dep in completed_ids for dep in t.dependencies)]

            if not ready:
                # Deadlock or waiting — check if we're stuck
                if remaining:
                    logger.warning("No ready tasks, %d remaining", len(remaining))
                    break

            # Execute ready tasks (up to max concurrency)
            batch = ready[: self._max_concurrency]
            coroutines = [self._execute_one(task) for task in batch]

            batch_results = await asyncio.gather(*coroutines, return_exceptions=True)

            for task, result in zip(batch, batch_results, strict=False):
                if isinstance(result, Exception):
                    results[task.subtask_id] = {
                        "subtask_id": task.subtask_id,
                        "status": "error",
                        "error": str(result),
                    }
                else:
                    results[task.subtask_id] = result
                    # Only satisfy dependents if the task actually succeeded.
                    # _execute_one never raises — it returns an error dict on
                    # failure — so a failed task must NOT be treated as completed,
                    # or its dependents run against a failed prerequisite.
                    if result.get("status") == "success":
                        completed_ids.add(task.subtask_id)

                remaining.remove(task)

        # Classify remaining tasks: a task left over because its dependency
        # never completed (failed or missing) is "skipped"; only a task whose
        # dependencies are all satisfied but didn't get scheduled in time is a
        # genuine "timeout". Conflating them masks upstream-failure cascades.
        for task in remaining:
            failed_dep = next(
                (dep for dep in task.dependencies if dep not in completed_ids),
                None,
            )
            if failed_dep is not None:
                results[task.subtask_id] = {
                    "subtask_id": task.subtask_id,
                    "status": "skipped",
                    "error": f"Dependency '{failed_dep}' did not complete",
                }
            else:
                results[task.subtask_id] = {
                    "subtask_id": task.subtask_id,
                    "status": "timeout",
                    "error": "Execution timed out",
                }

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info("Parallel execution complete: %d tasks, %.0fms", len(subtasks), elapsed_ms)

        # Return in original order
        _missing = {"subtask_id": "", "status": "missing"}
        return [
            results.get(
                t.subtask_id,
                {**_missing, "subtask_id": t.subtask_id},
            )
            for t in subtasks
        ]

    async def _execute_one(self, subtask: Subtask) -> dict[str, Any]:
        """Execute a single subtask."""
        if self._executor_fn is None:
            return {
                "subtask_id": subtask.subtask_id,
                "status": "success",
                "description": subtask.description,
                "task_type": subtask.task_type,
            }

        try:
            result = self._executor_fn(subtask)
            # Handle both sync and async executor functions
            if asyncio.iscoroutine(result):
                result = await result
            return {
                "subtask_id": subtask.subtask_id,
                "status": "success",
                "result": result,
            }
        except Exception as exc:
            return {
                "subtask_id": subtask.subtask_id,
                "status": "error",
                "error": str(exc),
            }
