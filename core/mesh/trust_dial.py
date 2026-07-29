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
