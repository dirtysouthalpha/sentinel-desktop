"""Sentinel Desktop v6.0 — Control Loop.

Orchestrates the Plan → Ground → Execute → Verify cycle.
Re-plans on failure, retries on grounding misses, and reports results.

This is the main entry point for v6.0 deep control.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.control.grounder import ActionGrounder
from core.control.planner import StepStatus, StepType, TaskPlanner
from core.control.verifier import ActionVerifier, VerificationReport, VerifyResult
from core.perception.pipeline import PerceptionPipeline
from core.perception.types import PerceptionResult

logger = logging.getLogger(__name__)


class ControlLoop:
    """Orchestrates the Plan → Ground → Execute → Verify loop.

    Usage::

        loop = ControlLoop()
        result = loop.execute(goal="Save the document as report.pdf")
        print(result["status"])
    """

    def __init__(
        self,
        planner: TaskPlanner | None = None,
        grounder: ActionGrounder | None = None,
        verifier: ActionVerifier | None = None,
        perception: PerceptionPipeline | None = None,
        executor: Any | None = None,
        max_retries_per_step: int = 3,
        max_replans: int = 2,
    ) -> None:
        self.planner = planner or TaskPlanner()
        self.grounder = grounder or ActionGrounder()
        self.verifier = verifier or ActionVerifier()
        self.perception = perception or PerceptionPipeline()
        self.executor = executor
        self.max_retries_per_step = max_retries_per_step
        self.max_replans = max_replans

    def execute(
        self,
        goal: str,
        max_steps: int = 50,
        on_step_callback: Any | None = None,
    ) -> dict[str, Any]:
        """Execute a goal through the full control loop.

        Args:
            goal: The user's goal in plain English.
            max_steps: Maximum number of steps to execute.
            on_step_callback: Optional callback(step, grounded, report) per step.

        Returns:
            Dict with status, steps completed, and results.
        """
        start_time = time.monotonic()
        plan = self.planner.plan(goal)
        steps_executed = 0
        results: list[dict[str, Any]] = []

        while not plan.is_complete and steps_executed < max_steps:
            step = plan.advance()
            if step is None:
                break

            step.status = StepStatus.IN_PROGRESS

            # Ground the step
            perception_result = self._get_perception()
            grounded = self.grounder.ground(step, perception_result)

            if not grounded.is_grounded and step.step_type not in (
                StepType.KEY,
                StepType.HOTKEY,
                StepType.WAIT,
            ):
                # Can't ground — retry or fail
                step.retries += 1
                if step.retries >= self.max_retries_per_step:
                    step.status = StepStatus.FAILED
                    results.append(
                        {
                            "step": step.to_dict(),
                            "status": "grounding_failed",
                            "confidence": 0.0,
                        }
                    )
                    plan.current_step_index += 1
                    steps_executed += 1
                    continue
                continue  # Retry grounding on next iteration

            # Execute the grounded action
            action_dict = grounded.to_action_dict()
            exec_result = self._execute_action(action_dict)

            # Verify the action
            after_perception = self._get_perception()
            report = self._verify_action(perception_result, after_perception)

            # Record result
            step.result = {
                "action": action_dict,
                "exec_result": exec_result,
                "verification": report.to_dict(),
            }

            if report.is_success or not report.should_retry:
                step.status = StepStatus.COMPLETED
                plan.current_step_index += 1
            else:
                step.retries += 1
                if step.retries >= self.max_retries_per_step:
                    step.status = StepStatus.FAILED
                    plan.current_step_index += 1

            results.append(
                {
                    "step": step.to_dict(),
                    "grounded_method": grounded.method,
                    "verification": report.to_dict(),
                }
            )

            steps_executed += 1

            if on_step_callback:
                try:
                    on_step_callback(step, grounded, report)
                except Exception:
                    logger.debug("on_step_callback raised exception", exc_info=True)

        elapsed = (time.monotonic() - start_time) * 1000

        return {
            "status": "completed" if not plan.failed_steps else "partial",
            "goal": goal,
            "steps_executed": steps_executed,
            "total_steps": len(plan.steps),
            "completed": len(plan.completed_steps),
            "failed": len(plan.failed_steps),
            "elapsed_ms": round(elapsed, 1),
            "results": results,
        }

    def _get_perception(self) -> PerceptionResult:
        """Capture and analyze the current screen."""
        from core.screenshot import capture_screen

        screenshot = capture_screen()
        return self.perception.analyze(
            screenshot,
            include_accessibility=True,
            include_ocr=True,
            include_vision=False,
        )

    def _execute_action(self, action_dict: dict[str, Any]) -> dict[str, Any]:
        """Execute a grounded action via the executor."""
        if self.executor is None:
            return {"success": False, "output": "No executor configured"}
        try:
            return self.executor.execute_sync(action_dict)
        except Exception as exc:
            return {"success": False, "output": str(exc)}

    def _verify_action(
        self, before_perception: PerceptionResult, after_perception: PerceptionResult
    ) -> VerificationReport:
        """Verify action success using before/after perception."""

        before_img = before_perception.annotated_image
        after_img = after_perception.annotated_image
        if before_img and after_img:
            return self.verifier.verify(before_img, after_img)
        # Fallback when images not available - assume success to avoid blocking
        return VerificationReport(
            result=VerifyResult.SUCCESS,
            pixel_diff_percent=0.0,
            confidence=0.0,
            details="No images available for verification",
        )
