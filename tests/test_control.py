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
