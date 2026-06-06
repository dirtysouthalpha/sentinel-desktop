"""Tests for Sentinel Desktop v7.0 Swarm and v8.0 Autonomous Memory."""

from __future__ import annotations

import pytest

from core.swarm.bus import AgentMessage, MessageBus, MessagePriority
from core.swarm.orchestrator import SwarmOrchestrator
from core.swarm.registry import AgentRegistry
from core.swarm.specialist import AgentRole, AgentState, DesktopAgent, TerminalAgent

# ── v7.0 Swarm Tests ─────────────────────────────────────────────────────


class TestMessageBus:
    def test_register_and_list(self):
        bus = MessageBus()
        bus.register("agent-1")
        assert "agent-1" in bus.registered_agents

    def test_unregister(self):
        bus = MessageBus()
        bus.register("agent-1")
        bus.unregister("agent-1")
        assert "agent-1" not in bus.registered_agents

    @pytest.mark.asyncio
    async def test_send_and_receive(self):
        bus = MessageBus()
        bus.register("agent-1")
        bus.subscribe("agent-1", "task")
        msg = AgentMessage(sender="boss", recipient="broadcast", msg_type="task", payload={"action": "click"})
        count = await bus.send(msg)
        assert count == 1
        received = await bus.receive("agent-1", timeout=1.0)
        assert received is not None
        assert received.payload["action"] == "click"

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple(self):
        bus = MessageBus()
        bus.register("a1")
        bus.register("a2")
        bus.subscribe("a1", "task")
        bus.subscribe("a2", "task")
        msg = AgentMessage(sender="boss", msg_type="task", payload={"x": 1})
        count = await bus.send(msg)
        assert count == 2

    @pytest.mark.asyncio
    async def test_direct_message(self):
        bus = MessageBus()
        bus.register("a1")
        msg = AgentMessage(sender="boss", recipient="a1", msg_type="task", payload={"do": "thing"})
        count = await bus.send(msg)
        assert count == 1

    @pytest.mark.asyncio
    async def test_receive_timeout(self):
        bus = MessageBus()
        bus.register("a1")
        result = await bus.receive("a1", timeout=0.1)
        assert result is None

    def test_history(self):
        bus = MessageBus()
        bus.register("a1")
        msg = AgentMessage(sender="test", payload={"v": 1})
        bus._history.append(msg)
        assert len(bus.history) == 1

    def test_clear(self):
        bus = MessageBus()
        bus.register("a1")
        bus.clear()
        assert len(bus.registered_agents) == 0
        assert len(bus.history) == 0


class TestAgentMessage:
    def test_default_values(self):
        msg = AgentMessage()
        assert msg.recipient == "broadcast"
        assert msg.priority == MessagePriority.NORMAL
        assert msg.sender == ""

    def test_to_dict(self):
        msg = AgentMessage(sender="a1", msg_type="result", payload={"ok": True})
        d = msg.to_dict()
        assert d["sender"] == "a1"
        assert d["type"] == "result"
        assert d["payload"]["ok"] is True


class TestSpecialistAgent:
    def test_desktop_agent_creation(self):
        bus = MessageBus()
        agent = DesktopAgent(bus, "desk-1")
        assert agent.agent_id == "desk-1"
        assert agent.role == AgentRole.DESKTOP
        assert agent.state == AgentState.IDLE

    def test_to_dict(self):
        bus = MessageBus()
        agent = DesktopAgent(bus)
        d = agent.to_dict()
        assert d["role"] == "desktop"
        assert d["state"] == "idle"

    @pytest.mark.asyncio
    async def test_process_task(self):
        bus = MessageBus()
        agent = DesktopAgent(bus)
        result = await agent.process_task({"action": {"action": "click", "x": 100, "y": 200}})
        assert result["success"] is True


class TestAgentRegistry:
    def test_register_and_find(self):
        bus = MessageBus()
        registry = AgentRegistry()
        agent = DesktopAgent(bus)
        registry.register(agent)
        found = registry.find_by_role(AgentRole.DESKTOP)
        assert len(found) == 1

    def test_find_for_task(self):
        bus = MessageBus()
        registry = AgentRegistry()
        registry.register(DesktopAgent(bus))
        registry.register(TerminalAgent(bus))
        agent = registry.find_for_task("shell")
        assert agent is not None
        assert agent.role == AgentRole.TERMINAL

    def test_find_for_unknown_defaults_to_desktop(self):
        bus = MessageBus()
        registry = AgentRegistry()
        registry.register(DesktopAgent(bus))
        agent = registry.find_for_task("unknown_thing")
        assert agent.role == AgentRole.DESKTOP

    def test_no_available_returns_none(self):
        registry = AgentRegistry()
        assert registry.find_for_task("click") is None

    def test_count(self):
        bus = MessageBus()
        registry = AgentRegistry()
        registry.register(DesktopAgent(bus))
        registry.register(TerminalAgent(bus))
        assert registry.count == 2


class TestSwarmOrchestrator:
    def test_decompose_terminal(self):
        tasks = SwarmOrchestrator._decompose("Configure the firewall rules")
        assert any(t["type"] == "terminal" for t in tasks)

    def test_decompose_browser(self):
        tasks = SwarmOrchestrator._decompose("Navigate to the admin portal")
        assert any(t["type"] == "browser" for t in tasks)

    def test_decompose_monitor(self):
        tasks = SwarmOrchestrator._decompose("Monitor the system health")
        assert any(t["type"] == "monitor" for t in tasks)

    def test_decompose_default(self):
        tasks = SwarmOrchestrator._decompose("Click the save button")
        assert len(tasks) >= 1
        assert tasks[0]["type"] == "desktop"

    def test_status(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        status = swarm.status()
        assert status["agent_count"] == 3
        assert status["healthy"] == 3
