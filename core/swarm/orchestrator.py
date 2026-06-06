"""Sentinel Desktop v7.0 — Swarm Orchestrator.

Decomposes complex goals into subtasks, assigns them to specialist agents,
and monitors progress. Coordinates multiple agents working in parallel.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.swarm.bus import AgentMessage, MessageBus
from core.swarm.registry import AgentRegistry
from core.swarm.specialist import (
    DesktopAgent,
    MonitorAgent,
    SpecialistAgent,
    TerminalAgent,
)

logger = logging.getLogger(__name__)


class SwarmOrchestrator:
    """Orchestrates multi-agent task execution.

    Usage::

        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        result = swarm.execute("Configure the firewall and check logs")
    """

    def __init__(self, bus: MessageBus | None = None) -> None:
        self.bus = bus or MessageBus()
        self.registry = AgentRegistry()
        self._results: list[dict[str, Any]] = []

    def add_agent(self, agent: SpecialistAgent) -> None:
        """Register a specialist agent."""
        self.registry.register(agent)

    def add_default_agents(self) -> None:
        """Add the standard set of specialist agents."""
        self.add_agent(DesktopAgent(self.bus, "desktop-1"))
        self.add_agent(TerminalAgent(self.bus, "terminal-1"))
        self.add_agent(MonitorAgent(self.bus, "monitor-1"))

    async def execute(
        self,
        goal: str,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Execute a goal by decomposing and delegating to agents.

        Args:
            goal: The user's goal in plain English.
            timeout: Maximum seconds to wait for completion.

        Returns:
            Result dict with status, subtasks, and agent results.
        """
        start = time.monotonic()
        self._results.clear()

        # Decompose the goal into subtasks
        subtasks = self._decompose(goal)

        # Assign and execute each subtask
        for i, subtask in enumerate(subtasks):
            if time.monotonic() - start > timeout:
                logger.warning("Swarm execution timed out after %.1fs", timeout)
                break

            agent = self.registry.find_for_task(subtask.get("type", "desktop"))
            if agent is None:
                self._results.append(
                    {
                        "subtask": subtask,
                        "status": "no_agent",
                        "error": "No available agent for this task",
                    }
                )
                continue

            # Send task to agent
            await self.bus.send(
                AgentMessage(
                    sender="orchestrator",
                    recipient=agent.agent_id,
                    msg_type="task",
                    payload={**subtask, "goal": goal, "step": i + 1},
                )
            )

            # Wait for result
            result_msg = await self.bus.receive("orchestrator", timeout=30.0)
            if result_msg:
                self._results.append(
                    {
                        "subtask": subtask,
                        "agent": result_msg.payload.get("agent_id", "unknown"),
                        "status": "success" if result_msg.payload.get("success") else "failed",
                        "result": result_msg.payload,
                    }
                )
            else:
                self._results.append(
                    {
                        "subtask": subtask,
                        "agent": agent.agent_id,
                        "status": "timeout",
                    }
                )

        elapsed = (time.monotonic() - start) * 1000
        successes = sum(1 for r in self._results if r.get("status") == "success")

        return {
            "goal": goal,
            "status": "completed" if successes == len(subtasks) else "partial",
            "subtasks_total": len(subtasks),
            "subtasks_completed": successes,
            "subtasks_failed": len(self._results) - successes,
            "elapsed_ms": round(elapsed, 1),
            "agents_used": list(set(r.get("agent", "none") for r in self._results)),
            "results": self._results,
        }

    @staticmethod
    def _decompose(goal: str) -> list[dict[str, Any]]:
        """Decompose a goal into subtasks (rule-based for v7.0).

        Uses keyword detection to identify task types. In v8.0, the planner
        will handle this with LLM-powered decomposition.
        """
        subtasks: list[dict[str, Any]] = []
        goal_lower = goal.lower()

        # Detect terminal tasks
        terminal_keywords = [
            "configure",
            "install",
            "run ",
            "execute",
            "command",
            "ssh",
            "powershell",
            "bash",
            "script",
        ]
        for kw in terminal_keywords:
            if kw in goal_lower:
                subtasks.append(
                    {
                        "type": "terminal",
                        "description": goal,
                        "command": goal,
                    }
                )
                break

        # Detect browser tasks
        browser_keywords = [
            "browser",
            "website",
            "web ",
            "navigate",
            "open ",
            "download",
            "portal",
            "login",
        ]
        for kw in browser_keywords:
            if kw in goal_lower:
                subtasks.append(
                    {
                        "type": "browser",
                        "description": goal,
                    }
                )
                break

        # Detect monitor tasks
        monitor_keywords = ["monitor", "watch", "alert", "check ", "verify", "status", "health"]
        for kw in monitor_keywords:
            if kw in goal_lower:
                subtasks.append(
                    {
                        "type": "monitor",
                        "description": goal,
                    }
                )
                break

        # If no specific type detected, create a desktop task
        if not subtasks:
            subtasks.append(
                {
                    "type": "desktop",
                    "description": goal,
                }
            )

        return subtasks

    def status(self) -> dict[str, Any]:
        """Return current swarm status."""
        return {
            "agents": self.registry.all_agents,
            "agent_count": self.registry.count,
            "healthy": self.registry.healthy_count,
            "bus_agents": self.bus.registered_agents,
        }
