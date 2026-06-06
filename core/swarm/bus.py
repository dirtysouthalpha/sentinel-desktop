"""Sentinel Desktop v7.0 — Message Bus.

Inter-agent communication via asyncio queues. Thread-safe, supports
publish/subscribe patterns for broadcasting results and status updates.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MessagePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentMessage:
    """A message passed between agents.

    Attributes:
        id: Unique message ID.
        sender: Agent ID that sent the message.
        recipient: Agent ID to receive (or "broadcast" for all).
        msg_type: Message type (task, result, status, error, alert).
        payload: Message content (arbitrary dict).
        priority: Message priority.
        timestamp: Creation timestamp (monotonic).
        parent_id: ID of the message this is a reply to.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sender: str = ""
    recipient: str = "broadcast"
    msg_type: str = "status"
    payload: dict[str, Any] = field(default_factory=dict)
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: float = field(default_factory=time.monotonic)
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "type": self.msg_type,
            "priority": self.priority.value,
            "payload": self.payload,
        }


class MessageBus:
    """Async message bus for inter-agent communication.

    Agents subscribe to message types and receive them via asyncio queues.
    Supports both direct messaging and broadcast patterns.
    """

    def __init__(self, max_queue_size: int = 100) -> None:
        self._queues: dict[str, asyncio.Queue[AgentMessage]] = {}
        self._subscriptions: dict[str, set[str]] = {}  # msg_type → set of agent_ids
        self._max_queue_size = max_queue_size
        self._history: list[AgentMessage] = []
        self._history_max = 1000

    def register(self, agent_id: str) -> asyncio.Queue[AgentMessage]:
        """Register an agent and return its message queue."""
        queue: asyncio.Queue[AgentMessage] = asyncio.Queue(maxsize=self._max_queue_size)
        self._queues[agent_id] = queue
        return queue

    def unregister(self, agent_id: str) -> None:
        """Remove an agent from the bus."""
        self._queues.pop(agent_id, None)
        for subscribers in self._subscriptions.values():
            subscribers.discard(agent_id)

    def subscribe(self, agent_id: str, msg_type: str) -> None:
        """Subscribe an agent to a message type."""
        if msg_type not in self._subscriptions:
            self._subscriptions[msg_type] = set()
        self._subscriptions[msg_type].add(agent_id)

    async def send(self, message: AgentMessage) -> int:
        """Send a message. Returns the number of agents that received it."""
        recipients = 0

        if message.recipient == "broadcast":
            # Send to all subscribers of this message type
            subscribers = self._subscriptions.get(message.msg_type, set())
            for agent_id in subscribers:
                queue = self._queues.get(agent_id)
                if queue and agent_id != message.sender:
                    try:
                        queue.put_nowait(message)
                        recipients += 1
                    except asyncio.QueueFull:
                        logger.warning("Queue full for agent %s, dropping message", agent_id)
        else:
            # Direct message
            queue = self._queues.get(message.recipient)
            if queue:
                try:
                    queue.put_nowait(message)
                    recipients = 1
                except asyncio.QueueFull:
                    logger.warning("Queue full for agent %s, dropping message", message.recipient)

        # Record in history
        self._history.append(message)
        if len(self._history) > self._history_max:
            self._history = self._history[-self._history_max:]

        return recipients

    async def receive(self, agent_id: str, timeout: float = 1.0) -> AgentMessage | None:
        """Receive a message for an agent (with timeout)."""
        queue = self._queues.get(agent_id)
        if queue is None:
            return None
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    @property
    def registered_agents(self) -> list[str]:
        return list(self._queues.keys())

    @property
    def history(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self._history[-100:]]

    def clear(self) -> None:
        """Clear all queues and history (for testing)."""
        self._queues.clear()
        self._subscriptions.clear()
        self._history.clear()
