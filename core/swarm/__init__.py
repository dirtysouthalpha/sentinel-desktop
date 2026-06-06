"""Sentinel Desktop v7.0 — Swarm Orchestration.

Multi-agent system where an orchestrator decomposes complex goals into
subtasks and assigns them to specialist agents. Agents communicate through
a shared message bus backed by SQLite + asyncio queues.

Specialist agent types:
    - BrowserAgent: Web automation (Chrome Extension bridge)
    - TerminalAgent: Shell/SSH command execution
    - MonitorAgent: Passive monitoring and alert detection
    - DesktopAgent: General desktop interaction (default)

Usage::

    from core.swarm import SwarmOrchestrator

    swarm = SwarmOrchestrator()
    result = swarm.execute("Configure the firewall and check logs")
"""

from core.swarm.bus import AgentMessage, MessageBus
from core.swarm.orchestrator import SwarmOrchestrator
from core.swarm.registry import AgentRegistry
from core.swarm.specialist import AgentRole, SpecialistAgent

__all__ = [
    "SwarmOrchestrator",
    "MessageBus",
    "AgentMessage",
    "SpecialistAgent",
    "AgentRole",
    "AgentRegistry",
]
