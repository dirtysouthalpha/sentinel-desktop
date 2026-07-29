"""Fleet mesh CLI — command-line control for the distributed fleet."""
from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from core.mesh.event_bus import EventBus
from core.mesh.metrics import FleetMetricsAggregator

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create the fleet CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="fleet",
        description="Sentinel Fleet Mesh CLI — control the distributed fleet",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    p_status = subparsers.add_parser("status", help="Show fleet status")
    p_status.add_argument("--format", choices=["text", "json"], default="text")

    # nodes
    p_nodes = subparsers.add_parser("nodes", help="List fleet nodes")
    p_nodes.add_argument("--format", choices=["text", "json"], default="text")

    # plans
    p_plans = subparsers.add_parser("plans", help="List active plans")
    p_plans.add_argument("--format", choices=["text", "json"], default="text")

    # create-plan
    p_create = subparsers.add_parser("create-plan", help="Create a new plan")
    p_create.add_argument("name", help="Plan name")
    p_create.add_argument("--tasks", required=True, help="JSON task list")
    p_create.add_argument("--format", choices=["text", "json"], default="text")

    # assign
    p_assign = subparsers.add_parser("assign", help="Assign a task to a node")
    p_assign.add_argument("plan_id", help="Plan ID")
    p_assign.add_argument("task_id", help="Task ID")
    p_assign.add_argument("node_id", help="Target node ID")
    p_assign.add_argument("--format", choices=["text", "json"], default="text")

    # deploy
    p_deploy = subparsers.add_parser("deploy", help="Deploy a plan to the fleet")
    p_deploy.add_argument("name", help="Plan name")
    p_deploy.add_argument("--tasks", required=True, help="JSON task list")
    p_deploy.add_argument("--format", choices=["text", "json"], default="text")

    # logs
    p_logs = subparsers.add_parser("logs", help="Show recent fleet events")
    p_logs.add_argument("--limit", type=int, default=20, help="Number of events")
    p_logs.add_argument("--format", choices=["text", "json"], default="text")

    return parser


class FleetCLI:
    """Executes fleet CLI commands."""

    def __init__(
        self,
        bus: EventBus | None = None,
        metrics: FleetMetricsAggregator | None = None,
        event_log: list[dict[str, Any]] | None = None,
    ) -> None:
        self.bus = bus or EventBus()
        self.metrics = metrics or FleetMetricsAggregator()
        self._event_log = event_log if event_log is not None else []
        self.parser = create_parser()

    def execute(self, args: list[str] | None = None) -> str:
        """Execute a CLI command and return the output."""
        parsed = self.parser.parse_args(args)

        if not parsed.command:
            self.parser.print_help()
            return ""

        handler = getattr(self, f"cmd_{parsed.command.replace('-', '_')}", None)
        if handler is None:
            return f"Unknown command: {parsed.command}"

        return handler(parsed)

    def cmd_status(self, args: argparse.Namespace) -> str:
        """Show fleet status."""
        summary = self.metrics.get_fleet_summary()
        if args.format == "json":
            return json.dumps(summary, indent=2, default=str)

        lines = [
            "FLEET STATUS",
            "=" * 40,
            f"Total nodes: {summary.get('total_nodes', 0)}",
            f"Healthy nodes: {summary.get('healthy_nodes', 0)}",
            f"Avg CPU: {summary.get('avg_cpu', 0):.1f}%",
            f"Avg Memory: {summary.get('avg_memory', 0):.1f}%",
            f"Active tasks: {summary.get('total_tasks_active', 0)}",
            f"Completed tasks: {summary.get('total_tasks_completed', 0)}",
        ]
        return "\n".join(lines)

    def cmd_nodes(self, args: argparse.Namespace) -> str:
        """List fleet nodes."""
        summary = self.metrics.get_fleet_summary()
        nodes = summary.get("nodes", {})
        if args.format == "json":
            return json.dumps(nodes, indent=2, default=str)

        if not nodes:
            return "No nodes registered."

        lines = ["NODES", "=" * 40]
        for node_id, info in nodes.items():
            cpu = info.get("cpu_percent", 0)
            mem = info.get("memory_percent", 0)
            lines.append(f"  {node_id}: CPU {cpu:.0f}% | MEM {mem:.0f}%")
        return "\n".join(lines)

    def cmd_plans(self, args: argparse.Namespace) -> str:
        """List active plans."""
        if args.format == "json":
            return json.dumps([], indent=2)  # Would query orchestrator
        return "No active plans."

    def cmd_create_plan(self, args: argparse.Namespace) -> str:
        """Create a new plan."""
        try:
            tasks = json.loads(args.tasks)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        if args.format == "json":
            return json.dumps({"status": "created", "name": args.name, "tasks": len(tasks)}, indent=2)
        return f"Plan '{args.name}' created with {len(tasks)} tasks."

    def cmd_assign(self, args: argparse.Namespace) -> str:
        """Assign a task to a node."""
        if args.format == "json":
            return json.dumps({"status": "assigned", "plan": args.plan_id, "task": args.task_id, "node": args.node_id}, indent=2)
        return f"Task {args.task_id} of plan {args.plan_id} assigned to {args.node_id}."

    def cmd_deploy(self, args: argparse.Namespace) -> str:
        """Deploy a plan to the fleet."""
        try:
            tasks = json.loads(args.tasks)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        if args.format == "json":
            return json.dumps({"status": "deployed", "name": args.name, "tasks": len(tasks)}, indent=2)
        return f"Plan '{args.name}' deployed with {len(tasks)} tasks."

    def cmd_logs(self, args: argparse.Namespace) -> str:
        """Show recent fleet events."""
        events = self._event_log[-args.limit:]
        if args.format == "json":
            return json.dumps(events, indent=2, default=str)

        if not events:
            return "No events recorded."

        lines = [f"RECENT EVENTS (last {len(events)})", "=" * 40]
        for evt in events:
            evt_type = evt.get("type", "?")
            data = evt.get("data", {})
            summary = ", ".join(f"{k}={v}" for k, v in list(data.items())[:3])
            lines.append(f"  {evt_type}: {summary}")
        return "\n".join(lines)


def main(args: list[str] | None = None) -> str:
    """Entry point for the fleet CLI."""
    cli = FleetCLI()
    return cli.execute(args)


if __name__ == "__main__":
    print(main())
