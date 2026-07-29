"""WebSocket pub/sub event bus for the fleet mesh.

In-process pub/sub for single-node operation. The WebSocket transport
layer (Task 8) wraps this for cross-node delivery. This design keeps
the core bus testable without network I/O.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.mesh.transport import WebSocketTransport

logger = logging.getLogger(__name__)


class FleetEvent(str, Enum):
    """Fleet event types published on the mesh event bus."""
    # Lifecycle
    NODE_HEARTBEAT = "fleet.event.node.heartbeat"
    NODE_JOINED = "fleet.event.node.joined"
    NODE_LEFT = "fleet.event.node.left"
    # Tasks
    TASK_CREATED = "fleet.event.task.created"
    TASK_ASSIGNED = "fleet.event.task.assigned"
    TASK_RUNNING = "fleet.event.task.running"
    TASK_PROGRESS = "fleet.event.task.progress"
    TASK_COMPLETED = "fleet.event.task.completed"
    TASK_FAILED = "fleet.event.task.failed"
    TASK_RETRY = "fleet.event.task.retry"
    # Plans
    PLAN_CREATED = "fleet.event.plan.created"
    PLAN_UPDATED = "fleet.event.plan.updated"
    PLAN_COMPLETED = "fleet.event.plan.completed"
    # Memory
    MEMORY_STORED = "fleet.event.memory.stored"
    MEMORY_RECALLED = "fleet.event.memory.recalled"
    # Metrics
    NODE_METRICS = "fleet.event.node.metrics"
    # Escalation
    ESCALATION_DAILY = "fleet.event.escalation.daily"
    ESCALATION_CRITICAL = "fleet.event.escalation.critical"


EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class EventBus:
    """In-process async event bus.

    Subscribers register a handler for an event type. `publish` delivers
    the event to all matching subscribers concurrently.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._transport: WebSocketTransport | None = None

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register *handler* for *event_type*."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove *handler* from *event_type*."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    def set_transport(self, transport: WebSocketTransport) -> None:
        """Set the remote transport for cross-node event delivery."""
        self._transport = transport
        transport.on_remote_event(self._handle_remote_event)

    async def _handle_remote_event(self, envelope: dict[str, Any]) -> None:
        """Deliver a remote event to local subscribers."""
        event_type = envelope.get("type")
        if event_type and event_type in self._subscribers:
            results = await asyncio.gather(
                *[self._safe_call(h, envelope) for h in self._subscribers[event_type]],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Handler error for %s: %s", event_type, result)

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers.

        Data is wrapped in an envelope containing the event type, a unique
        id, and a UTC timestamp. Handlers run concurrently; exceptions are
        logged but don't block.
        """
        handlers = list(self._subscribers.get(event_type, []))
        if not handlers:
            return

        envelope: dict[str, Any] = {
            "type": event_type,
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        results = await asyncio.gather(
            *[self._safe_call(h, envelope) for h in handlers],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Event handler error: %s", result)

        # Forward to remote peers
        if self._transport:
            await self._transport.send_to_peers(envelope)

    @staticmethod
    async def _safe_call(handler: EventHandler, data: dict[str, Any]) -> None:
        """Call handler, catching exceptions."""
        result = handler(data)
        if asyncio.iscoroutine(result):
            await result
