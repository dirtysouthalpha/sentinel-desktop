"""
Sentinel Desktop v30.0.0 - Multi-Agent Swarm Orchestration.

Coordinate multiple AgentEngine instances on parallel tasks
with a shared message bus and dependency tracking.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SwarmTask:
    """A task assigned to a swarm agent."""
    id: str
    goal: str
    agent_id: str = ""
    status: str = "pending"  # pending, running, completed, failed
    result: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def is_ready(self) -> bool:
        """True when all dependencies are completed."""
        return self.status == "pending"

    @property
    def elapsed(self) -> float:
        """Elapsed time since start."""
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        if self.started_at:
            return time.time() - self.started_at
        return 0.0


@dataclass
class SwarmAgent:
    """An agent in the swarm."""
    id: str
    name: str = ""
    status: str = "idle"  # idle, running, stopped
    current_task: str = ""
    tasks_completed: int = 0


@dataclass
class Swarm:
    """A coordinated group of agents working on related tasks."""
    id: str
    name: str
    agents: dict[str, SwarmAgent] = field(default_factory=dict)
    tasks: dict[str, SwarmTask] = field(default_factory=dict)
    message_bus: deque = field(default_factory=lambda: deque(maxlen=100))
    created_at: float = field(default_factory=time.time)
    status: str = "active"  # active, stopped

    def add_task(self, goal: str, depends_on: list[str] | None = None) -> str:
        """Add a task to the swarm."""
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = SwarmTask(
            id=task_id,
            goal=goal,
            depends_on=depends_on or [],
        )
        self.message_bus.append({"type": "task_added", "task_id": task_id, "goal": goal})
        return task_id

    def get_status(self) -> dict[str, Any]:
        """Get swarm status summary."""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status == "completed")
        failed = sum(1 for t in self.tasks.values() if t.status == "failed")
        running = sum(1 for t in self.tasks.values() if t.status == "running")
        pending = sum(1 for t in self.tasks.values() if t.status == "pending")
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "agents": len(self.agents),
            "tasks": {"total": total, "completed": completed, "failed": failed, "running": running, "pending": pending},
            "messages": len(self.message_bus),
            "uptime_seconds": round(time.time() - self.created_at, 1),
        }


# ── Swarm Manager ──────────────────────────────────────────────

class SwarmManager:
    """Manages multiple swarms."""

    def __init__(self) -> None:
        self._swarms: dict[str, Swarm] = {}
        self._lock = threading.Lock()

    def create_swarm(self, name: str, agent_count: int = 3) -> Swarm:
        """Create a new swarm with N agents."""
        swarm_id = str(uuid.uuid4())[:8]
        swarm = Swarm(id=swarm_id, name=name)
        for i in range(agent_count):
            agent_id = f"agent-{i+1}"
            swarm.agents[agent_id] = SwarmAgent(id=agent_id, name=f"Agent {i+1}")
        with self._lock:
            self._swarms[swarm_id] = swarm
        logger.info("Created swarm '%s' with %d agents", name, agent_count)
        return swarm

    def get_swarm(self, swarm_id: str) -> Swarm | None:
        """Get a swarm by ID."""
        return self._swarms.get(swarm_id)

    def assign_task(self, swarm_id: str, goal: str, depends_on: list[str] | None = None) -> dict[str, Any]:
        """Assign a task to a swarm."""
        swarm = self._swarms.get(swarm_id)
        if not swarm:
            return {"success": False, "message": f"Swarm '{swarm_id}' not found"}
        task_id = swarm.add_task(goal, depends_on)
        # Assign to first idle agent
        for agent_id, agent in swarm.agents.items():
            if agent.status == "idle":
                agent.status = "assigned"
                agent.current_task = task_id
                swarm.tasks[task_id].agent_id = agent_id
                swarm.tasks[task_id].status = "running"
                swarm.tasks[task_id].started_at = time.time()
                swarm.message_bus.append({"type": "task_assigned", "task_id": task_id, "agent_id": agent_id})
                break
        return {"success": True, "task_id": task_id, "swarm_id": swarm_id}

    def complete_task(self, swarm_id: str, task_id: str, result: dict[str, Any]) -> dict[str, Any]:
        """Mark a task as completed."""
        swarm = self._swarms.get(swarm_id)
        if not swarm or task_id not in swarm.tasks:
            return {"success": False, "message": "Task not found"}
        task = swarm.tasks[task_id]
        task.status = "completed"
        task.result = result
        task.finished_at = time.time()
        # Free the agent
        if task.agent_id and task.agent_id in swarm.agents:
            swarm.agents[task.agent_id].status = "idle"
            swarm.agents[task.agent_id].current_task = ""
            swarm.agents[task.agent_id].tasks_completed += 1
        swarm.message_bus.append({"type": "task_completed", "task_id": task_id})
        return {"success": True, "message": f"Task {task_id} completed"}

    def stop_swarm(self, swarm_id: str) -> dict[str, Any]:
        """Stop an entire swarm."""
        swarm = self._swarms.get(swarm_id)
        if not swarm:
            return {"success": False, "message": f"Swarm '{swarm_id}' not found"}
        swarm.status = "stopped"
        for agent in swarm.agents.values():
            agent.status = "stopped"
        for task in swarm.tasks.values():
            if task.status == "running":
                task.status = "failed"
                task.finished_at = time.time()
        swarm.message_bus.append({"type": "swarm_stopped"})
        return {"success": True, "message": f"Swarm '{swarm_id}' stopped"}

    def list_swarms(self) -> list[dict[str, Any]]:
        """List all swarms with status."""
        return [s.get_status() for s in self._swarms.values()]


# Singleton
_manager: SwarmManager | None = None


def get_manager() -> SwarmManager:
    """Get or create the singleton swarm manager."""
    global _manager
    if _manager is None:
        _manager = SwarmManager()
    return _manager
