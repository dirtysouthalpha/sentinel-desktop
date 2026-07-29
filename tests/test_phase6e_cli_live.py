"""Phase 6E: Fleet CLI wired to live mesh control."""
from __future__ import annotations

import json

import pytest

from core.mesh.cli import FleetCLI
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator


class TestCLILive:
    @pytest.fixture
    def live_cli(self):
        """CLI with a real EventBus and MetricsAggregator."""
        bus = EventBus()
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "node-1", "cpu_percent": 30.0, "memory_percent": 45.0, "tasks_active": 2, "tasks_completed": 10})
        cli = FleetCLI(bus=bus, metrics=agg)
        return cli, bus

    def test_status_returns_live_data(self, live_cli):
        cli, _ = live_cli
        output = cli.execute(["status"])
        assert "Total nodes: 1" in output
        assert "Avg CPU: 30.0%" in output

    def test_nodes_returns_live_nodes(self, live_cli):
        cli, _ = live_cli
        output = cli.execute(["nodes"])
        assert "node-1" in output
        assert "CPU 30%" in output

    def test_deploy_publishes_task(self, live_cli):
        """CLI deploy command publishes TASK_ASSIGNED to the live bus."""
        cli, bus = live_cli
        received = []
        bus.subscribe(FleetEvent.TASK_ASSIGNED, lambda env: received.append(env))
        output = cli.execute(["deploy", "TestPlan", "--tasks", json.dumps([{"id": "t1", "type": "shell", "goal": "echo hi"}])])
        assert "deployed" in output.lower()
        assert len(received) == 1
        assert received[0]["data"]["task_id"] == "t1"

    def test_inject_failure_publishes_stuck_task(self, live_cli):
        """CLI inject-failure command publishes a task designed to fail."""
        cli, bus = live_cli
        received = []
        bus.subscribe(FleetEvent.TASK_ASSIGNED, lambda env: received.append(env))
        output = cli.execute(["inject-failure", "node-1", "--cmd", "exit 1"])
        assert "injected" in output.lower()
        assert len(received) == 1

    def test_trust_get_set(self, live_cli):
        """CLI trust command gets and sets trust dial levels."""
        cli, _ = live_cli
        output = cli.execute(["trust"])
        assert "destructive" in output.lower()
        output = cli.execute(["trust", "--set", "destructive", "execute"])
        assert "set" in output.lower()
