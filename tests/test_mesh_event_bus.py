"""Tests for the WebSocket event bus."""
import asyncio
import pytest
from core.mesh.event_bus import EventBus, FleetEvent


class TestEventBus:
    def test_event_types_defined(self):
        """FleetEvent enum covers all required event types."""
        assert FleetEvent.NODE_HEARTBEAT == "fleet.event.node.heartbeat"
        assert FleetEvent.TASK_COMPLETED == "fleet.event.task.completed"
        assert FleetEvent.TASK_FAILED == "fleet.event.task.failed"
        assert FleetEvent.PLAN_CREATED == "fleet.event.plan.created"
        assert FleetEvent.MEMORY_STORED == "fleet.event.memory.stored"
        assert FleetEvent.ESCALATION_DAILY == "fleet.event.escalation.daily"

    @pytest.mark.asyncio
    async def test_publish_subscribe_in_process(self):
        """Subscriber receives events published on the bus."""
        bus = EventBus()
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        bus.subscribe("fleet.event.task.completed", handler)
        await bus.publish("fleet.event.task.completed", {"task_id": "t1", "result": "ok"})

        assert len(received) == 1
        assert received[0]["type"] == "fleet.event.task.completed"
        assert "event_id" in received[0]
        assert "timestamp" in received[0]
        assert received[0]["data"]["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_subscriber_receives_only_its_events(self):
        """Subscriber does not receive events it didn't subscribe to."""
        bus = EventBus()
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        bus.subscribe("fleet.event.task.completed", handler)
        await bus.publish("fleet.event.task.failed", {"task_id": "t2"})

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """All subscribers for an event type receive it."""
        bus = EventBus()
        a: list[dict] = []
        b: list[dict] = []

        bus.subscribe("fleet.event.node.heartbeat", lambda evt: a.append(evt))
        bus.subscribe("fleet.event.node.heartbeat", lambda evt: b.append(evt))
        await bus.publish("fleet.event.node.heartbeat", {"node_id": "n1"})

        assert len(a) == 1
        assert len(b) == 1

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_block_others(self):
        """A raising handler does not prevent other subscribers from receiving the event."""
        bus = EventBus()
        received: list[dict] = []

        async def bad_handler(event: dict) -> None:
            raise RuntimeError("boom")

        async def good_handler(event: dict) -> None:
            received.append(event)

        bus.subscribe("fleet.event.task.created", bad_handler)
        bus.subscribe("fleet.event.task.created", good_handler)
        await bus.publish("fleet.event.task.created", {"task_id": "t3"})

        assert len(received) == 1
        assert received[0]["data"]["task_id"] == "t3"

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Unsubscribed handler no longer receives events."""
        bus = EventBus()
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        bus.subscribe("fleet.event.plan.created", handler)
        bus.unsubscribe("fleet.event.plan.created", handler)
        await bus.publish("fleet.event.plan.created", {"plan_id": "p1"})

        assert len(received) == 0
