"""Sentinel Desktop v7.0 — Specialist Agent Base.

Base class for all specialist agents. Each agent type has a specific
domain of expertise and can process tasks independently.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from core.swarm.bus import AgentMessage, MessageBus

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Specialist agent roles."""

    DESKTOP = "desktop"  # General desktop interaction (default)
    BROWSER = "browser"  # Web automation
    TERMINAL = "terminal"  # Shell/SSH execution
    MONITOR = "monitor"  # Passive monitoring
    ORCHESTRATOR = "orchestrator"  # Task decomposition


class AgentState(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    ERROR = "error"
    STOPPED = "stopped"


class SpecialistAgent(ABC):
    """Base class for specialist agents.

    Subclasses implement `process_task()` to handle their specific domain.

    Attributes:
        agent_id: Unique identifier for this agent.
        role: The agent's specialist role.
        state: Current agent state.
        bus: The shared message bus.
        task_count: Number of tasks completed.
    """

    def __init__(
        self,
        agent_id: str,
        role: AgentRole,
        bus: MessageBus,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.state = AgentState.IDLE
        self.bus = bus
        self.task_count = 0
        self.error_count = 0
        self._queue = bus.register(agent_id)
        self.bus.subscribe(agent_id, "task")
        self.bus.subscribe(agent_id, "control")

    @abstractmethod
    async def process_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Process a single task. Subclasses must implement this.

        Args:
            task: Task specification with 'description', 'type', etc.

        Returns:
            Result dict with 'success', 'output', etc.
        """
        ...

    async def run_once(self, timeout: float = 1.0) -> dict[str, Any] | None:
        """Run one processing cycle: receive a task, process it, send result.

        Returns the result dict or None if no task was received.
        """
        message = await self.bus.receive(self.agent_id, timeout=timeout)
        if message is None:
            return None

        if message.msg_type == "control":
            cmd = message.payload.get("command")
            if cmd == "stop":
                self.state = AgentState.STOPPED
                return {"success": True, "output": "Agent stopped"}
            return None

        if message.msg_type != "task":
            return None

        self.state = AgentState.WORKING
        task = message.payload
        start = time.monotonic()

        try:
            result = await self.process_task(task)
            elapsed = (time.monotonic() - start) * 1000
            result["elapsed_ms"] = round(elapsed, 1)
            result["agent_id"] = self.agent_id
            self.task_count += 1

            # Send result back
            await self.bus.send(
                AgentMessage(
                    sender=self.agent_id,
                    recipient=message.sender or "orchestrator",
                    msg_type="result",
                    payload=result,
                    parent_id=message.id,
                )
            )

            self.state = AgentState.IDLE
            return result

        except Exception as exc:
            self.error_count += 1
            self.state = AgentState.ERROR
            logger.error("Agent %s task failed: %s", self.agent_id, exc)

            error_result = {
                "success": False,
                "error": str(exc),
                "agent_id": self.agent_id,
            }
            await self.bus.send(
                AgentMessage(
                    sender=self.agent_id,
                    recipient=message.sender or "orchestrator",
                    msg_type="error",
                    payload=error_result,
                    parent_id=message.id,
                )
            )
            return error_result

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.agent_id,
            "role": self.role.value,
            "state": self.state.value,
            "tasks_completed": self.task_count,
            "errors": self.error_count,
        }


class DesktopAgent(SpecialistAgent):
    """General desktop interaction agent — handles clicks, typing, screenshots."""

    def __init__(self, bus: MessageBus, agent_id: str = "desktop-1") -> None:
        super().__init__(agent_id, AgentRole.DESKTOP, bus)

    async def process_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a desktop action via the existing action executor."""
        action = task.get("action", {})
        # In production, this would call the real executor
        return {"success": True, "output": f"Executed: {action.get('action', 'unknown')}"}


class TerminalAgent(SpecialistAgent):
    """Terminal/SSH command execution agent."""

    def __init__(self, bus: MessageBus, agent_id: str = "terminal-1") -> None:
        super().__init__(agent_id, AgentRole.TERMINAL, bus)

    async def process_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a shell command."""
        command = task.get("command", task.get("description", ""))
        from core.platform import get_backend

        backend = get_backend()
        result = backend.shell.execute(command)
        return {"success": result["exit_code"] == 0, "output": result}


class MonitorAgent(SpecialistAgent):
    """Passive monitoring agent — watches for alerts, state changes."""

    def __init__(self, bus: MessageBus, agent_id: str = "monitor-1") -> None:
        super().__init__(agent_id, AgentRole.MONITOR, bus)

    async def process_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Check a monitoring condition."""
        check_type = task.get("check", "screenshot")
        return {"success": True, "output": f"Monitor check: {check_type}", "status": "ok"}
