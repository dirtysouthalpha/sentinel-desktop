"""
Sentinel Desktop — Workflow Builder.
Chain actions into reusable, ordered workflows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class WorkflowStatus(str, Enum):
    """Lifecycle status of a workflow (draft, active, running, etc.)."""

    DRAFT = "draft"
    ACTIVE = "active"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, Enum):
    """Execution status of a single workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class WorkflowStep:
    """A single executable step within a builder workflow.

    Each step represents one action (click, type, script, etc.) with
    optional timeout, retries, and conditional execution.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    timeout: int = 30  # seconds
    retry_count: int = 0
    max_retries: int = 2
    condition: str | None = None  # Python expression for conditional execution
    on_failure: str = "stop"  # stop | skip | continue
    status: StepStatus = StepStatus.PENDING
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize step to a JSON-friendly dictionary.

        Returns:
            Dict containing step id, name, action, params, timeout,
            max_retries, condition, on_failure policy, status, and error.
        """
        return {
            "id": self.id,
            "name": self.name,
            "action": self.action,
            "params": self.params,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "condition": self.condition,
            "on_failure": self.on_failure,
            "status": self.status.value,
            "error": self.error,
        }


@dataclass
class Workflow:
    """A named, ordered collection of workflow steps with lifecycle tracking.

    Supports CRUD operations on steps, serialization to/from dicts,
    and duplication for templating.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Workflow"
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.DRAFT
    variables: dict[str, Any] = field(default_factory=dict)
    current_step_index: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: datetime | None = None
    run_count: int = 0

    def add_step(
        self,
        action: str,
        name: str = "",
        params: dict | None = None,
        **kwargs,
    ) -> WorkflowStep:
        """Append a new step to the end of the workflow.

        Args:
            action: Action type identifier (e.g. ``"click"``, ``"type_text"``).
            name: Human-readable step label. Defaults to *action*.
            params: Keyword arguments forwarded to the action executor.
            **kwargs: Additional WorkflowStep fields (timeout, max_retries, etc.).

        Returns:
            The newly created and appended WorkflowStep.
        """
        step = WorkflowStep(
            name=name or action,
            action=action,
            params=params or {},
            **kwargs,
        )
        self.steps.append(step)
        self.updated_at = datetime.now(timezone.utc)
        return step

    def insert_step(self, index: int, action: str, name: str = "", **kwargs) -> WorkflowStep:
        """Insert a new step at a specific position in the workflow.

        Args:
            index: Zero-based insertion position.
            action: Action type identifier.
            name: Human-readable step label. Defaults to *action*.
            **kwargs: Additional WorkflowStep fields.

        Returns:
            The newly created and inserted WorkflowStep.
        """
        step = WorkflowStep(name=name or action, action=action, **kwargs)
        self.steps.insert(index, step)
        self.updated_at = datetime.now(timezone.utc)
        return step

    def remove_step(self, step_id: str) -> bool:
        """Remove a step from the workflow by its ID.

        Args:
            step_id: UUID of the step to remove.

        Returns:
            True if a step was removed, False if no matching step was found.
        """
        before = len(self.steps)
        self.steps = [s for s in self.steps if s.id != step_id]
        if len(self.steps) < before:
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def reorder_steps(self, step_ids: list[str]) -> None:
        """Reorder workflow steps to match the given list of step IDs.

        Steps whose IDs are not present in *step_ids* are dropped.
        Updates the workflow's ``updated_at`` timestamp.

        Args:
            step_ids: Desired step ordering as a list of step UUIDs.
        """
        step_map = {s.id: s for s in self.steps}
        self.steps = [step_map[sid] for sid in step_ids if sid in step_map]
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow and its steps to a JSON-friendly dict.

        Returns:
            Dict with workflow metadata, serialized step list, variables,
            timestamps, and run statistics.
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "variables": self.variables,
            "current_step_index": self.current_step_index,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "run_count": self.run_count,
        }


class WorkflowStore:
    """In-memory workflow store."""

    def __init__(self) -> None:
        self._workflows: dict[str, Workflow] = {}

    def create(self, name: str, description: str = "") -> Workflow:
        """Create a new workflow and register it in the store.

        Args:
            name: Human-readable workflow name.
            description: Optional longer description.

        Returns:
            The newly created Workflow (status set to ACTIVE).
        """
        wf = Workflow(name=name, description=description, status=WorkflowStatus.ACTIVE)
        self._workflows[wf.id] = wf
        return wf

    def get(self, workflow_id: str) -> Workflow | None:
        """Retrieve a workflow by ID.

        Args:
            workflow_id: UUID of the workflow.

        Returns:
            The matching Workflow, or None if not found.
        """
        return self._workflows.get(workflow_id)

    def list_all(self) -> list[Workflow]:
        """Return all workflows in the store.

        Returns:
            List of all registered Workflow instances.
        """
        return list(self._workflows.values())

    def delete(self, workflow_id: str) -> bool:
        """Remove a workflow from the store.

        Args:
            workflow_id: UUID of the workflow to delete.

        Returns:
            True if the workflow was found and deleted, False otherwise.
        """
        if workflow_id in self._workflows:
            del self._workflows[workflow_id]
            return True
        return False

    def duplicate(self, workflow_id: str, new_name: str | None = None) -> Workflow | None:
        """Deep-copy a workflow with all its steps.

        Args:
            workflow_id: UUID of the source workflow.
            new_name: Optional name for the copy. Defaults to
                ``"<source name> (Copy)"``.

        Returns:
            The newly created duplicate, or None if the source was not found.
        """
        source = self._workflows.get(workflow_id)
        if not source:
            return None
        new_wf = self.create(
            name=new_name or f"{source.name} (Copy)",
            description=source.description,
        )
        for step in source.steps:
            new_wf.add_step(
                action=step.action,
                name=step.name,
                params=step.params.copy(),
                timeout=step.timeout,
                max_retries=step.max_retries,
                condition=step.condition,
                on_failure=step.on_failure,
            )
        return new_wf


# ─── Pre-built workflow templates ────────────────────────────────────────

TEMPLATES: dict[str, dict] = {
    "daily_standup": {
        "name": "Daily Standup Prep",
        "description": "Open Slack, email, and calendar for morning standup",
        "steps": [
            {"action": "launch_app", "name": "Open Slack", "params": {"app": "slack"}},
            {"action": "wait", "name": "Wait for Slack", "params": {"seconds": 3}},
            {"action": "launch_app", "name": "Open Outlook", "params": {"app": "outlook"}},
            {"action": "wait", "name": "Wait for Outlook", "params": {"seconds": 3}},
            {"action": "launch_app", "name": "Open Teams", "params": {"app": "teams"}},
        ],
    },
    "incident_response": {
        "name": "Incident Response",
        "description": "Standard IT incident triage workflow",
        "steps": [
            {"action": "screenshot", "name": "Capture current state", "params": {}},
            {
                "action": "launch_app",
                "name": "Open Ticketing System",
                "params": {"app": "chrome", "url": "https://servicedesk"},
            },
            {"action": "type_text", "name": "Search ticket", "params": {"text": "{ticket_id}"}},
            {"action": "screenshot", "name": "Document ticket state", "params": {}},
        ],
    },
    "password_reset": {
        "name": "Password Reset",
        "description": "Guide user through password reset",
        "steps": [
            {"action": "launch_app", "name": "Open ADUC", "params": {"app": "dsa.msc"}},
            {"action": "type_text", "name": "Search user", "params": {"text": "{username}"}},
            {"action": "click", "name": "Reset Password", "params": {"text": "Reset Password"}},
            {"action": "type_text", "name": "New password", "params": {"text": "{new_password}"}},
            {"action": "click", "name": "Confirm", "params": {"text": "OK"}},
            {"action": "screenshot", "name": "Document completion", "params": {}},
        ],
    },
    "new_user_onboard": {
        "name": "New User Onboarding",
        "description": "Standard new hire setup workflow",
        "steps": [
            {"action": "launch_app", "name": "Open ADUC", "params": {"app": "dsa.msc"}},
            {"action": "click", "name": "Create new user", "params": {"text": "New User"}},
            {"action": "type_text", "name": "Enter name", "params": {"text": "{full_name}"}},
            {"action": "type_text", "name": "Enter username", "params": {"text": "{username}"}},
            {"action": "type_text", "name": "Set temp password", "params": {"text": "{temp_password}"}},
            {"action": "click", "name": "Create", "params": {"text": "OK"}},
            {
                "action": "launch_app",
                "name": "Open email admin",
                "params": {"app": "chrome", "url": "https://admin.microsoft.com"},
            },
        ],
    },
}


# Singleton
workflow_store = WorkflowStore()
