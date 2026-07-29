"""Neuralis-backed cross-session memory for the fleet mesh."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from core.legacy_brain import BrainClient
from core.mesh.task_graph import TaskGraph

logger = logging.getLogger(__name__)

DEFAULT_BRAIN_URL = os.environ.get("NEURALIS_BRAIN_URL", "http://100.64.0.2:8001")


class NeuralisMemory:
    """Stores and retrieves fleet state via the Neuralis brain.

    Each plan checkpoint is a neuron:
    - topic: "orchestrator-checkpoint:<plan_id>"
    - content: JSON with plan metadata + serialized task graph
    - region: "fleet"
    """

    def __init__(self, brain_url: str = DEFAULT_BRAIN_URL, enabled: bool = True) -> None:
        self.brain_url = brain_url
        self.enabled = enabled
        self._brain = None
        if enabled:
            try:
                self._brain = BrainClient(url=brain_url)
                logger.info("Neuralis memory initialized: %s", brain_url)
            except Exception as e:
                logger.warning("Neuralis memory init failed: %s", e)
                self.enabled = False

    def store_checkpoint(self, plan_id: str, name: str, graph: TaskGraph) -> bool:
        """Persist a plan checkpoint to Neuralis."""
        if not self.enabled or not self._brain:
            return False
        try:
            tasks_data = []
            for task in graph.tasks.values():
                tasks_data.append({
                    "id": task.id,
                    "type": task.type,
                    "goal": task.goal,
                    "status": task.status.value,
                    "assigned_node": task.assigned_node,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                    "result": task.result,
                    "error": task.error,
                    "depends_on": task.depends_on,
                    "params": getattr(task, "params", {}),
                })
            checkpoint = {
                "plan_id": plan_id,
                "name": name,
                "tasks": tasks_data,
                "is_complete": graph.is_complete(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._brain.think(
                topic=f"orchestrator-checkpoint:{plan_id}",
                content=json.dumps(checkpoint),
                region="fleet",
            )
            logger.debug("Checkpoint stored for plan %s", plan_id)
            return True
        except Exception as e:
            logger.warning("Failed to store checkpoint for %s: %s", plan_id, e)
            return False

    def load_checkpoint(self, plan_id: str) -> dict[str, Any] | None:
        """Load a specific plan checkpoint."""
        if not self.enabled or not self._brain:
            return None
        try:
            results = self._brain.search(q=f"orchestrator-checkpoint:{plan_id}")
            if not results:
                return None
            # Find exact match
            for neuron in results:
                topic = neuron.get("topic", "")
                if topic == f"orchestrator-checkpoint:{plan_id}":
                    content = neuron.get("content", "{}")
                    if isinstance(content, str):
                        return json.loads(content)
                    return content
            return None
        except Exception as e:
            logger.warning("Failed to load checkpoint for %s: %s", plan_id, e)
            return None

    def find_incomplete_plans(self) -> list[dict[str, Any]]:
        """Find all plans that are not yet complete."""
        if not self.enabled or not self._brain:
            return []
        try:
            results = self._brain.search(q="orchestrator-checkpoint:")
            incomplete = []
            for neuron in results:
                content = neuron.get("content", "{}")
                try:
                    if isinstance(content, str):
                        data = json.loads(content)
                    else:
                        data = content
                    if not data.get("is_complete", True):
                        incomplete.append(data)
                except (json.JSONDecodeError, TypeError):
                    continue
            return incomplete
        except Exception as e:
            logger.warning("Failed to search for incomplete plans: %s", e)
            return []

    def store_event(self, event_type: str, data: dict[str, Any]) -> bool:
        """Store a fleet event as a neuron."""
        if not self.enabled or not self._brain:
            return False
        try:
            content = json.dumps({
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self._brain.think(
                topic=f"fleet-event:{event_type}",
                content=content,
                region="context",
            )
            return True
        except Exception as e:
            logger.warning("Failed to store event: %s", e)
            return False
