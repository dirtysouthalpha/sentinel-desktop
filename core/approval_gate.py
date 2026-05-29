"""
Sentinel Desktop v2 — Approval gate for agent actions.

When approval mode is enabled, the agent pauses before executing each
action and presents a preview card to the user. The user can approve,
modify, skip, or abort. This is the desktop equivalent of Sentinel
Override's approval-gated mode.

Works with both the GUI (approval cards in chat) and the API (webhook
callback or polling).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ApprovalDecision(Enum):
    """User decision on a pending agent action in approval mode."""

    APPROVE = "approve"
    MODIFY = "modify"  # user changed params before approving
    SKIP = "skip"  # skip this action, continue agent loop
    ABORT = "abort"  # stop the entire run


class ApprovalRequest:
    """Represents a pending action awaiting user approval."""

    def __init__(self, action: dict[str, Any], step_num: int) -> None:
        """Initialize a pending approval request.

        Args:
            action: The action dict awaiting user approval.
            step_num: The agent step number that generated this request.
        """
        self.action = action
        self.step_num = step_num
        self.decision: ApprovalDecision | None = None
        self.modified_action: dict[str, Any] | None = None
        self._event = threading.Event()

    def wait(self, timeout: float = 300) -> bool:
        """Block until the user responds or timeout. Returns True if decided."""
        return self._event.wait(timeout=timeout)

    def respond(
        self, decision: ApprovalDecision, modified_action: dict[str, Any] | None = None
    ) -> None:
        """Called by the UI/API to submit the user's decision."""
        self.decision = decision
        self.modified_action = modified_action
        self._event.set()

    @property
    def resolved(self) -> bool:
        """Return True if the user has responded to this request."""
        return self._event.is_set()


class ApprovalGate:
    """
    Gate that intercepts actions before execution when approval mode is on.

    Usage:
        gate = ApprovalGate(enabled=True)
        ...
        # In agent loop:
        decision, action = gate.evaluate(action, step_num)
        if decision == ApprovalDecision.APPROVE:
            executor.execute(action)
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize the approval gate.

        Args:
            enabled: When ``True`` the gate will block and request user approval
                before each action. When ``False`` all actions pass through.
        """
        self.enabled = enabled
        self._callback: Callable[[ApprovalRequest], None] | None = None
        self._current_request: ApprovalRequest | None = None
        self._stats = {"approved": 0, "skipped": 0, "modified": 0, "aborted": 0}

    def set_callback(self, callback: Callable[[ApprovalRequest], None]) -> None:
        """Set a callback to notify the UI when a request is pending."""
        self._callback = callback

    def evaluate(
        self, action: dict[str, Any], step_num: int
    ) -> tuple[ApprovalDecision, dict[str, Any] | None]:
        """
        Evaluate an action through the approval gate.

        Returns (decision, action_to_execute).
        If approval mode is off, returns (APPROVE, original_action).
        If approval mode is on, blocks until user responds.
        """
        if not self.enabled:
            return ApprovalDecision.APPROVE, action

        # Auto-approve safe read-only actions
        safe_actions = {
            "screenshot",
            "wait",
            "read_text",
            "list_controls",
            "find_element",
            "get_element_bounds",
            "brief_system_info",
        }
        if action.get("action") in safe_actions:
            return ApprovalDecision.APPROVE, action

        # Create request and notify UI
        request = ApprovalRequest(action, step_num)
        self._current_request = request

        if self._callback:
            try:
                self._callback(request)
            except (RuntimeError, OSError, ValueError) as exc:
                logger.warning("Approval callback error: %s — auto-approving", exc)
                self._current_request = None
                return ApprovalDecision.APPROVE, action

        # Block until user responds
        if not request.wait(timeout=300):
            # Timeout — auto-approve with warning
            logger.warning("Approval timeout at step %d — auto-approving", step_num)
            self._current_request = None
            return ApprovalDecision.APPROVE, action

        self._current_request = None
        return self._process_decision(request, action)

    def _process_decision(
        self, request: ApprovalRequest, action: dict[str, Any]
    ) -> tuple[ApprovalDecision, dict[str, Any] | None]:
        """Tally stats and return the (decision, action) tuple."""
        decision = request.decision or ApprovalDecision.APPROVE

        if decision == ApprovalDecision.APPROVE:
            self._stats["approved"] += 1
            return decision, action
        if decision == ApprovalDecision.MODIFY:
            self._stats["modified"] += 1
            return decision, request.modified_action or action
        if decision == ApprovalDecision.SKIP:
            self._stats["skipped"] += 1
            return decision, None
        if decision == ApprovalDecision.ABORT:
            self._stats["aborted"] += 1
            return decision, None
        return ApprovalDecision.APPROVE, action

    def respond_current(
        self, decision: ApprovalDecision, modified_action: dict[str, Any] | None = None
    ) -> None:
        """Respond to the currently pending request (for API use)."""
        if self._current_request and not self._current_request.resolved:
            self._current_request.respond(decision, modified_action)

    @property
    def pending_request(self) -> ApprovalRequest | None:
        """Return the currently pending approval request, if any."""
        return self._current_request

    def get_stats(self) -> dict[str, int]:
        """Return a copy of the approval statistics counters."""
        return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset all approval statistics counters to zero."""
        self._stats = {"approved": 0, "skipped": 0, "modified": 0, "aborted": 0}
