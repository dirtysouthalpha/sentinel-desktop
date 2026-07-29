"""Per-action-type autonomy levels (trust dial)."""
from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class TrustLevel(str, Enum):
    PROPOSE = "propose"
    EXECUTE = "execute"


class ActionType(str, Enum):
    SAFE = "safe"
    DESTRUCTIVE = "destructive"
    IRREVERSIBLE = "irreversible"


class TrustDial:
    def __init__(self) -> None:
        self._levels: dict[ActionType, TrustLevel] = {
            ActionType.SAFE: TrustLevel.EXECUTE,
            ActionType.DESTRUCTIVE: TrustLevel.PROPOSE,
            ActionType.IRREVERSIBLE: TrustLevel.PROPOSE,
        }

    def get_level(self, action_type: ActionType) -> TrustLevel:
        return self._levels.get(action_type, TrustLevel.PROPOSE)

    def set_level(self, action_type: ActionType, level: TrustLevel) -> None:
        self._levels[action_type] = level
        logger.info("Trust dial: %s -> %s", action_type.value, level.value)

    def can_execute(self, action_type: ActionType) -> bool:
        return self._levels.get(action_type) == TrustLevel.EXECUTE

    def can_propose(self, action_type: ActionType) -> bool:
        return True

    def classify_action(self, action_name: str) -> ActionType:
        """Classify an action name into SAFE, DESTRUCTIVE, or IRREVERSIBLE."""
        safe_actions = {
            "type", "click", "double_click", "right_click", "move",
            "scroll", "wait", "screenshot", "read", "get_text",
            "find", "focus", "copy", "paste", "hotkey", "key",
            "press", "alert", "notify", "speak", "ocr",
        }
        destructive_actions = {
            "delete", "kill", "remove", "rename", "move_file",
            "write_file", "create_file", "create_dir",
            "run", "execute", "shell", "powershell",
            "restart", "shutdown", "terminate",
        }
        irreversible_actions = {
            "format", "wipe", "factory_reset", "unlink",
            "destroy", "purge", "clean_disk",
        }
        if action_name in safe_actions:
            return ActionType.SAFE
        if action_name in destructive_actions:
            return ActionType.DESTRUCTIVE
        if action_name in irreversible_actions:
            return ActionType.IRREVERSIBLE
        return ActionType.SAFE  # Default: treat unknown actions as safe
