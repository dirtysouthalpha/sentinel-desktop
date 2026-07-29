"""Self-recovery ladder for the fleet mesh."""
from __future__ import annotations

import logging
import re
from enum import Enum

from core.mesh.node import MeshNode
from core.mesh.task_graph import Task

logger = logging.getLogger(__name__)


class FailureType(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


_TRANSIENT_PATTERNS = [r"timeout", r"timed out", r"connection.*refused", r"rate.?limit", r"429", r"503", r"502", r"504", r"temporary", r"unavailable"]
_PERMANENT_PATTERNS = [r"auth", r"unauthorized", r"forbidden", r"403", r"401", r"not found", r"404", r"invalid", r"validation", r"malformed"]
_RESOURCE_PATTERNS = [r"no space", r"disk.?full", r"out of memory", r"oom", r"quota", r"rate.?exceeded", r"too many"]


class RecoveryManager:
    def classify_failure(self, error_message: str) -> FailureType:
        msg = error_message.lower()
        for p in _RESOURCE_PATTERNS:
            if re.search(p, msg):
                return FailureType.RESOURCE
        for p in _PERMANENT_PATTERNS:
            if re.search(p, msg):
                return FailureType.PERMANENT
        for p in _TRANSIENT_PATTERNS:
            if re.search(p, msg):
                return FailureType.TRANSIENT
        return FailureType.UNKNOWN

    def should_retry(self, task: Task, failure_type: FailureType) -> bool:
        if not task.can_retry():
            return False
        if failure_type == FailureType.PERMANENT:
            return False
        return True

    def select_fallback_node(self, current_node_id: str, available_nodes: list[MeshNode], timeout_seconds: float = 30) -> MeshNode | None:
        candidates = [n for n in available_nodes if n.node_id != current_node_id and n.is_alive(timeout_seconds=timeout_seconds)]
        if not candidates:
            return None
        candidates.sort(key=lambda n: n.priority, reverse=True)
        return candidates[0]

    def get_retry_delay(self, retry_count: int, base_delay: float = 1.0) -> float:
        return base_delay * (2 ** retry_count)
