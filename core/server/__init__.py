"""Server/Enterprise modules — event bus, scaling, auth, metrics."""

from .event_bus import (
    Event, EventRule, EventBus,
    EVENT_FILE_CREATED, EVENT_FILE_MODIFIED, EVENT_FILE_DELETED,
    EVENT_SCHEDULE_FIRED, EVENT_WEBHOOK_RECEIVED,
    EVENT_PROCESS_STARTED, EVENT_PROCESS_STOPPED,
    EVENT_WINDOW_CREATED, EVENT_WINDOW_CLOSED, EVENT_CUSTOM,
)
from .scaling import Task, ServerMetrics, ScalingController

# Auth will be added in Phase 6
from .auth import AuthManager, Role, Permission

__all__ = [
    "Event", "EventRule", "EventBus",
    "EVENT_FILE_CREATED", "EVENT_FILE_MODIFIED", "EVENT_FILE_DELETED",
    "EVENT_SCHEDULE_FIRED", "EVENT_WEBHOOK_RECEIVED",
    "EVENT_PROCESS_STARTED", "EVENT_PROCESS_STOPPED",
    "EVENT_WINDOW_CREATED", "EVENT_WINDOW_CLOSED", "EVENT_CUSTOM",
    "Task", "ServerMetrics", "ScalingController",
    "AuthManager", "Role", "Permission",
]
