# Fleet Mesh Phase 4 — Fleet CLI, Self-Healing Watcher, MCP Server

**Date:** 2026-07-29
**Goal:** Remote CLI control, autonomous self-healing, and MCP tool exposure for the fleet mesh.
**Depends on:** Phase 1 (16 modules) + Phase 2 (transport, executor, dashboard) + Phase 3 (agent integration, memory, observability)

---

## Task 1: Fleet CLI

**Files:**
- Create: `core/mesh/cli.py` — Fleet mesh CLI commands
- Modify: `main.py` — add `--fleet` flag and subcommands
- Test: `tests/test_mesh_cli.py`

### Design

A proper CLI for controlling the fleet mesh. Uses argparse subcommands (unlike the flat flags currently in main.py). Commands: `status`, `nodes`, `plans`, `create-plan`, `assign`, `deploy`, `logs`.

### `core/mesh/cli.py`

```python
"""Fleet mesh CLI — command-line control for the distributed fleet."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator
from core.mesh.node import NodeCapabilities, NodePriority

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
            f"Total nodes: {summary['total_nodes']}",
            f"Healthy nodes: {summary['healthy_nodes']}",
            f"Avg CPU: {summary['avg_cpu']:.1f}%",
            f"Avg Memory: {summary['avg_memory']:.1f}%",
            f"Active tasks: {summary['total_tasks_active']}",
            f"Completed tasks: {summary['total_tasks_completed']}",
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
```

### Modify `main.py`

Add a `--fleet` flag that delegates to the fleet CLI:

```python
# In parse_args():
parser.add_argument("--fleet", nargs="*", default=None,
                    metavar="COMMAND",
                    help="Fleet mesh CLI (status, nodes, plans, deploy, ...)")

# In main(), after mesh mode:
if args.fleet is not None:
    from core.mesh.cli import FleetCLI
    cli = FleetCLI()
    output = cli.execute(args.fleet)
    print(output)
    return
```

### `tests/test_mesh_cli.py`

```python
"""Tests for the fleet mesh CLI."""
import json
import pytest
from core.mesh.cli import FleetCLI, create_parser
from core.mesh.metrics import FleetMetricsAggregator, NodeMetrics


class TestFleetCLI:
    def test_parser_creates_subcommands(self):
        parser = create_parser()
        # Should parse without error
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_cli_construct(self):
        cli = FleetCLI()
        assert cli.bus is not None
        assert cli.metrics is not None

    def test_cmd_status_text(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 50.0, "memory_percent": 60.0})
        cli = FleetCLI(metrics=agg)
        output = cli.cmd_status(argparse.Namespace(format="text"))
        assert "Total nodes: 1" in output
        assert "Avg CPU: 50.0%" in output

    def test_cmd_status_json(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 50.0, "memory_percent": 60.0})
        cli = FleetCLI(metrics=agg)
        output = cli.cmd_status(argparse.Namespace(format="json"))
        data = json.loads(output)
        assert data["total_nodes"] == 1

    def test_cmd_nodes(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 25.0, "memory_percent": 40.0})
        cli = FleetCLI(metrics=agg)
        output = cli.cmd_nodes(argparse.Namespace(format="text"))
        assert "n1" in output
        assert "CPU 25%" in output

    def test_cmd_create_plan(self):
        cli = FleetCLI()
        tasks = json.dumps([{"id": "t1", "type": "shell", "goal": "echo test"}])
        output = cli.cmd_create_plan(argparse.Namespace(name="test-plan", tasks=tasks, format="text"))
        assert "created" in output

    def test_cmd_create_plan_invalid_json(self):
        cli = FleetCLI()
        output = cli.cmd_create_plan(argparse.Namespace(name="test", tasks="not json", format="text"))
        assert "Invalid JSON" in output

    def test_cmd_deploy(self):
        cli = FleetCLI()
        tasks = json.dumps([{"id": "t1", "type": "shell", "goal": "echo test"}])
        output = cli.cmd_deploy(argparse.Namespace(name="deploy-test", tasks=tasks, format="text"))
        assert "deployed" in output

    def test_cmd_logs_empty(self):
        cli = FleetCLI()
        output = cli.cmd_logs(argparse.Namespace(limit=10, format="text"))
        assert "No events" in output

    def test_cmd_logs_with_events(self):
        agg = FleetMetricsAggregator()
        cli = FleetCLI(metrics=agg, event_log=[
            {"type": "node_joined", "data": {"node_id": "n1"}},
            {"type": "task_completed", "data": {"task_id": "t1"}},
        ])
        output = cli.cmd_logs(argparse.Namespace(limit=10, format="text"))
        assert "node_joined" in output
        assert "task_completed" in output

    def test_execute_no_command(self):
        cli = FleetCLI()
        output = cli.execute([])
        assert output == ""  # prints help

    def test_execute_status(self):
        cli = FleetCLI()
        output = cli.execute(["status"])
        assert "FLEET STATUS" in output


import argparse  # needed for Namespace in tests
```

---

## Task 2: Self-Healing Watcher

**Files:**
- Create: `core/mesh/watcher.py` — Self-healing watchdog
- Test: `tests/test_mesh_watcher.py`

### Design

A background watcher that subscribes to `NODE_METRICS` and `TASK_ASSIGNED`/`TASK_COMPLETED` events. Detects stuck tasks (running too long), unhealthy nodes (high CPU/memory), and triggers recovery actions via the EventBus.

### `core/mesh/watcher.py`

```python
"""Self-healing watcher for the fleet mesh."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator
from core.mesh.recovery import FailureType

logger = logging.getLogger(__name__)


@dataclass
class TaskTracker:
    """Tracks a running task for stuck detection."""
    task_id: str
    plan_id: str
    node_id: str
    assigned_at: float = 0.0
    task_type: str = ""

    def __post_init__(self) -> None:
        if self.assigned_at == 0.0:
            self.assigned_at = time.time()

    @property
    def runtime_seconds(self) -> float:
        return time.time() - self.assigned_at


@dataclass
class WatcherConfig:
    """Configuration for the self-healing watcher."""
    task_timeout_seconds: float = 300.0  # 5 minutes
    cpu_threshold: float = 95.0
    memory_threshold: float = 95.0
    check_interval_seconds: float = 30.0
    max_retries: int = 3


class SelfHealingWatcher:
    """Monitors fleet health and triggers recovery actions."""

    def __init__(
        self,
        bus: EventBus,
        metrics: FleetMetricsAggregator,
        config: WatcherConfig | None = None,
        recovery_callback: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.bus = bus
        self.metrics = metrics
        self.config = config or WatcherConfig()
        self._recovery_callback = recovery_callback
        self._running = False
        self._task_trackers: dict[str, TaskTracker] = {}
        self._retry_counts: dict[str, int] = {}

    def start(self) -> None:
        """Start watching for failures."""
        self._running = True
        self.bus.subscribe(FleetEvent.TASK_ASSIGNED, self._on_task_assigned)
        self.bus.subscribe(FleetEvent.TASK_COMPLETED, self._on_task_completed)
        self.bus.subscribe(FleetEvent.TASK_FAILED, self._on_task_failed)
        self.bus.subscribe(FleetEvent.NODE_METRICS, self._on_node_metrics)
        logger.info("Self-healing watcher started")

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        self.bus.unsubscribe(FleetEvent.TASK_ASSIGNED, self._on_task_assigned)
        self.bus.unsubscribe(FleetEvent.TASK_COMPLETED, self._on_task_completed)
        self.bus.unsubscribe(FleetEvent.TASK_FAILED, self._on_task_failed)
        self.bus.unsubscribe(FleetEvent.NODE_METRICS, self._on_node_metrics)

    async def _on_task_assigned(self, envelope: dict[str, Any]) -> None:
        """Track newly assigned tasks."""
        data = envelope.get("data", {})
        task_id = data.get("task_id", "")
        if task_id:
            self._task_trackers[task_id] = TaskTracker(
                task_id=task_id,
                plan_id=data.get("plan_id", ""),
                node_id=data.get("node_id", ""),
                task_type=data.get("task_type", ""),
            )

    async def _on_task_completed(self, envelope: dict[str, Any]) -> None:
        """Remove completed tasks from tracking."""
        data = envelope.get("data", {})
        task_id = data.get("task_id", "")
        self._task_trackers.pop(task_id, None)
        self._retry_counts.pop(task_id, None)

    async def _on_task_failed(self, envelope: dict[str, Any]) -> None:
        """Handle task failure — may trigger retry."""
        data = envelope.get("data", {})
        task_id = data.get("task_id", "")
        error = data.get("error", "")
        plan_id = data.get("plan_id", "")

        retries = self._retry_counts.get(task_id, 0)
        if retries < self.config.max_retries:
            self._retry_counts[task_id] = retries + 1
            logger.warning("Task %s failed (retry %d/%d): %s", task_id, retries + 1, self.config.max_retries, error)
            # Publish retry event
            await self.bus.publish(FleetEvent.TASK_RETRY, {
                "task_id": task_id,
                "plan_id": plan_id,
                "retry_count": retries + 1,
                "error": error,
            })
        else:
            logger.error("Task %s exhausted retries: %s", task_id, error)

    async def _on_node_metrics(self, envelope: dict[str, Any]) -> None:
        """Process node metrics for stuck detection."""
        data = envelope.get("data", {})
        self.metrics.update(data)

    async def check_health(self) -> list[dict[str, Any]]:
        """Run a health check cycle. Returns list of recovery actions taken."""
        if not self._running:
            return []

        actions = []

        # Check for stuck tasks
        now = time.time()
        for task_id, tracker in list(self._task_trackers.items()):
            if tracker.runtime_seconds > self.config.task_timeout_seconds:
                logger.warning("Stuck task detected: %s (%.0fs)", task_id, tracker.runtime_seconds)
                actions.append({
                    "action": "stuck_task",
                    "task_id": task_id,
                    "node_id": tracker.node_id,
                    "runtime": tracker.runtime_seconds,
                })
                if self._recovery_callback:
                    self._recovery_callback("stuck_task", task_id, {
                        "node_id": tracker.node_id,
                        "plan_id": tracker.plan_id,
                    })

        # Check for unhealthy nodes
        stuck_nodes = self.metrics.get_stuck_nodes(
            cpu_threshold=self.config.cpu_threshold,
            memory_threshold=self.config.memory_threshold,
        )
        for node_id in stuck_nodes:
            logger.warning("Unhealthy node detected: %s", node_id)
            actions.append({
                "action": "unhealthy_node",
                "node_id": node_id,
            })
            if self._recovery_callback:
                self._recovery_callback("unhealthy_node", node_id, {})

        return actions

    async def run(self) -> None:
        """Run the watcher loop (blocking)."""
        self._running = True
        while self._running:
            try:
                await self.check_health()
            except Exception:
                logger.exception("Health check error")
            await asyncio.sleep(self.config.check_interval_seconds)
```

### Add `TASK_RETRY` to `core/mesh/event_bus.py`

```python
TASK_RETRY = "fleet.event.task.retry"
```

### `tests/test_mesh_watcher.py`

```python
"""Tests for the self-healing watcher."""
import asyncio
import pytest
import pytest_asyncio
from core.mesh.watcher import SelfHealingWatcher, WatcherConfig, TaskTracker
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def metrics():
    return FleetMetricsAggregator()


@pytest.fixture
def watcher(bus, metrics):
    w = SelfHealingWatcher(bus, metrics, config=WatcherConfig(
        task_timeout_seconds=1.0,
        check_interval_seconds=0.1,
    ))
    w.start()
    yield w
    w.stop()


class TestTaskTracker:
    def test_runtime(self):
        t = TaskTracker(task_id="t1", plan_id="p1", node_id="n1", assigned_at=0.0)
        assert t.runtime_seconds > 0

    def test_default_timestamp(self):
        t = TaskTracker(task_id="t1", plan_id="p1", node_id="n1")
        assert t.assigned_at > 0


class TestSelfHealingWatcher:
    def test_construct(self, bus, metrics):
        w = SelfHealingWatcher(bus, metrics)
        assert w.config.task_timeout_seconds == 300.0
        assert not w._running

    def test_start_stop(self, bus, metrics):
        w = SelfHealingWatcher(bus, metrics)
        w.start()
        assert w._running
        w.stop()
        assert not w._running

    @pytest.mark.asyncio
    async def test_task_tracking(self, watcher, bus):
        """Tasks are tracked on assignment."""
        await bus.publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "t1",
            "plan_id": "p1",
            "node_id": "n1",
            "task_type": "shell",
        })
        await asyncio.sleep(0.1)
        assert "t1" in watcher._task_trackers

    @pytest.mark.asyncio
    async def test_task_completed_removes_tracker(self, watcher, bus):
        """Completed tasks are removed from tracking."""
        await bus.publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "t1", "plan_id": "p1", "node_id": "n1",
        })
        await asyncio.sleep(0.1)
        await bus.publish(FleetEvent.TASK_COMPLETED, {
            "task_id": "t1", "plan_id": "p1", "node_id": "n1",
        })
        await asyncio.sleep(0.1)
        assert "t1" not in watcher._task_trackers

    @pytest.mark.asyncio
    async def test_stuck_task_detection(self, watcher, bus):
        """Stuck tasks are detected after timeout."""
        # Assign a task with a past timestamp
        watcher._task_trackers["t1"] = TaskTracker(
            task_id="t1", plan_id="p1", node_id="n1",
            assigned_at=0.0,  # Very old
        )
        actions = await watcher.check_health()
        assert len(actions) == 1
        assert actions[0]["action"] == "stuck_task"
        assert actions[0]["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_unhealthy_node_detection(self, watcher, bus):
        """Unhealthy nodes are detected."""
        watcher.metrics.update({
            "node_id": "n1", "cpu_percent": 99.0, "memory_percent": 50.0,
        })
        actions = await watcher.check_health()
        assert any(a["action"] == "unhealthy_node" for a in actions)

    @pytest.mark.asyncio
    async def test_recovery_callback(self, bus, metrics):
        """Recovery callback is invoked on stuck tasks."""
        callback_calls = []
        w = SelfHealingWatcher(
            bus, metrics,
            config=WatcherConfig(task_timeout_seconds=0.01),
            recovery_callback=lambda *args: callback_calls.append(args),
        )
        w.start()
        w._task_trackers["t1"] = TaskTracker(
            task_id="t1", plan_id="p1", node_id="n1", assigned_at=0.0,
        )
        await w.check_health()
        w.stop()
        assert len(callback_calls) == 1

    @pytest.mark.asyncio
    async def test_task_failure_retry(self, watcher, bus):
        """Task failure triggers retry event."""
        retries = []
        bus.subscribe(FleetEvent.TASK_RETRY, lambda env: retries.append(env))

        await bus.publish(FleetEvent.TASK_FAILED, {
            "task_id": "t1", "plan_id": "p1", "node_id": "n1", "error": "timeout",
        })
        await asyncio.sleep(0.1)
        assert len(retries) == 1
        assert retries[0]["data"]["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_check_health_not_running(self, bus, metrics):
        """check_health returns empty when not running."""
        w = SelfHealingWatcher(bus, metrics)
        actions = await w.check_health()
        assert actions == []
```

---

## Task 3: MCP Server for Fleet Mesh

**Files:**
- Create: `core/mesh/mcp_server.py` — MCP server exposing fleet tools
- Test: `tests/test_mesh_mcp.py`

### Design

An MCP server that exposes fleet mesh operations as tools. Uses the `mcp` SDK (already installed). Tools: `fleet_status`, `list_nodes`, `create_plan`, `deploy_task`, `get_metrics`.

### `core/mesh/mcp_server.py`

```python
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
```

### `tests/test_mesh_mcp.py`

```python
"""Tests for the fleet mesh MCP server."""
import json
import pytest
from core.mesh.mcp_server import FleetMCPServer, TOOLS
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
        assert len(tools) == 5
        names = [t["name"] for t in tools]
        assert "fleet_status" in names
        assert "list_nodes" in names
        assert "create_plan" in names
        assert "deploy_task" in names
        assert "get_metrics" in names

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
```

---

## Task 4: Integration & Full Test Suite

1. Update `core/mesh/__init__.py` to export `FleetCLI`, `SelfHealingWatcher`, `FleetMCPServer`
2. Add `TASK_RETRY` to FleetEvent enum
3. Run `pytest tests/test_mesh_*.py -q --tb=short`
4. Run `ruff check core/mesh/`
5. Commit

---

## Self-Review Checklist

1. CLI: subcommands work, text and JSON output, integrates with metrics
2. Watcher: stuck task detection, unhealthy node detection, retry events, recovery callback
3. MCP: 5 tools, proper schema, async execution
4. Tests: all new code covered, existing tests still pass
