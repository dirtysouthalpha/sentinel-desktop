"""Phase 6E: Trust dial enforcement tests."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.executor import TaskExecutor
from core.mesh.node import NodeCapabilities
from core.mesh.trust_dial import ActionType, TrustDial, TrustLevel


class TestTrustDial:
    def test_safe_action_can_execute(self):
        dial = TrustDial()
        assert dial.can_execute(ActionType.SAFE) is True

    def test_destructive_action_cannot_execute(self):
        dial = TrustDial()
        assert dial.can_execute(ActionType.DESTRUCTIVE) is False

    def test_irreversible_action_cannot_execute(self):
        dial = TrustDial()
        assert dial.can_execute(ActionType.IRREVERSIBLE) is False

    def test_set_level_to_execute(self):
        dial = TrustDial()
        dial.set_level(ActionType.DESTRUCTIVE, TrustLevel.EXECUTE)
        assert dial.can_execute(ActionType.DESTRUCTIVE) is True

    def test_classify_action_safe_actions(self):
        """Action names like 'type', 'click' are classified as SAFE."""
        dial = TrustDial()
        assert dial.classify_action("type") == ActionType.SAFE
        assert dial.classify_action("click") == ActionType.SAFE
        assert dial.classify_action("wait") == ActionType.SAFE

    def test_classify_action_destructive_actions(self):
        """Action names like 'delete', 'kill' are classified as DESTRUCTIVE."""
        dial = TrustDial()
        assert dial.classify_action("delete") == ActionType.DESTRUCTIVE
        assert dial.classify_action("kill") == ActionType.DESTRUCTIVE
        assert dial.classify_action("remove") == ActionType.DESTRUCTIVE

    def test_classify_action_irreversible_actions(self):
        """Action names like 'format', 'wipe' are classified as IRREVERSIBLE."""
        dial = TrustDial()
        assert dial.classify_action("format") == ActionType.IRREVERSIBLE
        assert dial.classify_action("wipe") == ActionType.IRREVERSIBLE


class TestExecutorTrustDial:
    @pytest.mark.asyncio
    async def test_safe_action_executes(self):
        """A SAFE action task is executed when trust dial allows."""
        bus = EventBus()
        caps = NodeCapabilities()
        executor = TaskExecutor(node_id="n1", bus=bus, capabilities=caps)

        # Patch action_executor to avoid real desktop interaction
        mock_exec = MagicMock()
        mock_exec.execute_sync.return_value = {"status": "ok"}
        executor._executor = mock_exec

        result = await executor._exec_action({
            "task_id": "a1", "goal": "click", "params": {"action": "click", "action_params": {"x": 10, "y": 20}},
        })
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_destructive_action_blocked_without_trust(self):
        """A DESTRUCTIVE action task is blocked when trust dial is at PROPOSE."""
        bus = EventBus()
        caps = NodeCapabilities()
        executor = TaskExecutor(node_id="n1", bus=bus, capabilities=caps)

        with pytest.raises(PermissionError, match="blocked by trust dial"):
            await executor._exec_action({
                "task_id": "d1", "goal": "delete", "params": {"action": "delete", "action_params": {}},
            })
