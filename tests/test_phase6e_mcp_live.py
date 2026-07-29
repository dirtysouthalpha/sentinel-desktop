"""Phase 6E: MCP server wired to live EventBus tests."""
from __future__ import annotations

import json

import pytest

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.mcp_server import FleetMCPServer
from core.mesh.metrics import FleetMetricsAggregator


class TestMCPLive:
    @pytest.fixture
    def live_server(self):
        """MCP server with a real EventBus and MetricsAggregator."""
        bus = EventBus()
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "node-1", "cpu_percent": 30.0, "memory_percent": 45.0, "tasks_active": 2, "tasks_completed": 10})
        agg.update({"node_id": "node-2", "cpu_percent": 60.0, "memory_percent": 70.0, "tasks_active": 1, "tasks_completed": 5})
        server = FleetMCPServer(bus=bus, metrics=agg)
        return server, bus

    @pytest.mark.asyncio
    async def test_fleet_status_returns_live_data(self, live_server):
        server, _ = live_server
        result = await server.tool_fleet_status({})
        assert result["total_nodes"] == 2
        assert result["avg_cpu"] == 45.0
        assert result["avg_memory"] == 57.5

    @pytest.mark.asyncio
    async def test_list_nodes_returns_live_nodes(self, live_server):
        server, _ = live_server
        result = await server.tool_list_nodes({})
        assert "node-1" in result["nodes"]
        assert "node-2" in result["nodes"]

    @pytest.mark.asyncio
    async def test_deploy_task_publishes_to_bus(self, live_server):
        """deploy_task publishes TASK_ASSIGNED to the live EventBus."""
        server, bus = live_server
        received = []
        bus.subscribe(FleetEvent.TASK_ASSIGNED, lambda env: received.append(env))
        result = await server.tool_deploy_task({
            "task_type": "shell", "goal": "echo test", "node_id": "node-1",
            "params": json.dumps({"command": "echo test"}),
        })
        assert result["status"] == "deployed"
        assert len(received) == 1
        assert received[0]["data"]["node_id"] == "node-1"

    @pytest.mark.asyncio
    async def test_get_metrics_node_specific(self, live_server):
        server, _ = live_server
        result = await server.tool_get_metrics({"node_id": "node-1"})
        assert "node" in result
        assert result["node"]["node_id"] == "node-1"

    @pytest.mark.asyncio
    async def test_inject_failure_publishes_to_bus(self, live_server):
        """inject_failure publishes a TASK_ASSIGNED designed to fail."""
        server, bus = live_server
        received = []
        bus.subscribe(FleetEvent.TASK_ASSIGNED, lambda env: received.append(env))
        result = await server.tool_inject_failure({"node_id": "node-1", "command": "exit 1"})
        assert result["status"] == "injected"
        assert len(received) == 1
