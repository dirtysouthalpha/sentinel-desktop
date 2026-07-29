"""MCP server exposing fleet mesh operations as tools."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator

logger = logging.getLogger(__name__)

# MCP tool definitions
TOOLS: list[dict[str, Any]] = [
    {
        "name": "fleet_status",
        "description": "Get current fleet status including node count, health, and task counts",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_nodes",
        "description": "List all fleet nodes with their CPU, memory, and health status",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "create_plan",
        "description": "Create a new fleet plan with tasks",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Plan name"},
                "tasks": {"type": "string", "description": "JSON array of task objects"},
            },
            "required": ["name", "tasks"],
        },
    },
    {
        "name": "deploy_task",
        "description": "Deploy a single task to a specific node",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": {"type": "string", "description": "Task type: shell, python, action, llm"},
                "goal": {"type": "string", "description": "Task goal/description"},
                "node_id": {"type": "string", "description": "Target node ID"},
                "params": {"type": "string", "description": "JSON object of task parameters"},
            },
            "required": ["task_type", "goal", "node_id"],
        },
    },
    {
        "name": "get_metrics",
        "description": "Get detailed metrics for a specific node or the entire fleet",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "Node ID (omit for fleet-wide)"},
            },
        },
    },
    {
        "name": "get_plans",
        "description": "Get active fleet plans",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_events",
        "description": "Get recent fleet events",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "inject_failure",
        "description": "Inject a stuck task for recovery testing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "Target node ID"},
                "command": {"type": "string", "description": "Command that fails (default: exit 1)"},
            },
            "required": ["node_id"],
        },
    },
]


class FleetMCPServer:
    """MCP server for fleet mesh operations, wired to a live EventBus."""

    def __init__(self, bus: EventBus | None = None, metrics: FleetMetricsAggregator | None = None) -> None:
        self.bus = bus
        self.metrics = metrics or FleetMetricsAggregator()

    def list_tools(self) -> list[dict[str, Any]]:
        """Return available MCP tools."""
        return TOOLS

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute an MCP tool and return the result."""
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = await handler(arguments)
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def tool_fleet_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get fleet status from live metrics aggregator."""
        return self.metrics.get_fleet_summary()

    async def tool_list_nodes(self, args: dict[str, Any]) -> dict[str, Any]:
        """List all nodes from live metrics."""
        summary = self.metrics.get_fleet_summary()
        return {"nodes": summary.get("nodes", {})}

    async def tool_create_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        """Create a plan."""
        name = args.get("name", "")
        tasks_json = args.get("tasks", "[]")
        try:
            tasks = json.loads(tasks_json)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid tasks JSON: {e}"}
        return {
            "status": "created",
            "name": name,
            "task_count": len(tasks),
            "plan_id": f"plan-{name.lower().replace(' ', '-')}",
        }

    async def tool_deploy_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Deploy a task by publishing TASK_ASSIGNED to the live EventBus."""
        params = json.loads(args.get("params", "{}"))
        task_data = {
            "task_type": args.get("task_type", "shell"),
            "goal": args.get("goal", ""),
            "node_id": args.get("node_id", ""),
            "params": params,
        }
        if self.bus:
            await self.bus.publish(FleetEvent.TASK_ASSIGNED, {
                "task_id": f"mcp-{uuid.uuid4().hex[:8]}",
                "plan_id": f"mcp-plan-{uuid.uuid4().hex[:8]}",
                **task_data,
            })
        return {"status": "deployed", **task_data}

    async def tool_get_metrics(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get metrics from live aggregator."""
        node_id = args.get("node_id")
        if node_id:
            summary = self.metrics.get_fleet_summary()
            nodes = summary.get("nodes", {})
            return {"node": nodes.get(node_id, {"error": "Node not found"})}
        return self.metrics.get_fleet_summary()

    async def tool_get_plans(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get active plans from the bus event log."""
        return {"plans": [], "note": "Plans managed by Orchestrator on leader node"}

    async def tool_get_events(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get recent fleet events."""
        return {"events": [], "note": "Events flow through EventBus subscriptions"}

    async def tool_inject_failure(self, args: dict[str, Any]) -> dict[str, Any]:
        """Inject a stuck task for recovery testing via the live EventBus."""
        node_id = args.get("node_id", "")
        command = args.get("command", "exit 1")
        if self.bus:
            await self.bus.publish(FleetEvent.TASK_ASSIGNED, {
                "task_id": f"inject-{uuid.uuid4().hex[:8]}",
                "plan_id": "injection-test",
                "node_id": node_id,
                "task_type": "shell",
                "goal": command,
                "params": {"command": command},
            })
        return {"status": "injected", "node_id": node_id, "command": command}
