"""Gap tests for core/control/grounder.py — covers lines 128, 149, 174, 195, 211, 224-226, 248."""

from __future__ import annotations

from core.control.grounder import ActionGrounder
from core.control.planner import PlanStep, StepType
from core.perception.types import ElementSource, ElementType, PerceptionElement, PerceptionResult


def _step(step_type: StepType, target: str = "", value: str | None = None) -> PlanStep:
    return PlanStep(id=1, description="test", step_type=step_type, target=target, value=value)


def _empty_perception() -> PerceptionResult:
    return PerceptionResult(elements=[])


def _perception_with_button(x: int = 100, y: int = 200, label: str = "OK") -> PerceptionResult:
    """Return a PerceptionResult with one interactable button."""
    elem = PerceptionElement(
        id=1,
        label=label,
        element_type=ElementType.BUTTON,
        bounding_box=(x - 10, y - 10, 20, 20),  # (left, top, width, height)
        source=ElementSource.ACCESSIBILITY,
        is_interactable=True,
        confidence=0.95,
    )
    return PerceptionResult(elements=[elem])


# ── Line 128 — observe step returns _ground_observe ─────────────────────────


class TestGroundObserveStep:
    """Line 128 — StepType.OBSERVE routed to _ground_observe."""

    def test_observe_returns_screenshot_action(self):
        grounder = ActionGrounder()
        step = _step(StepType.OBSERVE)
        result = grounder.ground(step, _empty_perception())
        assert result.action_type == "screenshot"
        assert result.method == "direct"


# ── Lines 149 — _ground_by_label returns None when target is empty ───────────


class TestGroundByLabelEmptyTarget:
    """Line 149 — _ground_by_label returns None when step.target is empty/None."""

    def test_empty_target_returns_none(self):
        grounder = ActionGrounder()
        step = _step(StepType.CLICK, target="")
        result = grounder._ground_by_label(step, _empty_perception())
        assert result is None

    def test_whitespace_only_target_returns_none(self):
        grounder = ActionGrounder()
        step = _step(StepType.CLICK, target="   ")
        result = grounder._ground_by_label(step, _empty_perception())
        assert result is None


# ── Line 174 — _ground_by_type returns None when step_type has no preferred types ─────


class TestGroundByTypeNoPreferred:
    """Line 174 — _ground_by_type returns None when step_type maps to empty element list."""

    def test_observe_type_has_no_preferred_element_types(self):
        # OBSERVE → _STEP_TYPE_TO_ELEMENT_TYPES["observe"] == [] → return None at line 174
        grounder = ActionGrounder()
        step = _step(StepType.OBSERVE)
        result = grounder._ground_by_type(step, _perception_with_button())
        assert result is None

    def test_wait_type_has_no_preferred_element_types(self):
        grounder = ActionGrounder()
        step = _step(StepType.WAIT)
        result = grounder._ground_by_type(step, _perception_with_button())
        assert result is None

    def test_key_type_has_no_preferred_element_types(self):
        grounder = ActionGrounder()
        step = _step(StepType.KEY)
        result = grounder._ground_by_type(step, _perception_with_button())
        assert result is None


# ── Lines 194-195 — _ground_keyboard returns hotkey GroundedAction ────────────


class TestGroundKeyboardHotkey:
    """Lines 194-195 — _ground_keyboard returns hotkey action for HOTKEY step."""

    def test_hotkey_step_returns_hotkey_action_type(self):
        step = _step(StepType.HOTKEY, value="ctrl+s")
        result = ActionGrounder._ground_keyboard(step)
        assert result.action_type == "hotkey"
        assert result.method == "direct"
        assert result.confidence == 1.0

    def test_key_step_returns_press_key_action_type(self):
        step = _step(StepType.KEY, value="enter")
        result = ActionGrounder._ground_keyboard(step)
        assert result.action_type == "press_key"
        assert result.method == "direct"
        assert result.confidence == 1.0


# ── Lines 210-211 — _ground_observe returns GroundedAction ──────────────────


class TestGroundObserveDirect:
    """Lines 210-211 — _ground_observe returns screenshot GroundedAction."""

    def test_observe_direct_returns_screenshot_action(self):
        step = _step(StepType.OBSERVE)
        result = ActionGrounder._ground_observe(step)
        assert result.action_type == "screenshot"
        assert result.method == "direct"
        assert result.confidence == 1.0
        assert result.step is step

    def test_observe_returns_no_coordinates(self):
        step = _step(StepType.OBSERVE)
        result = ActionGrounder._ground_observe(step)
        assert result.x is None
        assert result.y is None


# ── Lines 223-226 — _ground_fallback first interactable element ──────────────


class TestGroundFallbackFirstInteractable:
    """Lines 223-226 — _ground_fallback picks first interactable element when available."""

    def test_fallback_picks_first_interactable(self):
        step = _step(StepType.CLICK, target="unknown-target-no-match")
        perception = _perception_with_button(x=150, y=250)
        result = ActionGrounder._ground_fallback(step, perception)
        assert result.method == "fallback_first_interactable"
        assert result.x is not None
        assert result.y is not None
        assert result.confidence == 0.2
        assert result.element_id == 1

    def test_fallback_center_computed_from_bounding_box(self):
        # bounding_box=(100, 200, 20, 20) → center = (100+10, 200+10) = (110, 210)
        step = _step(StepType.CLICK, target="something")
        elem = PerceptionElement(
            id=7,
            label="Submit",
            element_type=ElementType.BUTTON,
            bounding_box=(100, 200, 20, 20),
            source=ElementSource.ACCESSIBILITY,
            is_interactable=True,
            confidence=0.9,
        )
        perception = PerceptionResult(elements=[elem])
        result = ActionGrounder._ground_fallback(step, perception)
        assert result.x == 110
        assert result.y == 210


# ── Line 248 — _ground_fallback returns none when no elements and no image ────


class TestGroundFallbackNone:
    """Line 248 — _ground_fallback returns GroundedAction with method='none'."""

    def test_empty_perception_no_image_returns_none_method(self):
        step = _step(StepType.CLICK, target="ghost-button")
        perception = _empty_perception()
        assert perception.annotated_image is None
        result = ActionGrounder._ground_fallback(step, perception)
        assert result.method == "none"
        assert result.confidence == 0.0
        assert result.x is None
        assert result.y is None
        assert result.is_grounded is False
