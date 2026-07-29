"""Tests for the self-healing watcher."""
import asyncio

import pytest

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.metrics import FleetMetricsAggregator
from core.mesh.watcher import SelfHealingWatcher, TaskTracker, WatcherConfig


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
