"""Tests for the per-action-type trust dial."""
import pytest
from core.mesh.trust_dial import TrustDial, TrustLevel, ActionType


class TestTrustDial:
    def test_default_trust_levels(self):
        dial = TrustDial()
        assert dial.get_level(ActionType.SAFE) == TrustLevel.EXECUTE
        assert dial.get_level(ActionType.DESTRUCTIVE) == TrustLevel.PROPOSE
        assert dial.get_level(ActionType.IRREVERSIBLE) == TrustLevel.PROPOSE

    def test_set_trust_level(self):
        dial = TrustDial()
        dial.set_level(ActionType.DESTRUCTIVE, TrustLevel.EXECUTE)
        assert dial.get_level(ActionType.DESTRUCTIVE) == TrustLevel.EXECUTE

    def test_can_execute_safe(self):
        dial = TrustDial()
        assert dial.can_execute(ActionType.SAFE) is True

    def test_cannot_execute_destructive_by_default(self):
        dial = TrustDial()
        assert dial.can_execute(ActionType.DESTRUCTIVE) is False

    def test_can_execute_destructive_when_trusted(self):
        dial = TrustDial()
        dial.set_level(ActionType.DESTRUCTIVE, TrustLevel.EXECUTE)
        assert dial.can_execute(ActionType.DESTRUCTIVE) is True

    def test_can_always_propose(self):
        dial = TrustDial()
        assert dial.can_propose(ActionType.SAFE) is True
        assert dial.can_propose(ActionType.DESTRUCTIVE) is True
        assert dial.can_propose(ActionType.IRREVERSIBLE) is True
