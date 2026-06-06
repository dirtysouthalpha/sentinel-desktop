"""Sentinel Desktop v6.0 — Task Planner.

Decomposes a user goal into a sequence of high-level steps using a heavy
LLM. Each step describes WHAT to do (not WHERE — that's the grounder's job).

Steps are semantic: "Click the Save button", "Type the filename", "Press Enter".
The grounder converts these to precise coordinates using the perception pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class StepStatus(str, Enum):
    """Status of a plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepType(str, Enum):
    """Category of action a step represents."""

    CLICK = "click"
    TYPE = "type"
    KEY = "key"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    WAIT = "wait"
    READ = "read"
    NAVIGATE = "navigate"
    OBSERVE = "observe"


@dataclass
class PlanStep:
    """A single step in the execution plan.

    Attributes:
        id: Step number (1-indexed).
        description: What to do in plain English.
        step_type: Category of action.
        target: Semantic target (e.g., "Save button", "filename field").
        value: Optional value (for type steps).
        status: Current execution status.
        retries: Number of times this step has been retried.
        max_retries: Maximum retries before marking as failed.
        result: Result from execution (success/failure details).
        grounded_coords: Coordinates from the grounder (x, y) or None.
    """

    id: int = 0
    description: str = ""
    step_type: StepType = StepType.CLICK
    target: str = ""
    value: str | None = None
    status: StepStatus = StepStatus.PENDING
    retries: int = 0
    max_retries: int = 3
    result: dict[str, Any] = field(default_factory=dict)
    grounded_coords: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "type": self.step_type.value,
            "target": self.target,
            "value": self.value,
            "status": self.status.value,
            "retries": self.retries,
        }


@dataclass
class ExecutionPlan:
    """A complete execution plan with steps and metadata."""

    goal: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    current_step_index: int = 0
    created_at: str = ""
    total_retries: int = 0

    @property
    def current_step(self) -> PlanStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def is_complete(self) -> bool:
        return self.current_step_index >= len(self.steps)

    @property
    def completed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.COMPLETED]

    @property
    def failed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    def advance(self) -> PlanStep | None:
        """Move to the next pending step and return it."""
        while self.current_step_index < len(self.steps):
            step = self.steps[self.current_step_index]
            if step.status == StepStatus.PENDING:
                return step
            self.current_step_index += 1
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step_index,
            "completed": len(self.completed_steps),
            "failed": len(self.failed_steps),
        }


# System prompt for the planner
_PLANNER_PROMPT = """\
You are a task planner for a desktop automation agent. Given a user goal and
the current screen state, produce a short plan of 1-10 steps.

Each step must be a JSON object with:
- "description": What to do (e.g., "Click the Save button")
- "type": One of: click, type, key, hotkey, scroll, wait, read, navigate, observe
- "target": What to interact with (e.g., "Save button", "filename input field")
- "value": Optional value for type/hotkey steps

Rules:
- Be specific about targets (button labels, field names)
- Include a wait/observe step after navigation or opening apps
- Minimize steps — efficiency matters
- If the goal is already met, return an empty array

Return ONLY a JSON array of step objects. No markdown. No commentary.
"""


class TaskPlanner:
    """Plans high-level steps for a goal using an LLM.

    Usage::

        planner = TaskPlanner()
        plan = planner.plan("Save the document as report.pdf")
        for step in plan.steps:
            print(f"Step {step.id}: {step.description}")
    """

    def __init__(self, llm_client: Any | None = None) -> None:
        """Initialize with an optional LLM client.

        Args:
            llm_client: An LLMClient instance. If None, creates one on first use.
        """
        self._llm = llm_client

    def plan(self, goal: str, context: str = "") -> ExecutionPlan:
        """Create an execution plan for a goal.

        Args:
            goal: The user's goal in plain English.
            context: Optional context (e.g., current screen description).

        Returns:
            An ExecutionPlan with steps.
        """
        prompt = f"Goal: {goal}\n"
        if context:
            prompt += f"\nCurrent screen context:\n{context}\n"
        prompt += "\nProduce a plan:"

        try:
            steps = self._query_llm(prompt)
            return ExecutionPlan(
                goal=goal,
                steps=steps,
            )
        except Exception as exc:
            logger.error("Planning failed: %s", exc)
            # Return a minimal fallback plan
            return ExecutionPlan(
                goal=goal,
                steps=[
                    PlanStep(
                        id=1,
                        description=goal,
                        step_type=StepType.OBSERVE,
                        target="screen",
                    )
                ],
            )

    def _query_llm(self, prompt: str) -> list[PlanStep]:
        """Query the LLM and parse the response into plan steps."""
        if self._llm is None:
            from core.llm_client import LLMClient

            self._llm = LLMClient()

        # Use a simple request — in production this would use the full
        # config (provider, model, api_key from config)
        messages = [
            {"role": "system", "content": _PLANNER_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response = self._llm.chat(
            provider="openai",
            model="gpt-4o",
            messages=messages,
            temperature=0.1,
        )

        return self._parse_steps(response)

    @staticmethod
    def _parse_steps(response: str) -> list[PlanStep]:
        """Parse LLM response into PlanStep objects."""
        # Extract JSON from response (may have markdown fences)
        json_str = response.strip()
        json_match = re.search(r"\[.*\]", json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group()

        try:
            raw_steps = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse planner response as JSON")
            return []

        steps = []
        for i, raw in enumerate(raw_steps):
            step_type_str = raw.get("type", "click").lower()
            try:
                step_type = StepType(step_type_str)
            except ValueError:
                step_type = StepType.CLICK

            steps.append(
                PlanStep(
                    id=i + 1,
                    description=raw.get("description", ""),
                    step_type=step_type,
                    target=raw.get("target", ""),
                    value=raw.get("value"),
                )
            )

        return steps
