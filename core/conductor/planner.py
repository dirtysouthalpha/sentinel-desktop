"""Sentinel Desktop v12.0 — Task Planner.

Decomposes complex goals into subtasks with dependencies.
Uses rule-based decomposition for reliability (LLM-assisted
decomposition available as optional enhancement).

Each subtask has: id, description, type, dependencies, priority.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Subtask:
    """A single subtask within a decomposed goal."""
    subtask_id: str
    description: str
    task_type: str  # desktop, terminal, browser, monitor, network
    dependencies: list[str] = field(default_factory=list)
    priority: int = 0
    assigned_agent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "description": self.description,
            "task_type": self.task_type,
            "dependencies": self.dependencies,
            "priority": self.priority,
            "assigned_agent": self.assigned_agent,
        }


class TaskPlanner:
    """Decomposes goals into executable subtask plans.

    Usage::

        planner = TaskPlanner()
        plan = planner.decompose("Login to firewall, check ARP, and export config")
        for subtask in plan:
            print(subtask.description)
    """

    # Task type detection rules: (keywords, task_type)
    _TYPE_RULES: list[tuple[list[str], str]] = [
        (
            [
                "ssh", "ssh_connect", "ssh_run", "ssh_show",
                "ssh_ping", "router", "switch", "firewall config",
                "show version", "show interface",
            ],
            "network",
        ),
        (
            ["browser", "website", "web ", "navigate", "portal", "login to", "open url", "http"],
            "browser",
        ),
        (
            ["terminal", "command", "powershell", "bash", "script", "execute", "run "],
            "terminal",
        ),
        (
            ["monitor", "watch", "alert", "check ", "verify", "status", "health", "uptime"],
            "monitor",
        ),
        (
            ["click", "type", "window", "app", "open ", "desktop", "screenshot", "ocr"],
            "desktop",
        ),
    ]

    # Conjunction patterns that indicate multiple subtasks
    _SPLIT_PATTERNS: list[str] = [
        r"\band\b",
        r"\bthen\b",
        r"\bafter that\b",
        r"\bnext\b",
        r"\bfollowed by\b",
        r",\s*",
    ]

    def decompose(self, goal: str) -> list[Subtask]:
        """Decompose a goal into subtasks.

        Args:
            goal: User's goal in plain English.

        Returns:
            List of Subtask with IDs, types, and dependencies.
        """
        # Split the goal into potential subtask fragments
        fragments = self._split_goal(goal)

        if not fragments:
            # Single task
            return [Subtask(
                subtask_id="t-1",
                description=goal.strip(),
                task_type=self._detect_type(goal),
                priority=0,
            )]

        subtasks = []
        for i, fragment in enumerate(fragments):
            subtask = Subtask(
                subtask_id=f"t-{i + 1}",
                description=fragment.strip(),
                task_type=self._detect_type(fragment),
                priority=len(fragments) - i,
            )
            # Add sequential dependency (each task depends on previous)
            if i > 0:
                subtask.dependencies = [f"t-{i}"]
            subtasks.append(subtask)

        # If all tasks are independent (no sequential keywords), remove dependencies
        if not self._is_sequential(goal):
            for subtask in subtasks:
                subtask.dependencies = []

        logger.info(
            "Decomposed goal into %d subtasks: %s",
            len(subtasks),
            [s.task_type for s in subtasks],
        )
        return subtasks

    def _split_goal(self, goal: str) -> list[str]:
        """Split a goal into fragments at conjunction boundaries."""
        # Don't split very short goals
        if len(goal.split()) < 6:
            return [goal]

        # Try splitting at conjunctions
        pattern = "|".join(self._SPLIT_PATTERNS)
        parts = re.split(pattern, goal, flags=re.IGNORECASE)

        # Filter out empty/very short fragments
        return [p.strip() for p in parts if p and len(p.strip()) > 3]

    def _detect_type(self, text: str) -> str:
        """Detect the task type from text."""
        text_lower = text.lower()
        for keywords, task_type in self._TYPE_RULES:
            for kw in keywords:
                if kw in text_lower:
                    return task_type
        return "desktop"

    def _is_sequential(self, goal: str) -> bool:
        """Check if the goal implies sequential execution."""
        sequential_markers = ["then", "after that", "followed by", "next"]
        goal_lower = goal.lower()
        return any(marker in goal_lower for marker in sequential_markers)
