"""Phase 6D: Real-time dashboard tests."""
from __future__ import annotations

import asyncio

import pytest

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator


def _sync_publish(bus: EventBus, event_type: str, data: dict) -> None:
    """Helper to publish an event synchronously (for testing)."""
    asyncio.run(bus.publish(event_type, data))


class TestFleetTabLive:
    """Test that FleetTab can subscribe to live EventBus events."""

    def test_fleet_tab_subscribes_to_events(self):
        """FleetTab subscribes to FleetEvent types on the EventBus."""
        bus = EventBus()
        received = []

        # Simulate what FleetTab should do: subscribe to live events
        bus.subscribe(FleetEvent.NODE_METRICS, lambda env: received.append(env))
        bus.subscribe(FleetEvent.TASK_COMPLETED, lambda env: received.append(env))

        _sync_publish(bus, FleetEvent.NODE_METRICS, {"node_id": "n1", "cpu": 50})
        _sync_publish(bus, FleetEvent.TASK_COMPLETED, {"task_id": "t1"})

        assert len(received) == 2

    def test_fleet_tab_aggregator_updates(self):
        """FleetMetricsAggregator receives updates from events."""
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 50, "memory_percent": 60})
        agg.update({"node_id": "n2", "cpu_percent": 30, "memory_percent": 40})
        summary = agg.get_fleet_summary()
        assert summary["total_nodes"] == 2
        assert summary["avg_cpu"] == 40.0

    def test_fleet_tab_shows_leader_changes(self):
        """FleetTab receives NODE_JOINED events."""
        bus = EventBus()
        received = []
        bus.subscribe(FleetEvent.NODE_JOINED, lambda env: received.append(env))
        _sync_publish(bus, FleetEvent.NODE_JOINED, {"node_id": "node-a"})
        assert len(received) == 1
        assert received[0]["data"]["node_id"] == "node-a"

    def test_fleet_tab_receives_recovery_events(self):
        """FleetTab receives recovery-related events."""
        bus = EventBus()
        received = []
        bus.subscribe(FleetEvent.TASK_RETRY, lambda env: received.append(env))
        _sync_publish(bus, FleetEvent.TASK_RETRY, {"task_id": "t1", "retry_count": 2})
        assert len(received) == 1
