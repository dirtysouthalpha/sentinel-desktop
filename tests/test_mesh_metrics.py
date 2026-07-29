"""Tests for fleet observability metrics."""
import asyncio
from unittest.mock import MagicMock, patch

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator, MetricsCollector, MetricsReporter, NodeMetrics


class TestNodeMetrics:
    def test_default_construction(self):
        m = NodeMetrics(node_id="n1")
        assert m.node_id == "n1"
        assert m.cpu_percent == 0.0
        assert m.memory_percent == 0.0
        assert m.tasks_active == 0

    def test_to_dict(self):
        metrics = NodeMetrics(node_id="n1", cpu_percent=50.0, memory_percent=75.0)
        d = metrics.to_dict()
        assert d["node_id"] == "n1"
        assert d["cpu_percent"] == 50.0
        assert d["memory_percent"] == 75.0
        assert "timestamp" in d
        assert "uptime_seconds" in d


class TestMetricsCollector:
    def test_collect(self):
        collector = MetricsCollector("test-node")
        metrics = collector.collect(tasks_active=3, tasks_completed=10)
        assert metrics.node_id == "test-node"
        assert metrics.tasks_active == 3
        assert metrics.tasks_completed == 10
        assert metrics.cpu_percent >= 0
        assert metrics.memory_percent >= 0

    def test_collect_with_psutil(self):
        """collect() uses psutil when available."""
        collector = MetricsCollector("n1")
        metrics = collector.collect()
        assert metrics.node_id == "n1"
        assert metrics.timestamp > 0
        assert metrics.uptime_seconds >= 0

    def test_collect_import_error_fallback(self):
        """collect() gracefully handles psutil import failure."""
        collector = MetricsCollector("n1")
        with patch.dict("sys.modules", {"psutil": None}):
            metrics = collector.collect()
        assert metrics.node_id == "n1"
        assert metrics.cpu_percent == 0.0
        assert metrics.memory_percent == 0.0
        assert metrics.uptime_seconds >= 0


class TestMetricsReporter:
    def test_construct(self):
        bus = EventBus()
        reporter = MetricsReporter("n1", bus, interval_seconds=0.5)
        assert reporter.node_id == "n1"
        assert reporter.interval == 0.5
        assert reporter._running is False

    def test_stop(self):
        bus = EventBus()
        reporter = MetricsReporter("n1", bus)
        reporter._running = True
        reporter.stop()
        assert reporter._running is False

    def test_start_publishes_event(self):
        """start() publishes NODE_METRICS events."""
        bus = EventBus()
        received = []
        bus.subscribe(FleetEvent.NODE_METRICS, lambda env: received.append(env))

        reporter = MetricsReporter("n1", bus, interval_seconds=0.1)

        async def run():
            task = asyncio.create_task(reporter.start())
            await asyncio.sleep(0.3)
            reporter.stop()
            await task

        asyncio.run(run())
        assert len(received) >= 1
        assert received[0]["type"] == FleetEvent.NODE_METRICS
        assert received[0]["data"]["node_id"] == "n1"

    def test_task_counter(self):
        """MetricsReporter uses task_counter callback."""
        bus = EventBus()
        received = []
        bus.subscribe(FleetEvent.NODE_METRICS, lambda env: received.append(env))

        counter = MagicMock(return_value=(5, 20))
        reporter = MetricsReporter("n1", bus, interval_seconds=0.1, task_counter=counter)

        async def run():
            task = asyncio.create_task(reporter.start())
            await asyncio.sleep(0.25)
            reporter.stop()
            await task

        asyncio.run(run())
        assert len(received) >= 1
        assert received[0]["data"]["tasks_active"] == 5
        assert received[0]["data"]["tasks_completed"] == 20


class TestFleetMetricsAggregator:
    def test_update_and_summary(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 50.0, "memory_percent": 60.0})
        agg.update({"node_id": "n2", "cpu_percent": 30.0, "memory_percent": 40.0})

        summary = agg.get_fleet_summary()
        assert summary["total_nodes"] == 2
        assert summary["avg_cpu"] == 40.0
        assert summary["avg_memory"] == 50.0

    def test_empty_summary(self):
        agg = FleetMetricsAggregator()
        summary = agg.get_fleet_summary()
        assert summary["total_nodes"] == 0
        assert summary["healthy_nodes"] == 0

    def test_get_stuck_nodes(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 98.0, "memory_percent": 50.0})
        agg.update({"node_id": "n2", "cpu_percent": 10.0, "memory_percent": 20.0})
        stuck = agg.get_stuck_nodes()
        assert "n1" in stuck
        assert "n2" not in stuck

    def test_healthy_nodes_count(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 10.0, "memory_percent": 20.0})
        agg.update({"node_id": "n2", "cpu_percent": 98.0, "memory_percent": 50.0})
        summary = agg.get_fleet_summary()
        assert summary["healthy_nodes"] == 1

    def test_total_tasks(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "tasks_active": 3, "tasks_completed": 10})
        agg.update({"node_id": "n2", "tasks_active": 2, "tasks_completed": 5})
        summary = agg.get_fleet_summary()
        assert summary["total_tasks_active"] == 5
        assert summary["total_tasks_completed"] == 15

    def test_update_overwrites(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 10.0})
        agg.update({"node_id": "n1", "cpu_percent": 90.0})
        summary = agg.get_fleet_summary()
        assert summary["avg_cpu"] == 90.0
        assert summary["total_nodes"] == 1

    def test_nodes_dict_in_summary(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 25.0})
        summary = agg.get_fleet_summary()
        assert "n1" in summary["nodes"]
        assert summary["nodes"]["n1"]["cpu_percent"] == 25.0
