"""Server/Enterprise modules — event bus, scaling, auth, metrics."""

# Auth will be added in Phase 6
from .auth import AuthManager, Permission, Role
from .event_bus import (
    EVENT_CUSTOM,
    EVENT_FILE_CREATED,
    EVENT_FILE_DELETED,
    EVENT_FILE_MODIFIED,
    EVENT_PROCESS_STARTED,
    EVENT_PROCESS_STOPPED,
    EVENT_SCHEDULE_FIRED,
    EVENT_WEBHOOK_RECEIVED,
    EVENT_WINDOW_CLOSED,
    EVENT_WINDOW_CREATED,
    Event,
    EventBus,
    EventRule,
)
from .scaling import ScalingController, ServerMetrics, Task

__all__ = [
    "Event",
    "EventRule",
    "EventBus",
    "EVENT_FILE_CREATED",
    "EVENT_FILE_MODIFIED",
    "EVENT_FILE_DELETED",
    "EVENT_SCHEDULE_FIRED",
    "EVENT_WEBHOOK_RECEIVED",
    "EVENT_PROCESS_STARTED",
    "EVENT_PROCESS_STOPPED",
    "EVENT_WINDOW_CREATED",
    "EVENT_WINDOW_CLOSED",
    "EVENT_CUSTOM",
    "Task",
    "ServerMetrics",
    "ScalingController",
    "AuthManager",
    "Role",
    "Permission",
]
