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
    DRAFT = "draft"
    ACTIVE = "active"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class WorkflowStep:
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
        step = WorkflowStep(name=name or action, action=action, **kwargs)
        self.steps.insert(index, step)
        self.updated_at = datetime.now(timezone.utc)
        return step

    def remove_step(self, step_id: str) -> bool:
        before = len(self.steps)
        self.steps = [s for s in self.steps if s.id != step_id]
        if len(self.steps) < before:
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def reorder_steps(self, step_ids: list[str]) -> None:
        step_map = {s.id: s for s in self.steps}
        self.steps = [step_map[sid] for sid in step_ids if sid in step_map]
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
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
        wf = Workflow(name=name, description=description, status=WorkflowStatus.ACTIVE)
        self._workflows[wf.id] = wf
        return wf

    def get(self, workflow_id: str) -> Workflow | None:
        return self._workflows.get(workflow_id)

    def list_all(self) -> list[Workflow]:
        return list(self._workflows.values())

    def delete(self, workflow_id: str) -> bool:
        if workflow_id in self._workflows:
            del self._workflows[workflow_id]
            return True
        return False

    def duplicate(self, workflow_id: str, new_name: str | None = None) -> Workflow | None:
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
            {"action": "launch_app", "name": "Open Ticketing System", "params": {"app": "chrome", "url": "https://servicedesk"}},
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
            {"action": "launch_app", "name": "Open email admin", "params": {"app": "chrome", "url": "https://admin.microsoft.com"}},
        ],
    },
}


# Singleton
workflow_store = WorkflowStore()
