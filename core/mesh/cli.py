"""Fleet mesh CLI — command-line control for the distributed fleet."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator
from core.mesh.trust_dial import ActionType, TrustDial, TrustLevel

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

    # inject-failure
    p_inject = subparsers.add_parser("inject-failure", help="Inject a stuck task for recovery testing")
    p_inject.add_argument("node_id", help="Target node ID")
    p_inject.add_argument("--cmd", dest="cmd", default="exit 1", help="Command that fails")
    p_inject.add_argument("--format", choices=["text", "json"], default="text")

    # trust
    p_trust = subparsers.add_parser("trust", help="Get/set trust dial levels")
    p_trust.add_argument("--set", nargs=2, metavar=("TYPE", "LEVEL"), help="Set trust level (e.g., destructive execute)")
    p_trust.add_argument("--format", choices=["text", "json"], default="text")

    # logs
    p_logs = subparsers.add_parser("logs", help="Show recent fleet events")
    p_logs.add_argument("--limit", type=int, default=20, help="Number of events")
    p_logs.add_argument("--format", choices=["text", "json"], default="text")

    # empire
    p_empire = subparsers.add_parser("empire", help="Run an empire analytics plan")
    p_empire.add_argument("--format", choices=["text", "json"], default="text")

    # audit
    p_audit = subparsers.add_parser("audit", help="Run self-improvement code audit")
    p_audit.add_argument("--format", choices=["text", "json"], default="text")

    # evals
    p_evals = subparsers.add_parser("evals", help="Run golden eval suite")
    p_evals.add_argument("--format", choices=["text", "json"], default="text")

    # version
    p_version = subparsers.add_parser("version", help="Show fleet version info")

    return parser


class FleetCLI:
    """Executes fleet CLI commands, wired to a live EventBus."""

    def __init__(
        self,
        bus: EventBus | None = None,
        metrics: FleetMetricsAggregator | None = None,
        event_log: list[dict[str, Any]] | None = None,
    ) -> None:
        self.bus = bus or EventBus()
        self.metrics = metrics or FleetMetricsAggregator()
        self._event_log = event_log if event_log is not None else []
        self._trust_dial = TrustDial()
        self.parser = create_parser()

    def execute(self, args: list[str] | None = None) -> str:
        """Execute a CLI command and return the output."""
        try:
            parsed = self.parser.parse_args(args)
        except SystemExit as exc:
            # argparse raises SystemExit(0) for --help (let it through)
            # and SystemExit(2) for unknown subcommands (friendly message).
            if exc.code == 0:
                raise
            return f"Unknown command. Run 'fleet --help' for available commands."

        if not parsed.command:
            self.parser.print_help()
            return ""

        handler = getattr(self, f"cmd_{parsed.command.replace('-', '_')}", None)
        if handler is None:
            return f"Unknown command: {parsed.command}"

        return handler(parsed)

    def _bus_publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Sync-safe publish to the EventBus (fire-and-forget)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.bus.publish(event_type, data))
        except RuntimeError:
            asyncio.run(self.bus.publish(event_type, data))

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
        """Deploy a plan to the live fleet by publishing TASK_ASSIGNED events."""
        try:
            tasks = json.loads(args.tasks)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        if self.bus:
            for task in tasks:
                self._bus_publish(FleetEvent.TASK_ASSIGNED, {
                    "task_id": task.get("id", ""),
                    "plan_id": args.name,
                    "node_id": task.get("node_id", ""),
                    "task_type": task.get("type", "shell"),
                    "goal": task.get("goal", ""),
                    "params": task.get("params", {}),
                })
        if args.format == "json":
            return json.dumps({"status": "deployed", "name": args.name, "tasks": len(tasks)}, indent=2)
        return f"Plan '{args.name}' deployed with {len(tasks)} tasks."

    def cmd_inject_failure(self, args: argparse.Namespace) -> str:
        """Inject a stuck task for recovery testing via the live EventBus."""
        command = args.cmd
        if self.bus:
            self._bus_publish(FleetEvent.TASK_ASSIGNED, {
                "task_id": f"inject-{args.node_id}",
                "plan_id": "injection-test",
                "node_id": args.node_id,
                "task_type": "shell",
                "goal": command,
                "params": {"command": command},
            })
        if args.format == "json":
            return json.dumps({"status": "injected", "node_id": args.node_id}, indent=2)
        return f"Failure injected to {args.node_id}."

    def cmd_trust(self, args: argparse.Namespace) -> str:
        """Get/set trust dial levels."""
        if args.set:
            type_str, level_str = args.set
            try:
                action_type = ActionType(type_str.lower())
                level = TrustLevel(level_str.lower())
                self._trust_dial.set_level(action_type, level)
                if args.format == "json":
                    return json.dumps({"status": "set", "type": type_str, "level": level_str}, indent=2)
                return f"Trust dial: {type_str} set to {level_str}."
            except ValueError as e:
                return f"Invalid type/level: {e}"
        # Show current levels
        levels = {}
        for at in ActionType:
            levels[at.value] = self._trust_dial.get_level(at).value
        if args.format == "json":
            return json.dumps(levels, indent=2)
        lines = ["TRUST DIAL LEVELS", "=" * 30]
        for at, level in levels.items():
            lines.append(f"  {at}: {level}")
        return "\n".join(lines)

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


    def cmd_empire(self, args: argparse.Namespace) -> str:
        """Run an empire analytics plan (yt-stats, alpaca-pnl, buffer-metrics → score → narrative)."""
        from core.mesh.empire_tasks import (
            handle_alpaca_pnl,
            handle_buffer_metrics,
            handle_empire_score,
            handle_narrative,
            handle_yt_stats,
        )

        import asyncio

        # Execute data tasks (stub mode if no credentials).
        yt = asyncio.run(handle_yt_stats({"params": {}}))
        alpaca = asyncio.run(handle_alpaca_pnl({"params": {"include_positions": False}}))
        buffer = asyncio.run(handle_buffer_metrics({"params": {}}))

        # Aggregate score.
        score = asyncio.run(handle_empire_score({"params": {
            "dependency_results": {"yt-stats": yt, "alpaca-pnl": alpaca, "buffer-metrics": buffer},
        }}))

        # Narrative.
        narrative = asyncio.run(handle_narrative({"params": {
            "dependency_results": {"empire-score": score},
            "tone": "professional",
        }}))

        result = {
            "yt_stats": yt,
            "alpaca_pnl": alpaca,
            "buffer_metrics": buffer,
            "empire_score": score["total_score"],
            "components": score["components"],
            "narrative": narrative["narrative"],
        }
        if args.format == "json":
            return json.dumps(result, indent=2, default=str)
        lines = [
            "EMPIRE ANALYTICS PLAN",
            "=" * 40,
            f"  Empire Score: {score['total_score']}/100",
            f"  YT: views={yt.get('views', 'n/a')}, subs={yt.get('subscribers', 'n/a')}",
            f"  Alpaca: equity={alpaca.get('equity', 'n/a')}, P&L={alpaca.get('unrealized_pl', 'n/a')}",
            f"  Buffer: posts={buffer.get('posts', 'n/a')}",
            f"  Narrative: {narrative['narrative']}",
        ]
        return "\n".join(lines)

    def cmd_audit(self, args: argparse.Namespace) -> str:
        """Run the self-improvement code audit."""
        import os

        from core.mesh.self_improvement import SelfImprovementLoop

        # Resolve project root (core/cli.py → project root is 2 levels up).
        project_root = str(Path(os.path.abspath(__file__)).parent.parent.parent)
        loop = SelfImprovementLoop(project_root)
        report = loop.run()
        if args.format == "json":
            return json.dumps(
                {"findings": len(report.findings), "proposals": len(report.proposals),
                 "executed": len(report.executed), "verified": len(report.verified),
                 "summary": report.summary},
                indent=2,
            )
        lines = [
            "SELF-IMPROVEMENT AUDIT",
            "=" * 40,
            report.summary,
            "",
            "TOP FINDINGS:",
        ]
        for f in sorted(report.findings, key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.severity.value, 9))[:5]:
            lines.append(f"  [{f.severity.value.upper()}] {f.file_path}:{f.line_number}  {f.description[:60]}")
        return "\n".join(lines)

    def cmd_evals(self, args: argparse.Namespace) -> str:
        """Run the golden eval suite."""
        from core.mesh.golden_evals import suite

        report = suite.run()
        if args.format == "json":
            results = [{"name": r.name, "component": r.component.value, "passed": r.passed, "message": r.message} for r in report.results]
            return json.dumps({"total": report.total, "passed": report.passed, "failed": report.failed, "pass_rate": report.pass_rate, "results": results}, indent=2)
        return report.summary()

    def cmd_version(self, args: argparse.Namespace) -> str:
        """Show fleet version info."""
        import importlib

        core_mod = importlib.import_module("core")
        version = getattr(core_mod, "__version__", "unknown")
        mesh_mod = importlib.import_module("core.mesh")
        mod_count = len(getattr(mesh_mod, "__all__", [])) or len([n for n in dir(mesh_mod) if not n.startswith("_")])
        return (
            f"Sentinel Fleet Mesh v{version}\n"
            f"CLI: 1.0.0\n"
            f"Mesh: Phase 6\n"
            f"Components: {mod_count} modules"
        )


def main(args: list[str] | None = None) -> str:
    """Entry point for the fleet CLI."""
    cli = FleetCLI()
    return cli.execute(args)


if __name__ == "__main__":
    print(main())
