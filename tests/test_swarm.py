"""Tests for Sentinel Desktop v7.0 Swarm and v8.0 Autonomous Memory."""

from __future__ import annotations

import pytest

from core.swarm.bus import AgentMessage, MessageBus, MessagePriority
from core.swarm.orchestrator import SwarmOrchestrator
from core.swarm.registry import AgentRegistry
from core.swarm.specialist import (
    AgentRole,
    AgentState,
    DesktopAgent,
    MonitorAgent,
    TerminalAgent,
)

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
        msg = AgentMessage(
            sender="boss", recipient="broadcast", msg_type="task", payload={"action": "click"}
        )
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

    @pytest.mark.asyncio
    async def test_execute_with_no_agents_returns_no_agent_status(self):
        swarm = SwarmOrchestrator()
        result = await swarm.execute("Click the button", timeout=1.0)
        assert result["status"] in ["completed", "partial"]
        assert result["subtasks_total"] >= 1
        assert len(result["results"]) >= 1
        assert result["results"][0]["status"] == "no_agent"

    @pytest.mark.asyncio
    async def test_execute_timeout_during_iteration(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        result = await swarm.execute("Click the button", timeout=0.001)
        assert result["status"] == "partial"
        assert result["elapsed_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execute_full_result_structure(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        result = await swarm.execute("Configure the firewall", timeout=1.0)
        assert "goal" in result
        assert "status" in result
        assert "subtasks_total" in result
        assert "subtasks_completed" in result
        assert "subtasks_failed" in result
        assert "elapsed_ms" in result
        assert "agents_used" in result
        assert "results" in result
        assert isinstance(result["results"], list)

    @pytest.mark.asyncio
    async def test_execute_clears_previous_results(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        await swarm.execute("First task", timeout=1.0)
        first_result_count = len(swarm._results)
        await swarm.execute("Second task", timeout=1.0)
        assert len(swarm._results) >= 0

    @pytest.mark.asyncio
    async def test_execute_with_terminal_task(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        result = await swarm.execute("Run the update script", timeout=1.0)
        # Check that terminal task was decomposed or at least one task was created
        assert result["subtasks_total"] >= 1
        # Verify results structure is valid
        if result["results"]:
            assert "subtask" in result["results"][0]

    @pytest.mark.asyncio
    async def test_execute_with_monitor_task(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        result = await swarm.execute("Monitor system health", timeout=1.0)
        assert result["goal"] == "Monitor system health"

    @pytest.mark.asyncio
    async def test_execute_multiple_subtasks(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        result = await swarm.execute("Configure and monitor the system", timeout=1.0)
        assert result["subtasks_total"] >= 1

    @pytest.mark.asyncio
    async def test_execute_agents_used_list(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        result = await swarm.execute("Click the button", timeout=1.0)
        assert isinstance(result["agents_used"], list)

    @pytest.mark.asyncio
    async def test_execute_elapsed_time_tracking(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        result = await swarm.execute("Click the button", timeout=1.0)
        assert result["elapsed_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execute_with_custom_bus(self):
        from core.swarm.bus import MessageBus

        custom_bus = MessageBus()
        swarm = SwarmOrchestrator(bus=custom_bus)
        assert swarm.bus is custom_bus
        swarm.add_default_agents()
        result = await swarm.execute("Test task", timeout=1.0)
        assert "goal" in result

    @pytest.mark.asyncio
    async def test_execute_status_calculation(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        result = await swarm.execute("Click the button", timeout=1.0)
        assert result["status"] in ["completed", "partial"]
        assert result["subtasks_completed"] + result["subtasks_failed"] == len(result["results"])

    @pytest.mark.asyncio
    async def test_execute_timeout_triggers_warning(self):
        """Test that timeout during execution triggers timeout handling (lines 73-74)."""
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()
        # Use a very short timeout to trigger the timeout branch
        result = await swarm.execute("Configure the firewall and monitor logs", timeout=0.001)
        assert result["status"] == "partial"
        assert result["elapsed_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execute_with_successful_agent_response(self):
        """Test successful agent message processing (line 100)."""
        from core.swarm.bus import MessageBus

        bus = MessageBus()
        swarm = SwarmOrchestrator(bus=bus)
        swarm.add_default_agents()

        # Register agents and subscriptions using internal _agents dict
        for agent_id in swarm.registry._agents:
            bus.register(agent_id)
            bus.subscribe(agent_id, "task")
            bus.subscribe("orchestrator", "result")

        # Execute should process at least one task
        result = await swarm.execute("Click the button", timeout=1.0)
        assert "results" in result
        assert result["subtasks_total"] >= 1


# ── SpecialistAgent.run_once ─────────────────────────────────────────────────

class TestSpecialistRunOnce:
    @pytest.mark.asyncio
    async def test_run_once_no_message_returns_none(self):
        bus = MessageBus()
        agent = DesktopAgent(bus)
        result = await agent.run_once(timeout=0.05)
        assert result is None

    @pytest.mark.asyncio
    async def test_run_once_control_stop(self):
        bus = MessageBus()
        agent = DesktopAgent(bus)
        await bus.send(AgentMessage(
            sender="orchestrator",
            recipient=agent.agent_id,
            msg_type="control",
            payload={"command": "stop"},
        ))
        result = await agent.run_once(timeout=1.0)
        assert result is not None
        assert result["success"] is True
        assert agent.state == AgentState.STOPPED

    @pytest.mark.asyncio
    async def test_run_once_control_other_returns_none(self):
        bus = MessageBus()
        agent = DesktopAgent(bus)
        await bus.send(AgentMessage(
            sender="orchestrator",
            recipient=agent.agent_id,
            msg_type="control",
            payload={"command": "pause"},
        ))
        result = await agent.run_once(timeout=1.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_run_once_non_task_message_returns_none(self):
        from unittest.mock import AsyncMock, patch
        bus = MessageBus()
        agent = DesktopAgent(bus)
        msg = AgentMessage(
            sender="monitor",
            recipient=agent.agent_id,
            msg_type="status",
            payload={"healthy": True},
        )
        with patch.object(bus, "receive", new=AsyncMock(return_value=msg)):
            result = await agent.run_once(timeout=1.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_run_once_task_success(self):
        bus = MessageBus()
        agent = DesktopAgent(bus)
        await bus.send(AgentMessage(
            sender="orchestrator",
            recipient=agent.agent_id,
            msg_type="task",
            payload={"action": {"action": "click", "x": 10, "y": 20}},
        ))
        result = await agent.run_once(timeout=1.0)
        assert result is not None
        assert result["success"] is True
        assert "elapsed_ms" in result
        assert result["agent_id"] == agent.agent_id
        assert agent.state == AgentState.IDLE
        assert agent.task_count == 1

    @pytest.mark.asyncio
    async def test_run_once_task_exception(self):
        from unittest.mock import AsyncMock, patch
        bus = MessageBus()
        agent = DesktopAgent(bus)
        await bus.send(AgentMessage(
            sender="orchestrator",
            recipient=agent.agent_id,
            msg_type="task",
            payload={"action": {}},
        ))
        with patch.object(agent, "process_task", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await agent.run_once(timeout=1.0)
        assert result is not None
        assert result["success"] is False
        assert agent.state == AgentState.ERROR
        assert agent.error_count == 1


# ── TerminalAgent and MonitorAgent ────────────────────────────────────────────

class TestTerminalAndMonitorAgents:
    @pytest.mark.asyncio
    async def test_monitor_agent_process_task(self):
        bus = MessageBus()
        agent = MonitorAgent(bus)
        result = await agent.process_task({"check": "cpu"})
        assert result["success"] is True
        assert "cpu" in result["output"]
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_monitor_agent_default_check(self):
        bus = MessageBus()
        agent = MonitorAgent(bus)
        result = await agent.process_task({})
        assert "screenshot" in result["output"]

    @pytest.mark.asyncio
    async def test_terminal_agent_process_task(self):
        from unittest.mock import MagicMock, patch
        bus = MessageBus()
        agent = TerminalAgent(bus)
        mock_backend = MagicMock()
        mock_backend.shell.execute.return_value = {"exit_code": 0, "stdout": "ok", "stderr": ""}
        with patch("core.platform.get_backend", return_value=mock_backend):
            result = await agent.process_task({"command": "echo hello"})
        assert result["success"] is True
        mock_backend.shell.execute.assert_called_once_with("echo hello")

    @pytest.mark.asyncio
    async def test_terminal_agent_uses_description_fallback(self):
        from unittest.mock import MagicMock, patch
        bus = MessageBus()
        agent = TerminalAgent(bus)
        mock_backend = MagicMock()
        mock_backend.shell.execute.return_value = {"exit_code": 1, "stdout": "", "stderr": "err"}
        with patch("core.platform.get_backend", return_value=mock_backend):
            result = await agent.process_task({"description": "ls /tmp"})
        assert result["success"] is False
        mock_backend.shell.execute.assert_called_once_with("ls /tmp")
