"""Sentinel Desktop v6.0 — Action Grounder.

Converts semantic step targets (e.g., "Click the Save button") into precise
screen coordinates using the perception pipeline's element map. Uses the
fastest available method: accessibility tree → OCR → vision model.
"""

from __future__ import annotations

import logging
from typing import Any

from core.control.planner import PlanStep
from core.perception.types import ElementType, PerceptionResult

logger = logging.getLogger(__name__)

# Element types that map to each step type
_STEP_TYPE_TO_ELEMENT_TYPES = {
    "click": [ElementType.BUTTON, ElementType.LINK, ElementType.MENU_ITEM,
              ElementType.ICON, ElementType.CHECKBOX, ElementType.RADIO,
              ElementType.TAB, ElementType.DROPDOWN, ElementType.DIALOG],
    "type": [ElementType.INPUT, ElementType.TEXT],
    "key": [],  # Keys don't target elements
    "hotkey": [],  # Hotkeys don't target elements
    "scroll": [],  # Scroll targets a region, not an element
    "wait": [],  # Wait doesn't target elements
    "read": [ElementType.TEXT, ElementType.INPUT],
    "navigate": [ElementType.BUTTON, ElementType.LINK, ElementType.ICON],
    "observe": [],  # Observe targets the whole screen
}


class GroundedAction:
    """A step that has been resolved to concrete screen coordinates.

    Attributes:
        step: The original PlanStep.
        action_type: The concrete action (click, type_text, press_key, etc.).
        x: Target X coordinate, or None.
        y: Target Y coordinate, or None.
        element_id: Perception element ID if matched, or None.
        confidence: How confident the grounding is (0.0–1.0).
        method: How the grounding was achieved (accessibility, ocr, fallback).
    """

    __slots__ = ("step", "action_type", "x", "y", "element_id", "confidence", "method")

    def __init__(
        self,
        step: PlanStep,
        action_type: str = "click",
        x: int | None = None,
        y: int | None = None,
        element_id: int | None = None,
        confidence: float = 0.0,
        method: str = "none",
    ) -> None:
        self.step = step
        self.action_type = action_type
        self.x = x
        self.y = y
        self.element_id = element_id
        self.confidence = confidence
        self.method = method

    @property
    def is_grounded(self) -> bool:
        """Return True if coordinates are available."""
        return self.x is not None and self.y is not None

    def to_action_dict(self) -> dict[str, Any]:
        """Convert to an action dict for the executor."""
        action: dict[str, Any] = {"action": self.action_type}
        if self.x is not None and self.y is not None:
            action["x"] = self.x
            action["y"] = self.y
        if self.step.value is not None:
            action["text"] = self.step.value
        return action


class ActionGrounder:
    """Converts plan steps to grounded actions using perception data.

    Usage::

        grounder = ActionGrounder()
        grounded = grounder.ground(step, perception_result)
        if grounded.is_grounded:
            print(f"Click at ({grounded.x}, {grounded.y})")
    """

    def ground(self, step: PlanStep, perception: PerceptionResult) -> GroundedAction:
        """Convert a plan step to a grounded action.

        Tries in order:
            1. Label match from perception elements
            2. Element type match from perception elements
            3. Fallback to screen center

        Args:
            step: The plan step to ground.
            perception: The current perception result with element map.

        Returns:
            A GroundedAction with coordinates or a fallback.
        """
        # Steps that don't need coordinates
        if step.step_type.value in ("key", "hotkey"):
            return self._ground_keyboard(step)
        if step.step_type.value == "wait":
            return GroundedAction(
                step=step, action_type="wait", confidence=1.0, method="direct",
            )
        if step.step_type.value == "observe":
            return self._ground_observe(step)

        # Try label match first
        grounded = self._ground_by_label(step, perception)
        if grounded is not None and grounded.is_grounded:
            return grounded

        # Try type match
        grounded = self._ground_by_type(step, perception)
        if grounded is not None and grounded.is_grounded:
            return grounded

        # Fallback
        return self._ground_fallback(step, perception)

    def _ground_by_label(self, step: PlanStep, perception: PerceptionResult) -> GroundedAction | None:
        """Try to find the target by matching step.target to element labels."""
        target = (step.target or "").lower().strip()
        if not target:
            return None

        # Exact/partial label match on interactable elements
        for elem in perception.interactable_elements():
            label = (elem.label or "").lower().strip()
            if target in label or label in target:
                cx, cy = elem.center
                return GroundedAction(
                    step=step,
                    action_type=self._step_to_action_type(step),
                    x=cx,
                    y=cy,
                    element_id=elem.id,
                    confidence=0.9,
                    method="label_match",
                )

        return None

    def _ground_by_type(self, step: PlanStep, perception: PerceptionResult) -> GroundedAction | None:
        """Try to find the target by matching element types."""
        preferred_types = _STEP_TYPE_TO_ELEMENT_TYPES.get(step.step_type.value, [])
        if not preferred_types:
            return None

        for elem in perception.interactable_elements():
            if elem.element_type in preferred_types:
                cx, cy = elem.center
                return GroundedAction(
                    step=step,
                    action_type=self._step_to_action_type(step),
                    x=cx,
                    y=cy,
                    element_id=elem.id,
                    confidence=0.5,
                    method="type_match",
                )

        return None

    @staticmethod
    def _ground_keyboard(step: PlanStep) -> GroundedAction:
        """Ground a keyboard step (no coordinates needed)."""
        if step.step_type.value == "hotkey":
            return GroundedAction(
                step=step,
                action_type="hotkey",
                confidence=1.0,
                method="direct",
            )
        return GroundedAction(
            step=step,
            action_type="press_key",
            confidence=1.0,
            method="direct",
        )

    @staticmethod
    def _ground_observe(step: PlanStep) -> GroundedAction:
        """Ground an observe step (screenshot, no action)."""
        return GroundedAction(
            step=step,
            action_type="screenshot",
            confidence=1.0,
            method="direct",
        )

    @staticmethod
    def _ground_fallback(step: PlanStep, perception: PerceptionResult) -> GroundedAction:
        """Fallback: use screen center if no element found."""
        # If there are any interactable elements, pick the first one
        interactable = perception.interactable_elements()
        if interactable:
            elem = interactable[0]
            cx, cy = elem.center
            return GroundedAction(
                step=step,
                action_type=ActionGrounder._step_to_action_type(step),
                x=cx, y=cy,
                element_id=elem.id,
                confidence=0.2,
                method="fallback_first_interactable",
            )

        # Absolute fallback: screen center (from annotated image size)
        if perception.annotated_image:
            w, h = perception.annotated_image.size
            return GroundedAction(
                step=step,
                action_type=ActionGrounder._step_to_action_type(step),
                x=w // 2, y=h // 2,
                confidence=0.1,
                method="fallback_center",
            )

        return GroundedAction(step=step, confidence=0.0, method="none")

    @staticmethod
    def _step_to_action_type(step: PlanStep) -> str:
        """Map StepType to action executor action type."""
        mapping = {
            "click": "click",
            "type": "type_text",
            "scroll": "scroll",
            "navigate": "click",
            "read": "read_text",
        }
        return mapping.get(step.step_type.value, "click")
