"""Gap tests for core/control/loop.py — covers lines 92-102, 121-122, 126-127."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.control.planner import ExecutionPlan, PlanStep, StepStatus, StepType


def _make_loop(max_retries=1):
    from core.control.loop import ControlLoop

    executor = MagicMock()
    executor.execute_sync.return_value = {"success": True, "output": "ok"}
    return ControlLoop(executor=executor, max_retries_per_step=max_retries)


def _make_plan(step_type=StepType.CLICK):
    step = PlanStep(id=1, description="Do something", step_type=step_type)
    return ExecutionPlan(steps=[step])


def _ungrounded_action(step):
    from core.control.grounder import GroundedAction

    return GroundedAction(step=step, x=None, y=None, method="failed", confidence=0.0)


def _grounded_action(step, x=100, y=200):
    from core.control.grounder import GroundedAction

    return GroundedAction(step=step, x=x, y=y, method="accessibility", confidence=0.9)


def _make_fake_perception():
    from core.perception.types import PerceptionResult

    return PerceptionResult(elements=[])


# ── Lines 92-102 — grounding failure with exhausted retries ──────────────────


class TestGroundingFailureExhausted:
    """Lines 92-102 — grounding fails and retries >= max_retries_per_step."""

    def test_click_step_grounding_fails_marks_step_failed(self):
        loop = _make_loop(max_retries=1)
        plan = _make_plan(StepType.CLICK)

        loop.planner.plan = MagicMock(return_value=plan)
        loop.grounder.ground = MagicMock(
            side_effect=lambda step, pr: _ungrounded_action(step)
        )

        fake_perception = _make_fake_perception()
        loop._get_perception = MagicMock(return_value=fake_perception)

        result = loop.execute(goal="click button", max_steps=10)

        # Step should be failed and recorded with grounding_failed status
        assert any(r.get("status") == "grounding_failed" for r in result["results"])
        assert result["failed"] >= 1


# ── Lines 121-122 — successful action: step completes ───────────────────────


class TestStepCompletedSuccessfully:
    """Lines 121-122 — step.status=COMPLETED after successful grounding+execution."""

    def test_successful_step_marks_completed(self):
        from core.control.verifier import VerificationReport, VerifyResult

        loop = _make_loop(max_retries=1)
        plan = _make_plan(StepType.CLICK)

        loop.planner.plan = MagicMock(return_value=plan)
        loop.grounder.ground = MagicMock(
            side_effect=lambda step, pr: _grounded_action(step)
        )

        fake_perception = _make_fake_perception()
        loop._get_perception = MagicMock(return_value=fake_perception)

        # Verification report: success
        success_report = VerificationReport(
            result=VerifyResult.SUCCESS, pixel_diff_percent=10.0, confidence=0.9
        )
        loop._verify_action = MagicMock(return_value=success_report)

        result = loop.execute(goal="click button", max_steps=10)

        # Should have completed steps
        assert result["completed"] >= 1
        assert result["steps_executed"] >= 1


# ── Lines 126-127 — execution failure with exhausted retries ─────────────────


class TestExecutionFailureExhausted:
    """Lines 126-127 — execution fails verify and retries >= max_retries_per_step."""

    def test_failed_verify_exhausted_marks_step_failed(self):
        from core.control.verifier import VerificationReport, VerifyResult

        loop = _make_loop(max_retries=1)
        plan = _make_plan(StepType.CLICK)

        loop.planner.plan = MagicMock(return_value=plan)
        loop.grounder.ground = MagicMock(
            side_effect=lambda step, pr: _grounded_action(step)
        )

        fake_perception = _make_fake_perception()
        loop._get_perception = MagicMock(return_value=fake_perception)

        # Verification: no change (should_retry=True), retries exhaust after 1
        fail_report = VerificationReport(
            result=VerifyResult.NO_CHANGE, pixel_diff_percent=0.0, confidence=0.0
        )
        loop._verify_action = MagicMock(return_value=fail_report)

        result = loop.execute(goal="click button", max_steps=10)

        # Step exhausted retries — ended as failed
        assert result["failed"] >= 1
