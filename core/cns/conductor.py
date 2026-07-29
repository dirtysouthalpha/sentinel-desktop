"""CNS Conductor — orchestrates plan→execute→evaluate cycles.

The conductor is the core reasoning engine of CNS 1.0. It:
  1. Decomposes a goal into a task graph (via TaskPlanner)
  2. Iterates through ready subtasks, dispatching them to a handler
  3. Evaluates results against expectations (via Evaluator)
  4. Retries failed subtasks up to max_retries
  5. Returns a final plan result with scores and summary

The conductor is transport-agnostic. It accepts a `handler` callable
that executes a subtask and returns its result. This lets it run
standalone (in tests), over the mesh (via TaskExecutor), or against
live fleet nodes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from core.cns.evaluator import EvalResult, EvalStatus, Evaluator
from core.cns.planner import Subtask, TaskPlanner, TaskType

logger = logging.getLogger(__name__)

# Subtask handler: takes a Subtask, returns a dict with at least {"output": str}.
SubtaskHandler = Callable[[Subtask], Awaitable[dict[str, Any]] | dict[str, Any]]


@dataclass
class PlanResult:
    """The result of executing a CNS plan."""
    goal: str
    subtotal: int = 0
    completed: int = 0
    failed: int = 0
    retried: int = 0
    eval_results: list[EvalResult] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed

    @property
    def overall_score(self) -> float:
        if not self.eval_results:
            return 0.0
        return sum(r.score for r in self.eval_results) / len(self.eval_results)

    @property
    def all_passed(self) -> bool:
        return all(r.status == EvalStatus.PASS for r in self.eval_results)


class Conductor:
    """Orchestrates plan→execute→evaluate cycles for CNS 1.0."""

    def __init__(
        self,
        planner: TaskPlanner | None = None,
        evaluator: Evaluator | None = None,
        max_retries: int = 2,
    ) -> None:
        self.planner = planner or TaskPlanner()
        self.evaluator = evaluator or Evaluator()
        self.max_retries = max_retries

    async def run(
        self,
        goal: str,
        handler: SubtaskHandler | None = None,
        expected: dict[str, str] | None = None,
    ) -> PlanResult:
        """Run a full plan for the given goal.

        Args:
            goal: The natural-language goal to accomplish.
            handler: Callable that executes a subtask. If None, a
                     default handler that returns the description
                     as the output is used (useful for testing).
            expected: Optional dict mapping subtask ID to expected
                      output. Used for evaluation.

        Returns:
            PlanResult with execution status and evaluation scores.
        """
        result = PlanResult(goal=goal, status="running")

        subtasks = self.planner.decompose(goal)
        if not subtasks:
            result.status = "completed"
            return result

        result.subtotal = len(subtasks)
        if expected is None:
            expected = {}

        if handler is None:
            handler = self._default_handler

        completed: set[str] = set()
        failed_per_task: dict[str, int] = {}

        while len(completed) < result.subtotal:
            # Find ready subtasks (pending, all deps completed)
            ready = [
                st for st in subtasks
                if st.status == "pending" and st.is_ready(completed)
            ]
            if not ready:
                # Deadlock: remaining tasks have unresolvable deps.
                remaining = [st for st in subtasks if st.status != "completed"]
                if remaining:
                    logger.warning("Plan deadlock: %d tasks stuck", len(remaining))
                    for st in remaining:
                        st.status = "failed"
                        result.failed += 1
                break

            for subtask in ready:
                subtask.status = "running"
                raw = handler(subtask)
                if hasattr(raw, "__await__"):
                    raw = await raw
                output = raw.get("output", "") if isinstance(raw, dict) else str(raw)

                # Evaluate against expectation
                exp = expected.get(subtask.id, subtask.description)
                eval_result = self.evaluator.evaluate(
                    subtask_id=subtask.id,
                    expected=exp,
                    actual=output,
                )

                if eval_result.status == EvalStatus.PASS:
                    subtask.status = "completed"
                    completed.add(subtask.id)
                    result.completed += 1
                    logger.debug("Subtask %s passed (%.2f)", subtask.id, eval_result.score)
                else:
                    # Retry logic
                    retries = failed_per_task.get(subtask.id, 0)
                    if retries < self.max_retries:
                        failed_per_task[subtask.id] = retries + 1
                        result.retried += 1
                        subtask.status = "pending"  # will retry next loop
                        logger.warning(
                            "Subtask %s failed (retry %d/%d): %s",
                            subtask.id, retries + 1, self.max_retries,
                            eval_result.feedback,
                        )
                    else:
                        subtask.status = "failed"
                        result.failed += 1
                        completed.add(subtask.id)  # unblock dependents
                        logger.error("Subtask %s exhausted retries", subtask.id)

                result.eval_results.append(eval_result)

        # Determine final status
        if result.failed == 0 and result.completed == result.subtotal:
            result.status = "completed"
        elif result.completed > 0:
            result.status = "completed"  # partial completion
        else:
            result.status = "failed"

        logger.info(
            "Plan '%s' done: %d/%d completed, %d failed, %d retried (score: %.2f)",
            goal[:40], result.completed, result.subtotal,
            result.failed, result.retried, result.overall_score,
        )
        return result

    @staticmethod
    def _default_handler(subtask: Subtask) -> dict[str, str]:
        """Default handler: returns the description as output.

        This is a no-op handler for testing the planning/evaluation
        pipeline without real execution.
        """
        return {"output": subtask.description}
