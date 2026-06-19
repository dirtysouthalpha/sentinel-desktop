"""Sentinel Desktop v21 — Scenario runner.

Replays a :class:`~eval.scenario.Scenario` step-by-step through an executor
callback, scores each step, and returns a :class:`~eval.scenario.ScenarioResult`.

The executor callback signature is::

    executor_fn(action: str, **params) -> dict[str, Any]

This matches :meth:`ActionExecutor.execute` when called as::

    runner = ScenarioRunner(executor_fn=lambda a, **p: executor.execute(a, **p))
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from eval.scenario import Scenario, ScenarioResult, ScenarioStep, ScenarioStepResult

logger = logging.getLogger(__name__)


class ScenarioRunner:
    """Replay a scenario through an executor callback and score results.

    Args:
        executor_fn: Callable that accepts ``(action, **params)`` and
            returns a result dict.  Exceptions are caught and recorded as
            failures.
        stop_on_failure: When True, abort the run after the first failing
            step.  Default False (collect all results).
    """

    def __init__(
        self,
        executor_fn: Callable[..., dict[str, Any]],
        *,
        stop_on_failure: bool = False,
    ) -> None:
        self._execute = executor_fn
        self._stop_on_failure = stop_on_failure

    def run(self, scenario: Scenario) -> ScenarioResult:
        """Run all steps of *scenario* and return an aggregate result.

        Args:
            scenario: The scenario to execute.

        Returns:
            A :class:`ScenarioResult` with per-step details and an overall
            pass/fail verdict.
        """
        logger.info("eval: starting scenario '%s' (%d steps)", scenario.name, len(scenario.steps))
        run_start = time.monotonic()
        step_results: list[ScenarioStepResult] = []
        passed = 0
        failed = 0

        for idx, step in enumerate(scenario.steps, start=1):
            sr = self._run_step(step, idx)
            step_results.append(sr)
            if sr.passed:
                passed += 1
            else:
                failed += 1
                if self._stop_on_failure:
                    logger.warning("eval: step %d failed — aborting '%s'", idx, scenario.name)
                    break

        total = len(step_results)
        score = round(passed / total, 4) if total else 0.0
        duration_ms = round((time.monotonic() - run_start) * 1000, 2)
        all_passed = failed == 0 and total == len(scenario.steps)

        logger.info(
            "eval: scenario '%s' done — score=%.2f (%d/%d) in %.0fms",
            scenario.name,
            score,
            passed,
            total,
            duration_ms,
        )
        return ScenarioResult(
            scenario_name=scenario.name,
            passed=all_passed,
            steps_passed=passed,
            steps_failed=failed,
            steps_total=total,
            score=score,
            duration_ms=duration_ms,
            step_results=step_results,
        )

    def _run_step(self, step: ScenarioStep, step_num: int) -> ScenarioStepResult:
        """Execute one step and score it.

        Args:
            step: The step definition.
            step_num: 1-based ordinal for logging.

        Returns:
            A :class:`ScenarioStepResult` with pass/fail verdict.
        """
        start = time.monotonic()
        error: str | None = None
        result: dict[str, Any] = {}

        try:
            result = self._execute(step.action, **step.params)
            if not isinstance(result, dict):
                result = {"raw": result}
        except Exception as exc:
            error = str(exc)
            result = {"success": False, "error": error}
            logger.debug("eval: step %d (%s) raised: %s", step_num, step.action, exc)

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        passed = self._score_step(step, result, error)
        logger.debug(
            "eval: step %d (%s) %s in %.0fms",
            step_num,
            step.action,
            "PASS" if passed else "FAIL",
            duration_ms,
        )
        return ScenarioStepResult(
            step_number=step_num,
            action=step.action,
            passed=passed,
            result=result,
            duration_ms=duration_ms,
            error=error,
        )

    @staticmethod
    def _score_step(step: ScenarioStep, result: dict[str, Any], error: str | None) -> bool:
        """Return True when *result* meets *step*'s scoring criteria.

        Scoring rules (all must pass):
        1. If ``expect_success`` is True, ``result["success"]`` must be truthy.
        2. If an exception was raised (*error* is set), always fail.
        3. Each key in ``expected_keys`` must be present in *result* and truthy.
        """
        if error:
            return False
        if step.expect_success and not result.get("success", True):
            return False
        for key in step.expected_keys:
            if not result.get(key):
                return False
        return True
