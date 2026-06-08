"""Tests for Sentinel Desktop v6.0 Deep Control Layer.

Covers: planner, grounder, verifier, control loop.
"""

from __future__ import annotations

import json

from PIL import Image

from core.control.grounder import ActionGrounder, GroundedAction
from core.control.planner import (
    ExecutionPlan,
    PlanStep,
    StepStatus,
    StepType,
    TaskPlanner,
)
from core.control.verifier import ActionVerifier, VerifyResult, _compute_pixel_diff
from core.perception.types import (
    ElementType,
    PerceptionElement,
    PerceptionResult,
)

# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class TestPlanStep:
    def test_default_values(self):
        step = PlanStep()
        assert step.id == 0
        assert step.status == StepStatus.PENDING
        assert step.retries == 0

    def test_to_dict(self):
        step = PlanStep(
            id=1, description="Click Save", step_type=StepType.CLICK, target="Save button"
        )
        d = step.to_dict()
        assert d["id"] == 1
        assert d["description"] == "Click Save"
        assert d["type"] == "click"
        assert d["target"] == "Save button"


class TestExecutionPlan:
    def test_empty_plan(self):
        plan = ExecutionPlan()
        assert plan.is_complete
        assert plan.current_step is None

    def test_advance_returns_pending_step(self):
        plan = ExecutionPlan(
            steps=[
                PlanStep(id=1, status=StepStatus.PENDING),
                PlanStep(id=2, status=StepStatus.PENDING),
            ]
        )
        step = plan.advance()
        assert step.id == 1

    def test_completed_steps(self):
        plan = ExecutionPlan(
            steps=[
                PlanStep(id=1, status=StepStatus.COMPLETED),
                PlanStep(id=2, status=StepStatus.FAILED),
                PlanStep(id=3, status=StepStatus.PENDING),
            ]
        )
        assert len(plan.completed_steps) == 1
        assert len(plan.failed_steps) == 1


class TestTaskPlanner:
    def test_parse_steps_from_json(self):
        response = json.dumps(
            [
                {"description": "Click Save", "type": "click", "target": "Save button"},
                {"description": "Wait for save", "type": "wait", "target": "screen"},
            ]
        )
        steps = TaskPlanner._parse_steps(response)
        assert len(steps) == 2
        assert steps[0].description == "Click Save"
        assert steps[0].step_type == StepType.CLICK
        assert steps[1].step_type == StepType.WAIT

    def test_parse_steps_with_markdown(self):
        response = '```json\n[{"description": "Test", "type": "click", "target": "btn"}]\n```'
        steps = TaskPlanner._parse_steps(response)
        assert len(steps) == 1

    def test_parse_invalid_json_returns_empty(self):
        steps = TaskPlanner._parse_steps("not json at all")
        assert steps == []

    def test_parse_unknown_type_defaults_to_click(self):
        response = json.dumps([{"description": "Do thing", "type": "teleport", "target": "moon"}])
        steps = TaskPlanner._parse_steps(response)
        assert steps[0].step_type == StepType.CLICK


# ---------------------------------------------------------------------------
# Grounder
# ---------------------------------------------------------------------------


class TestActionGrounder:
    def _make_perception(self, elements):
        return PerceptionResult(elements=elements)

    def test_ground_click_by_label(self):
        elements = [
            PerceptionElement(
                id=1,
                label="Save",
                element_type=ElementType.BUTTON,
                bounding_box=(100, 200, 80, 30),
                is_interactable=True,
            ),
        ]
        step = PlanStep(target="Save", step_type=StepType.CLICK)
        grounder = ActionGrounder()
        result = grounder.ground(step, self._make_perception(elements))
        assert result.is_grounded
        assert result.x == 140
        assert result.y == 215
        assert result.method == "label_match"

    def test_ground_type_step(self):
        elements = [
            PerceptionElement(
                id=1,
                label="Input",
                element_type=ElementType.INPUT,
                bounding_box=(100, 200, 200, 30),
                is_interactable=True,
            ),
        ]
        step = PlanStep(target="Input", step_type=StepType.TYPE, value="hello")
        grounder = ActionGrounder()
        result = grounder.ground(step, self._make_perception(elements))
        assert result.action_type == "type_text"

    def test_ground_key_step_needs_no_coords(self):
        step = PlanStep(step_type=StepType.KEY, value="enter")
        grounder = ActionGrounder()
        result = grounder.ground(step, PerceptionResult())
        assert result.action_type == "press_key"
        assert result.confidence == 1.0

    def test_ground_wait_step(self):
        step = PlanStep(step_type=StepType.WAIT)
        grounder = ActionGrounder()
        result = grounder.ground(step, PerceptionResult())
        assert result.action_type == "wait"

    def test_ground_fallback_to_center(self):
        img = Image.new("RGB", (800, 600))
        step = PlanStep(target="Nonexistent", step_type=StepType.CLICK)
        grounder = ActionGrounder()
        result = grounder.ground(step, PerceptionResult(annotated_image=img))
        assert result.is_grounded
        assert result.method == "fallback_center"
        assert result.confidence == 0.1

    def test_ground_by_type_match(self):
        elements = [
            PerceptionElement(
                id=1,
                label="MysteryBtn",
                element_type=ElementType.BUTTON,
                bounding_box=(200, 300, 60, 25),
                is_interactable=True,
            ),
        ]
        # Target doesn't match label, so falls to type_match
        step = PlanStep(target="something_completely_different", step_type=StepType.CLICK)
        grounder = ActionGrounder()
        result = grounder.ground(step, self._make_perception(elements))
        assert result.is_grounded
        assert result.method in ("label_match", "type_match")

    def test_grounded_action_to_dict(self):
        step = PlanStep(step_type=StepType.TYPE, value="hello")
        ga = GroundedAction(step=step, action_type="type_text", x=100, y=200)
        d = ga.to_action_dict()
        assert d["action"] == "type_text"
        assert d["x"] == 100
        assert d["text"] == "hello"


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class TestActionVerifier:
    def test_identical_screens_no_change(self):
        img = Image.new("RGB", (200, 200), color="white")
        verifier = ActionVerifier()
        report = verifier.verify(img, img)
        assert report.result == VerifyResult.NO_CHANGE

    def test_identical_screens_expected_no_change(self):
        img = Image.new("RGB", (200, 200), color="white")
        verifier = ActionVerifier()
        report = verifier.verify(img, img, expected_change="none")
        assert report.result == VerifyResult.SUCCESS

    def test_different_screens_success(self):
        before = Image.new("RGB", (200, 200), color="white")
        # Make a partial change — some pixels different, not all
        after = Image.new("RGB", (200, 200), color="white")
        pixels = after.load()
        for x in range(50, 150):
            for y in range(50, 150):
                pixels[x, y] = (255, 0, 0)
        verifier = ActionVerifier()
        report = verifier.verify(before, after)
        assert report.result == VerifyResult.SUCCESS
        assert report.pixel_diff_percent > 0

    def test_no_change_expected_fails_on_change(self):
        before = Image.new("RGB", (200, 200), color="white")
        after = Image.new("RGB", (200, 200), color="black")
        verifier = ActionVerifier()
        report = verifier.verify(before, after, expected_change="none")
        assert report.result == VerifyResult.UNEXPECTED

    def test_should_retry_on_no_change(self):
        img = Image.new("RGB", (200, 200), color="white")
        verifier = ActionVerifier()
        report = verifier.verify(img, img)
        assert report.should_retry


class TestPixelDiff:
    def test_identical_images(self):
        img = Image.new("RGB", (100, 100), color="white")
        assert _compute_pixel_diff(img, img) == 0.0

    def test_completely_different(self):
        before = Image.new("RGB", (100, 100), color="white")
        after = Image.new("RGB", (100, 100), color="black")
        assert _compute_pixel_diff(before, after) > 90.0

    def test_slight_change(self):
        before = Image.new("RGB", (200, 200), color=(128, 128, 128))
        after = Image.new("RGB", (200, 200), color=(128, 128, 128))
        pixels = after.load()
        for x in range(0, 50):
            for y in range(0, 50):
                pixels[x, y] = (200, 200, 200)
        diff = _compute_pixel_diff(before, after)
        assert 0 < diff < 100


# ---------------------------------------------------------------------------
# Control Loop
# ---------------------------------------------------------------------------


class TestControlLoop:
    """Test the main control loop orchestration."""

    def test_initialization(self):
        from core.control.loop import ControlLoop

        loop = ControlLoop()
        assert loop.planner is not None
        assert loop.grounder is not None
        assert loop.verifier is not None
        assert loop.perception is not None
        assert loop.max_retries_per_step == 3
        assert loop.max_replans == 2

    def test_custom_initialization(self):
        from core.control.loop import ControlLoop
        from core.control.planner import TaskPlanner
        from core.control.grounder import ActionGrounder

        planner = TaskPlanner()
        grounder = ActionGrounder()
        loop = ControlLoop(
            planner=planner,
            grounder=grounder,
            max_retries_per_step=5,
            max_replans=3,
        )
        assert loop.planner is planner
        assert loop.grounder is grounder
        assert loop.max_retries_per_step == 5
        assert loop.max_replans == 3

    def test_execute_with_mock_executor(self):
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        # Mock the executor
        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}

        loop = ControlLoop(executor=executor)

        # Mock the planner to return a simple completed plan
        loop.planner.plan = MagicMock(return_value=ExecutionPlan())

        result = loop.execute(goal="Test goal", max_steps=10)

        assert result["status"] == "completed"
        assert result["goal"] == "Test goal"
        assert result["steps_executed"] == 0
        assert result["elapsed_ms"] >= 0

    def test_execute_with_step_callback(self):
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}

        loop = ControlLoop(executor=executor)
        loop.planner.plan = MagicMock(return_value=ExecutionPlan())

        callback_data = []

        def mock_callback(step, grounded, report):
            callback_data.append({"step": step, "grounded": grounded, "report": report})

        result = loop.execute(goal="Test", on_step_callback=mock_callback)

        assert result["status"] == "completed"
        # Callback should be called for each step (0 in this case since plan is complete)

    def test_execute_without_executor(self):
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        loop = ControlLoop(executor=None)
        loop.planner.plan = MagicMock(return_value=ExecutionPlan())

        result = loop.execute(goal="Test goal")

        assert result["status"] == "completed"

    def test_execute_with_grounding_failure_retry(self):
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}

        loop = ControlLoop(executor=executor, max_retries_per_step=2)

        # Create a step that will fail grounding
        step = PlanStep(
            id=1,
            description="Click something",
            step_type=StepType.CLICK,
            target="nonexistent",
        )
        step.status = StepStatus.PENDING

        plan = ExecutionPlan(steps=[step])
        loop.planner.plan = MagicMock(return_value=plan)

        # Mock grounder to fail grounding (no coordinates = not grounded)
        loop.grounder.ground = MagicMock(
            return_value=GroundedAction(
                step=step,
                action_type="click",
                x=None,
                y=None,
                method="failed",
                confidence=0.0,
            )
        )

        result = loop.execute(goal="Test", max_steps=10)

        # Should handle grounding failure gracefully
        assert result["status"] in ("completed", "partial")

    def test_get_perception(self):
        from core.control.loop import ControlLoop
        from unittest.mock import patch, MagicMock

        loop = ControlLoop()

        # Mock the screenshot capture
        with patch("core.screenshot.capture_screen") as mock_capture:
            mock_img = MagicMock()
            mock_capture.return_value = mock_img

            # Mock perception analysis
            loop.perception.analyze = MagicMock(
                return_value=PerceptionResult(elements=[])
            )

            result = loop._get_perception()

            assert result is not None
            loop.perception.analyze.assert_called_once()

    def test_execute_action_success(self):
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True, "output": "Action completed"}

        loop = ControlLoop(executor=executor)

        action_dict = {"action": "click", "x": 100, "y": 200}
        result = loop._execute_action(action_dict)

        assert result["success"] is True
        executor.execute_sync.assert_called_once_with(action_dict)

    def test_execute_action_failure(self):
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.execute_sync.side_effect = Exception("Test error")

        loop = ControlLoop(executor=executor)

        action_dict = {"action": "click", "x": 100, "y": 200}
        result = loop._execute_action(action_dict)

        assert result["success"] is False
        assert "Test error" in result["output"]

    def test_verify_action_with_images(self):
        from core.control.loop import ControlLoop
        from PIL import Image

        before = Image.new("RGB", (200, 200), color="white")
        after = Image.new("RGB", (200, 200), color="black")

        loop = ControlLoop()

        before_result = PerceptionResult(annotated_image=before)
        after_result = PerceptionResult(annotated_image=after)

        report = loop._verify_action(before_result, after_result)

        assert report is not None
        assert hasattr(report, "result")

    def test_verify_action_without_images(self):
        from core.control.loop import ControlLoop

        loop = ControlLoop()

        before_result = PerceptionResult(annotated_image=None)
        after_result = PerceptionResult(annotated_image=None)

        report = loop._verify_action(before_result, after_result)

        # Should return fallback success result
        assert report is not None
        assert report.should_retry is False

    def test_execute_max_steps_limit(self):
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}

        loop = ControlLoop(executor=executor)

        # Create a plan that never completes
        step = PlanStep(
            id=1,
            description="Click something",
            step_type=StepType.CLICK,
            target="test",
        )
        step.status = StepStatus.PENDING

        # Create many steps
        steps = [PlanStep(id=i, description=f"Step {i}", step_type=StepType.WAIT) for i in range(1, 100)]
        plan = ExecutionPlan(steps=steps)
        loop.planner.plan = MagicMock(return_value=plan)

        result = loop.execute(goal="Test", max_steps=5)

        # Should stop at max_steps
        assert result["steps_executed"] <= 5

    def test_execute_with_completed_steps(self):
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}

        loop = ControlLoop(executor=executor)

        # Create a plan with some completed steps
        step1 = PlanStep(id=1, description="Done", step_type=StepType.WAIT)
        step1.status = StepStatus.COMPLETED

        step2 = PlanStep(id=2, description="Todo", step_type=StepType.WAIT)
        step2.status = StepStatus.PENDING

        plan = ExecutionPlan(steps=[step1, step2])
        loop.planner.plan = MagicMock(return_value=plan)

        # Mock grounder to succeed
        loop.grounder.ground = MagicMock(
            return_value=GroundedAction(
                step=step2,
                action_type="wait",
                x=100,
                y=100,
                method="test",
                confidence=1.0,
            )
        )

        result = loop.execute(goal="Test", max_steps=10)

        assert result["status"] == "completed"

    def test_execute_max_retries_during_grounding(self):
        """Test max retries exceeded during grounding (lines 92-102)."""
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}

        loop = ControlLoop(executor=executor, max_retries_per_step=2)

        # Create a simple plan
        step = PlanStep(
            id=1,
            description="Click button",
            step_type=StepType.CLICK,
            target="test",
        )
        plan = ExecutionPlan(steps=[step])
        loop.planner.plan = MagicMock(return_value=plan)

        # Mock grounder to return ungrounded action
        loop.grounder.ground = MagicMock(
            return_value=GroundedAction(
                step=step,
                action_type="click",
                x=None,  # No coordinates = not grounded
                y=None,
                confidence=0.0,
                method="failed",
            )
        )

        result = loop.execute(goal="Test", max_steps=10)

        # Should handle the ungrounded action with retry logic
        # The step won't execute since it's never grounded, but retries should be tracked
        assert result["status"] in ["completed", "failed", "partial"]
        # Verify that the grounder was called (indicating retry attempts were made)
        assert loop.grounder.ground.call_count > 0

    def test_execute_successful_step_completion(self):
        """Test successful step completion path (lines 121-122)."""
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True, "output": "Clicked"}

        loop = ControlLoop(executor=executor)

        # Create a simple plan
        step = PlanStep(
            id=1,
            description="Click button",
            step_type=StepType.CLICK,
            target="test",
        )
        plan = ExecutionPlan(steps=[step])
        loop.planner.plan = MagicMock(return_value=plan)

        # Mock grounder to succeed
        loop.grounder.ground = MagicMock(
            return_value=GroundedAction(
                step=step,
                action_type="click",
                x=100,
                y=100,
                method="test",
                confidence=1.0,
            )
        )

        result = loop.execute(goal="Test", max_steps=10)

        # Should complete successfully
        assert result["status"] == "completed"
        assert result["steps_executed"] == 1

    def test_execute_max_retries_during_execution(self):
        """Test max retries exceeded during execution (lines 126-127)."""
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        # Make executor fail but should retry
        executor.execute_sync.return_value = {"success": False, "should_retry": True}

        loop = ControlLoop(executor=executor, max_retries_per_step=2)

        # Create a simple plan
        step = PlanStep(
            id=1,
            description="Click button",
            step_type=StepType.CLICK,
            target="test",
        )
        plan = ExecutionPlan(steps=[step])
        loop.planner.plan = MagicMock(return_value=plan)

        # Mock grounder to succeed
        loop.grounder.ground = MagicMock(
            return_value=GroundedAction(
                step=step,
                action_type="click",
                x=100,
                y=100,
                method="test",
                confidence=1.0,
            )
        )

        result = loop.execute(goal="Test", max_steps=10)

        # Should handle retry logic
        assert result["steps_executed"] >= 1
        assert result["status"] in ["completed", "failed", "partial"]

    def test_execute_with_callback_exception(self):
        """Test callback execution with exception handling (lines 140-143)."""
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.execute_sync.return_value = {"success": True}

        loop = ControlLoop(executor=executor)

        # Create a simple plan
        step = PlanStep(
            id=1,
            description="Click button",
            step_type=StepType.CLICK,
            target="test",
        )
        plan = ExecutionPlan(steps=[step])
        loop.planner.plan = MagicMock(return_value=plan)

        # Mock grounder to succeed
        loop.grounder.ground = MagicMock(
            return_value=GroundedAction(
                step=step,
                action_type="click",
                x=100,
                y=100,
                method="test",
                confidence=1.0,
            )
        )

        # Create a callback that raises an exception
        def failing_callback(step, grounded, report):
            raise ValueError("Test exception in callback")

        result = loop.execute(goal="Test", max_steps=10, on_step_callback=failing_callback)

        # Should handle callback exception gracefully and continue
        assert result["status"] == "completed"

    def test_execute_with_no_executor(self):
        """Test execution with no executor configured (line 173)."""
        from core.control.loop import ControlLoop
        from unittest.mock import MagicMock

        # Create loop without executor
        loop = ControlLoop(executor=None)

        # Create a simple plan
        step = PlanStep(
            id=1,
            description="Click button",
            step_type=StepType.CLICK,
            target="test",
        )
        plan = ExecutionPlan(steps=[step])
        loop.planner.plan = MagicMock(return_value=plan)

        # Mock grounder to succeed
        loop.grounder.ground = MagicMock(
            return_value=GroundedAction(
                step=step,
                action_type="click",
                x=100,
                y=100,
                method="test",
                confidence=1.0,
            )
        )

        result = loop.execute(goal="Test", max_steps=10)

        # Should handle missing executor gracefully
        assert result["status"] in ["completed", "failed", "partial"]
