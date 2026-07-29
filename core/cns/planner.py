"""CNS Task Planner — decomposes complex goals into subtasks with dependencies.

Rule-based decomposition for reliability. Splits on natural language
sequencing cues ("then", "after that", "and then", "step by step",
commas in multi-part goals). Assigns task types by keyword detection
and links sequential dependencies so the conductor can schedule work.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of subtasks the CNS can plan."""
    SHELL = "shell"
    REASONING = "reasoning"
    EVALUATION = "evaluation"
    DESKTOP = "desktop"
    MONITORING = "monitoring"


# Keywords that signal each task type.
_TYPE_KEYWORDS: dict[TaskType, list[str]] = {
    TaskType.SHELL: ["run", "execute", "command", "shell", "bash", "script",
                     "install", "download", "fetch", "list", "check"],
    TaskType.REASONING: ["analyze", "plan", "decide", "evaluate", "reason",
                         "think", "consider", "compare", "recommend"],
    TaskType.EVALUATION: ["verify", "validate", "test", "score", "measure",
                          "assess", "audit", "review"],
    TaskType.DESKTOP: ["click", "type", "open", "close", "screenshot",
                       "window", "app", "browser", "desktop"],
    TaskType.MONITORING: ["monitor", "watch", "alert", "health", "status",
                          "heartbeat", "poll", "track"],
}

# Sequencing cues that indicate multi-step goals.
_SEQUENCE_PATTERNS = [
    r"\bthen\b",
    r"\bafter\s+that\b",
    r"\band\s+then\b",
    r"\band\s+also\b",
    r"\bstep\s+by\s+step\b",
    r"\bfirst\b",
    r"\bsecond\b",
    r"\bfinally\b",
    r"\bonce\s+done\b",
    r"\bwhen\s+finished\b",
    r"\bnext\b",
    r"\balso\b",
]


@dataclass
class Subtask:
    """A single unit of work within a CNS plan."""
    id: str
    description: str
    type: TaskType
    status: str = "pending"
    dependencies: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)

    def is_ready(self, completed: set[str]) -> bool:
        """True if all dependencies are in the completed set."""
        return all(dep in completed for dep in self.dependencies)


def _classify(description: str) -> TaskType:
    """Classify a subtask description into a task type by keyword match."""
    text = description.lower()
    best_type = TaskType.SHELL  # default
    best_count = 0
    for task_type, keywords in _TYPE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > best_count:
            best_count = count
            best_type = task_type
    return best_type


def _split_goal(goal: str) -> list[str]:
    """Split a goal into individual step descriptions."""
    if not goal or not goal.strip():
        return []

    text = goal.strip()

    # Try splitting on sequencing patterns first.
    for pattern in _SEQUENCE_PATTERNS:
        parts = re.split(pattern, text, flags=re.IGNORECASE)
        parts = [p.strip().strip(",;.") for p in parts if p.strip().strip(",;.")]
        if len(parts) >= 2:
            return parts

    # Fall back to splitting on semicolons or "and" between verb phrases.
    if ";" in text:
        parts = [p.strip() for p in text.split(";") if p.strip()]
        if len(parts) >= 2:
            return parts

    # Split on commas if there are at least 3 parts (avoids splitting
    # "do X in dir A, B" which is a single step).
    comma_parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(comma_parts) >= 3:
        return comma_parts

    return [text]


class TaskPlanner:
    """Decomposes complex goals into dependency-linked subtasks."""

    def decompose(self, goal: str) -> list[Subtask]:
        """Decompose a goal into a list of subtasks.

        Each subtask has a unique ID, a task type, and optional
        dependencies on prior subtasks (forming a chain).
        """
        steps = _split_goal(goal)
        if not steps:
            return []

        subtasks: list[Subtask] = []
        for i, step in enumerate(steps):
            st = Subtask(
                id=str(uuid.uuid4())[:8],
                description=step,
                type=_classify(step),
            )
            if i > 0:
                # Chain: each step depends on the previous.
                st.dependencies = [subtasks[i - 1].id]
            subtasks.append(st)

        logger.debug("Decomposed goal into %d subtasks", len(subtasks))
        return subtasks

    def build_task_graph(self, goal: str) -> dict[str, Subtask]:
        """Build a task graph (id -> subtask) for a goal."""
        subtasks = self.decompose(goal)
        return {st.id: st for st in subtasks}
