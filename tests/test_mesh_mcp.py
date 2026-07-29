"""Tests for the fleet mesh MCP server."""
import json

import pytest

from core.mesh.mcp_server import FleetMCPServer
from core.mesh.metrics import FleetMetricsAggregator


@pytest.fixture
def metrics():
    agg = FleetMetricsAggregator()
    agg.update({"node_id": "n1", "cpu_percent": 50.0, "memory_percent": 60.0})
    agg.update({"node_id": "n2", "cpu_percent": 30.0, "memory_percent": 40.0})
    return agg


@pytest.fixture
def server(metrics):
    return FleetMCPServer(metrics=metrics)


class TestFleetMCPServer:
    def test_list_tools(self, server):
        tools = server.list_tools()
        assert len(tools) == 8
        names = [t["name"] for t in tools]
        assert "fleet_status" in names
        assert "list_nodes" in names
        assert "create_plan" in names
        assert "deploy_task" in names
        assert "get_metrics" in names
        assert "get_plans" in names
        assert "get_events" in names
        assert "inject_failure" in names

    @pytest.mark.asyncio
    async def test_tool_fleet_status(self, server):
        result = await server.tool_fleet_status({})
        assert result["total_nodes"] == 2
        assert result["avg_cpu"] == 40.0

    @pytest.mark.asyncio
    async def test_tool_list_nodes(self, server):
        result = await server.tool_list_nodes({})
        assert "n1" in result["nodes"]
        assert "n2" in result["nodes"]

    @pytest.mark.asyncio
    async def test_tool_create_plan(self, server):
        result = await server.tool_create_plan({
            "name": "test-plan",
            "tasks": json.dumps([{"id": "t1", "type": "shell", "goal": "echo"}]),
        })
        assert result["status"] == "created"
        assert result["task_count"] == 1

    @pytest.mark.asyncio
    async def test_tool_create_plan_invalid_json(self, server):
        result = await server.tool_create_plan({
            "name": "test",
            "tasks": "not json",
        })
        assert "error" in result

    @pytest.mark.asyncio
    async def test_tool_deploy_task(self, server):
        result = await server.tool_deploy_task({
            "task_type": "shell",
            "goal": "echo test",
            "node_id": "n1",
            "params": json.dumps({"command": "echo test"}),
        })
        assert result["status"] == "deployed"
        assert result["node_id"] == "n1"

    @pytest.mark.asyncio
    async def test_tool_get_metrics_node(self, server):
        result = await server.tool_get_metrics({"node_id": "n1"})
        assert "node" in result
        assert result["node"]["cpu_percent"] == 50.0

    @pytest.mark.asyncio
    async def test_tool_get_metrics_fleet(self, server):
        result = await server.tool_get_metrics({})
        assert result["total_nodes"] == 2

    @pytest.mark.asyncio
    async def test_call_tool(self, server):
        result_str = await server.call_tool("fleet_status", {})
        result = json.loads(result_str)
        assert result["total_nodes"] == 2

    @pytest.mark.asyncio
    async def test_call_tool_unknown(self, server):
        result_str = await server.call_tool("nonexistent", {})
        result = json.loads(result_str)
        assert "error" in result
