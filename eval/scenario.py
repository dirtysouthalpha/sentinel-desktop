"""Sentinel Desktop v21 — Scenario data model.

A :class:`Scenario` is a named, versioned sequence of action steps with
expected outcomes.  Each :class:`ScenarioStep` specifies the action name,
parameters, and what keys in the result dict must be truthy for the step
to pass.  :class:`ScenarioResult` and :class:`ScenarioStepResult` hold the
outcome of a replay run.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Scenario definition
# ---------------------------------------------------------------------------


@dataclass
class ScenarioStep:
    """One action step in a scenario.

    Attributes:
        action: Action name (e.g. ``"click"``, ``"read_file"``).
        params: Parameter dict passed to ActionExecutor.
        expected_keys: Keys in the result dict that must be present and
            truthy for the step to pass scoring.
        expect_success: Whether the result ``success`` key must be True.
    """

    action: str
    params: dict[str, Any] = field(default_factory=dict)
    expected_keys: list[str] = field(default_factory=list)
    expect_success: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScenarioStep:
        return cls(
            action=data["action"],
            params=data.get("params", {}),
            expected_keys=data.get("expected_keys", []),
            expect_success=data.get("expect_success", True),
        )


@dataclass
class Scenario:
    """A named, versioned sequence of action steps for evaluation.

    Attributes:
        name: Unique identifier (used as the file stem).
        description: Human-readable purpose of this scenario.
        goal: Natural-language goal the scenario tests.
        steps: Ordered list of :class:`ScenarioStep` objects.
        tags: Optional categorisation tags (e.g. ``["ui", "file"]``).
        version: Semantic version string.
        created: ISO 8601 creation timestamp.
    """

    name: str
    description: str
    goal: str
    steps: list[ScenarioStep] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    version: str = "1.0"
    created: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "tags": self.tags,
            "version": self.version,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scenario:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            goal=data.get("goal", ""),
            steps=[ScenarioStep.from_dict(s) for s in data.get("steps", [])],
            tags=data.get("tags", []),
            version=data.get("version", "1.0"),
            created=data.get("created", ""),
        )

    def save(self, path: Path) -> None:
        """Serialise to a JSON file at *path*."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Scenario:
        """Deserialise from a JSON file at *path*."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class ScenarioStepResult:
    """Outcome of one step during a scenario run.

    Attributes:
        step_number: 1-based index.
        action: Action name executed.
        passed: Whether the step met its scoring criteria.
        result: Raw dict returned by the executor.
        duration_ms: Wall-clock milliseconds for this step.
        error: Exception message if the executor raised.
    """

    step_number: int
    action: str
    passed: bool
    result: dict[str, Any]
    duration_ms: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioResult:
    """Aggregate outcome of a scenario run.

    Attributes:
        scenario_name: Name of the scenario.
        passed: True when all steps pass.
        steps_passed: Count of passing steps.
        steps_failed: Count of failing steps.
        steps_total: Total step count.
        score: Fraction of steps that passed (0.0 – 1.0).
        duration_ms: Total wall-clock milliseconds.
        step_results: Per-step result objects.
        error: Top-level error if the run was aborted.
    """

    scenario_name: str
    passed: bool
    steps_passed: int
    steps_failed: int
    steps_total: int
    score: float
    duration_ms: float
    step_results: list[ScenarioStepResult] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "passed": self.passed,
            "steps_passed": self.steps_passed,
            "steps_failed": self.steps_failed,
            "steps_total": self.steps_total,
            "score": self.score,
            "duration_ms": self.duration_ms,
            "step_results": [r.to_dict() for r in self.step_results],
            "error": self.error,
        }
