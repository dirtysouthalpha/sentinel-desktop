"""Gap tests for core.swarm.{bus,orchestrator,registry}.

Covers:
  bus.py          — line 86 (unregister clears subscriptions),
                    lines 107-108 (broadcast QueueFull), 116-117 (direct QueueFull),
                    line 130 (receive returns None for unknown agent)
  orchestrator.py — lines 72-74 (timeout break), lines 77-84 (no_agent result)
  registry.py     — line 37 (unregister), line 41 (get)
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from core.swarm.bus import AgentMessage, MessageBus
from core.swarm.orchestrator import SwarmOrchestrator
from core.swarm.registry import AgentRegistry
from core.swarm.specialist import AgentRole, DesktopAgent


# ── MessageBus ────────────────────────────────────────────────────────────


class TestBusUnregister:
    """Line 86 — unregister() removes agent from subscriptions."""

    def test_unregister_removes_from_subscriptions(self):
        bus = MessageBus()
        bus.register("agent-x")
        bus.subscribe("agent-x", "task")

        bus.unregister("agent-x")

        # Should no longer be in subscriptions for "task"
        subs = bus._subscriptions.get("task", set())
        assert "agent-x" not in subs

    def test_unregister_removes_queue(self):
        bus = MessageBus()
        bus.register("agent-y")
        bus.unregister("agent-y")
        assert "agent-y" not in bus.registered_agents


class TestBusBroadcastQueueFull:
    """Lines 107-108 — QueueFull on broadcast drops message and logs warning."""

    @pytest.mark.asyncio
    async def test_broadcast_queue_full_logs_warning(self, caplog):
        import logging

        bus = MessageBus(max_queue_size=1)
        bus.register("listener")
        bus.subscribe("listener", "status")

        # Fill the queue to capacity
        msg1 = AgentMessage(sender="s", recipient="broadcast", msg_type="status")
        msg2 = AgentMessage(sender="s", recipient="broadcast", msg_type="status")
        await bus.send(msg1)  # fills the queue

        with caplog.at_level(logging.WARNING, logger="core.swarm.bus"):
            count = await bus.send(msg2)  # should trigger QueueFull

        assert count == 0
        assert any("Queue full" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_broadcast_queue_full_returns_zero_recipients(self):
        bus = MessageBus(max_queue_size=1)
        bus.register("listener")
        bus.subscribe("listener", "status")

        # Fill first, then overflow
        msg = AgentMessage(sender="s", recipient="broadcast", msg_type="status")
        await bus.send(msg)
        overflow = AgentMessage(sender="s", recipient="broadcast", msg_type="status")
        count = await bus.send(overflow)
        assert count == 0


class TestBusDirectQueueFull:
    """Lines 116-117 — QueueFull on direct message drops and logs warning."""

    @pytest.mark.asyncio
    async def test_direct_queue_full_logs_warning(self, caplog):
        import logging

        bus = MessageBus(max_queue_size=1)
        bus.register("target")

        msg1 = AgentMessage(sender="s", recipient="target", msg_type="task")
        msg2 = AgentMessage(sender="s", recipient="target", msg_type="task")
        await bus.send(msg1)

        with caplog.at_level(logging.WARNING, logger="core.swarm.bus"):
            count = await bus.send(msg2)

        assert count == 0
        assert any("Queue full" in r.message for r in caplog.records)


class TestBusReceiveNoQueue:
    """Line 130 — receive() returns None when agent has no queue."""

    @pytest.mark.asyncio
    async def test_receive_unknown_agent_returns_none(self):
        bus = MessageBus()
        result = await bus.receive("nonexistent-agent", timeout=0.05)
        assert result is None


# ── SwarmOrchestrator ─────────────────────────────────────────────────────


class TestOrchestratorTimeout:
    """Lines 72-74 — loop breaks when elapsed > timeout."""

    @pytest.mark.asyncio
    async def test_execute_breaks_on_timeout(self):
        swarm = SwarmOrchestrator()
        swarm.add_default_agents()

        # Make monotonic appear to jump past timeout on first iteration check
        call_count = [0]
        real_monotonic = time.monotonic

        def fake_monotonic():
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.0  # start = 0
            return 9999.0   # immediately past timeout

        with patch("core.swarm.orchestrator.time.monotonic", side_effect=fake_monotonic):
            result = await swarm.execute("open the browser", timeout=1.0)

        # First subtask was skipped due to timeout — results should be empty
        assert result["subtasks_completed"] == 0
        assert result["subtasks_total"] >= 1


class TestOrchestratorNoAgent:
    """Lines 77-84 — no_agent result when registry has no suitable agent."""

    @pytest.mark.asyncio
    async def test_execute_no_agent_appends_no_agent_result(self):
        # Empty registry — no agents registered
        swarm = SwarmOrchestrator()

        result = await swarm.execute("click on the icon")

        # Should complete but with no_agent status for each subtask
        assert result["status"] in ("completed", "partial")
        no_agent_results = [r for r in result["results"] if r.get("status") == "no_agent"]
        assert len(no_agent_results) >= 1
        assert "No available agent" in no_agent_results[0]["error"]


# ── AgentRegistry ─────────────────────────────────────────────────────────


class TestRegistryUnregister:
    """Line 37 — unregister() removes agent from registry."""

    def test_unregister_removes_agent(self):
        registry = AgentRegistry()
        bus = MessageBus()
        agent = DesktopAgent(bus, "desktop-test")
        registry.register(agent)
        assert registry.count == 1

        registry.unregister("desktop-test")
        assert registry.count == 0

    def test_unregister_nonexistent_does_not_raise(self):
        registry = AgentRegistry()
        registry.unregister("ghost-agent")  # should be a no-op


class TestRegistryGet:
    """Line 41 — get() returns agent by ID, or None."""

    def test_get_returns_registered_agent(self):
        registry = AgentRegistry()
        bus = MessageBus()
        agent = DesktopAgent(bus, "desktop-get-test")
        registry.register(agent)

        found = registry.get("desktop-get-test")
        assert found is agent

    def test_get_returns_none_for_unknown_id(self):
        registry = AgentRegistry()
        result = registry.get("nobody")
        assert result is None
