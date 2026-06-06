"""Sentinel Desktop v7.0 — Agent Registry.

Tracks all active agents, their capabilities, and health status.
Provides lookup by role and capability matching for task assignment.
"""

from __future__ import annotations

import logging
from typing import Any

from core.swarm.specialist import AgentRole, AgentState, SpecialistAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry of active agents with health tracking.

    Usage::

        registry = AgentRegistry()
        registry.register(agent)
        available = registry.find_by_role(AgentRole.DESKTOP)
    """

    def __init__(self) -> None:
        self._agents: dict[str, SpecialistAgent] = {}

    def register(self, agent: SpecialistAgent) -> None:
        """Register an agent."""
        self._agents[agent.agent_id] = agent
        logger.info("Registered agent %s (%s)", agent.agent_id, agent.role.value)

    def unregister(self, agent_id: str) -> None:
        """Remove an agent from the registry."""
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> SpecialistAgent | None:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def find_by_role(self, role: AgentRole) -> list[SpecialistAgent]:
        """Find all agents with a specific role that are idle."""
        return [
            a for a in self._agents.values()
            if a.role == role and a.state == AgentState.IDLE
        ]

    def find_available(self) -> list[SpecialistAgent]:
        """Find all idle agents."""
        return [a for a in self._agents.values() if a.state == AgentState.IDLE]

    def find_for_task(self, task_type: str) -> SpecialistAgent | None:
        """Find the best agent for a task type.

        Task type to role mapping:
            click, type, scroll, screenshot → DESKTOP
            shell, ssh, command → TERMINAL
            browser, web, navigate → BROWSER
            monitor, watch, alert → MONITOR
        """
        role_map = {
            "click": AgentRole.DESKTOP,
            "type": AgentRole.DESKTOP,
            "scroll": AgentRole.DESKTOP,
            "screenshot": AgentRole.DESKTOP,
            "desktop": AgentRole.DESKTOP,
            "shell": AgentRole.TERMINAL,
            "ssh": AgentRole.TERMINAL,
            "command": AgentRole.TERMINAL,
            "terminal": AgentRole.TERMINAL,
            "browser": AgentRole.BROWSER,
            "web": AgentRole.BROWSER,
            "navigate": AgentRole.BROWSER,
            "monitor": AgentRole.MONITOR,
            "watch": AgentRole.MONITOR,
            "alert": AgentRole.MONITOR,
        }

        role = role_map.get(task_type.lower())
        if role is None:
            # Default to desktop for unknown task types
            role = AgentRole.DESKTOP

        agents = self.find_by_role(role)
        if not agents:
            # Fallback: try any available desktop agent
            agents = self.find_by_role(AgentRole.DESKTOP)
        if not agents:
            # Last resort: any available agent
            agents = self.find_available()

        return agents[0] if agents else None

    @property
    def all_agents(self) -> list[dict[str, Any]]:
        """Return status of all registered agents."""
        return [a.to_dict() for a in self._agents.values()]

    @property
    def count(self) -> int:
        return len(self._agents)

    @property
    def healthy_count(self) -> int:
        return sum(1 for a in self._agents.values() if a.state != AgentState.ERROR)
