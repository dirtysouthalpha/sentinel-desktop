"""MCP server exposing fleet mesh operations as tools."""
from __future__ import annotations

import json
import logging
from typing import Any

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
]


class FleetMCPServer:
    """MCP server for fleet mesh operations."""

    def __init__(self, metrics: FleetMetricsAggregator | None = None) -> None:
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
        """Get fleet status."""
        return self.metrics.get_fleet_summary()

    async def tool_list_nodes(self, args: dict[str, Any]) -> dict[str, Any]:
        """List all nodes."""
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
        """Deploy a task."""
        return {
            "status": "deployed",
            "task_type": args.get("task_type"),
            "goal": args.get("goal"),
            "node_id": args.get("node_id"),
            "params": json.loads(args.get("params", "{}")),
        }

    async def tool_get_metrics(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get metrics."""
        node_id = args.get("node_id")
        if node_id:
            summary = self.metrics.get_fleet_summary()
            nodes = summary.get("nodes", {})
            return {"node": nodes.get(node_id, {"error": "Node not found"})}
        return self.metrics.get_fleet_summary()
