"""Tests for the self-recovery ladder."""
from __future__ import annotations

from core.mesh.event_bus import EventBus
from core.mesh.metrics import FleetMetricsAggregator
from core.mesh.recovery import RecoveryManager
from core.mesh.self_recovery import SelfRecoveryLadder


class TestSelfRecoveryLadder:
    def test_construct(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        assert ladder.bus is bus
        assert isinstance(ladder.recovery, RecoveryManager)

    def test_start_stop(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        ladder.start()
        ladder.stop()

    def test_recovery_log_empty(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        assert ladder.get_recovery_log() == []

    def test_recover_unhealthy_node(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        ladder._recover_unhealthy_node("n1")
        log = ladder.get_recovery_log()
        assert len(log) == 1
        assert log[0]["action"] == "drain"
        assert log[0]["node_id"] == "n1"

    def test_recover_stuck_task_no_fallback(self):
        bus = EventBus()
        metrics = FleetMetricsAggregator()
        ladder = SelfRecoveryLadder(bus, metrics)
        ladder._recover_stuck_task("t1", {"node_id": "n1", "plan_id": "p1"})
        log = ladder.get_recovery_log()
        assert len(log) == 1
        assert log[0]["action"] == "escalate"
