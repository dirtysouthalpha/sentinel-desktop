"""Tests for the fleet mesh CLI."""
import argparse
import json

from core.mesh.cli import FleetCLI, create_parser
from core.mesh.metrics import FleetMetricsAggregator


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
