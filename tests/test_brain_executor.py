"""Tests for brain action schemas and executor dispatch (v18.0 — Neuralis Brain Bridge)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.action_executor import ActionExecutor
from core.action_schemas import ACTION_MODELS, validate_action

# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestBrainThinkSchema:
    def test_valid_minimal(self):
        out, errs = validate_action({"action": "brain_think", "content": "some fact"})
        assert errs == []
        assert out["content"] == "some fact"
        assert out["region"] == "knowledge"  # default

    def test_valid_with_region(self):
        out, errs = validate_action(
            {"action": "brain_think", "content": "pref", "region": "preference"}
        )
        assert errs == []
        assert out["region"] == "preference"

    def test_missing_content(self):
        _, errs = validate_action({"action": "brain_think"})
        assert errs

    def test_empty_content_rejected(self):
        _, errs = validate_action({"action": "brain_think", "content": ""})
        assert errs

    def test_invalid_region_rejected(self):
        _, errs = validate_action({"action": "brain_think", "content": "x", "region": "garbage"})
        assert errs

    def test_all_valid_regions(self):
        for region in ("knowledge", "context", "preference", "decision"):
            out, errs = validate_action({"action": "brain_think", "content": "x", "region": region})
            assert errs == [], f"region={region!r} should be valid"


class TestBrainRecallSchema:
    def test_valid(self):
        out, errs = validate_action({"action": "brain_recall", "context": "dns failover"})
        assert errs == []
        assert out["context"] == "dns failover"

    def test_missing_context(self):
        _, errs = validate_action({"action": "brain_recall"})
        assert errs

    def test_empty_context_rejected(self):
        _, errs = validate_action({"action": "brain_recall", "context": ""})
        assert errs


class TestBrainSearchSchema:
    def test_valid(self):
        out, errs = validate_action({"action": "brain_search", "q": "sonicwall"})
        assert errs == []
        assert out["q"] == "sonicwall"

    def test_missing_q(self):
        _, errs = validate_action({"action": "brain_search"})
        assert errs

    def test_empty_q_rejected(self):
        _, errs = validate_action({"action": "brain_search", "q": ""})
        assert errs


class TestBrainStatsSchema:
    def test_valid_no_params(self):
        out, errs = validate_action({"action": "brain_stats"})
        assert errs == []

    def test_extra_fields_ignored(self):
        out, errs = validate_action({"action": "brain_stats", "extra": "ignored"})
        assert errs == []


class TestBrainFireSchema:
    def test_valid(self):
        out, errs = validate_action({"action": "brain_fire", "neuron_id": 42})
        assert errs == []
        assert out["neuron_id"] == 42

    def test_missing_neuron_id(self):
        _, errs = validate_action({"action": "brain_fire"})
        assert errs

    def test_zero_neuron_id_rejected(self):
        _, errs = validate_action({"action": "brain_fire", "neuron_id": 0})
        assert errs

    def test_negative_neuron_id_rejected(self):
        _, errs = validate_action({"action": "brain_fire", "neuron_id": -1})
        assert errs

    def test_minimum_valid_id(self):
        out, errs = validate_action({"action": "brain_fire", "neuron_id": 1})
        assert errs == []


# ---------------------------------------------------------------------------
# ACTION_MODELS registry completeness
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_all_brain_keys_in_action_models(self):
        for key in ("brain_think", "brain_recall", "brain_search", "brain_stats", "brain_fire"):
            assert key in ACTION_MODELS, f"{key!r} missing from ACTION_MODELS"


# ---------------------------------------------------------------------------
# Executor dispatch
# ---------------------------------------------------------------------------


@pytest.fixture
def executor():
    return ActionExecutor()


class TestBrainDispatchTable:
    def test_all_brain_keys_in_dispatch_table(self, executor):
        dt = executor._dispatch_table
        for key in ("brain_think", "brain_recall", "brain_search", "brain_stats", "brain_fire"):
            assert key in dt, f"{key!r} missing from _dispatch_table"


class TestBrainThinkDispatch:
    def test_success(self, executor):
        mock_result = {"neuron": {"id": 5, "content": "test fact"}}
        with patch("core.brain.think", return_value=mock_result):
            result = executor.execute_sync({"action": "brain_think", "content": "test fact"})
        assert result["success"] is True
        assert result["op"] == "brain_think"
        assert result["neuron_id"] == 5

    def test_unavailable_graceful(self, executor):
        from core.brain.client import BrainUnavailableError

        with patch("core.brain.think", side_effect=BrainUnavailableError("down")):
            result = executor.execute_sync({"action": "brain_think", "content": "test"})
        assert result["success"] is False
        assert result["error"] == "brain_unavailable"

    def test_brain_error_graceful(self, executor):
        from core.brain.client import BrainError

        with patch("core.brain.think", side_effect=BrainError("bad response")):
            result = executor.execute_sync({"action": "brain_think", "content": "test"})
        assert result["success"] is False
        assert result["error"] == "brain_error"

    def test_region_forwarded(self, executor):
        with patch("core.brain.think", return_value={"neuron": {"id": 1}}) as mock_think:
            executor.execute_sync(
                {"action": "brain_think", "content": "pref", "region": "preference"}
            )
        mock_think.assert_called_once()
        _, kwargs = mock_think.call_args
        assert kwargs.get("region") == "preference"


class TestBrainRecallDispatch:
    def test_success(self, executor):
        # handler computes count = len(direct) + len(associated)
        mock_result = {"direct": [{"content": "remembered"}], "associated": []}
        with patch("core.brain.recall", return_value=mock_result):
            result = executor.execute_sync({"action": "brain_recall", "context": "ha failover"})
        assert result["success"] is True
        assert result["op"] == "brain_recall"
        assert result["count"] == 1

    def test_unavailable_graceful(self, executor):
        from core.brain.client import BrainUnavailableError

        with patch("core.brain.recall", side_effect=BrainUnavailableError("down")):
            result = executor.execute_sync({"action": "brain_recall", "context": "x"})
        assert result["success"] is False
        assert result["error"] == "brain_unavailable"


class TestBrainSearchDispatch:
    def test_success(self, executor):
        # handler uses result.get("count", len(result.get("results", [])))
        mock_result = {"count": 1, "results": [{"id": 1, "content": "found"}]}
        with patch("core.brain.search", return_value=mock_result):
            result = executor.execute_sync({"action": "brain_search", "q": "sonicwall"})
        assert result["success"] is True
        assert result["op"] == "brain_search"
        assert result["count"] == 1

    def test_unavailable_graceful(self, executor):
        from core.brain.client import BrainUnavailableError

        with patch("core.brain.search", side_effect=BrainUnavailableError("down")):
            result = executor.execute_sync({"action": "brain_search", "q": "x"})
        assert result["success"] is False
        assert result["error"] == "brain_unavailable"


class TestBrainStatsDispatch:
    def test_success(self, executor):
        # handler extracts totals = result.get("totals", {}) then .get("neurons"/"synapses")
        mock_result = {"totals": {"neurons": 100, "synapses": 500}}
        with patch("core.brain.stats", return_value=mock_result):
            result = executor.execute_sync({"action": "brain_stats"})
        assert result["success"] is True
        assert result["op"] == "brain_stats"
        assert result["neurons"] == 100
        assert result["synapses"] == 500

    def test_unavailable_graceful(self, executor):
        from core.brain.client import BrainUnavailableError

        with patch("core.brain.stats", side_effect=BrainUnavailableError("down")):
            result = executor.execute_sync({"action": "brain_stats"})
        assert result["success"] is False
        assert result["error"] == "brain_unavailable"


class TestBrainFireDispatch:
    def test_success(self, executor):
        mock_result = {"fired": True, "neuron_id": 42}
        with patch("core.brain.fire", return_value=mock_result) as mock_fire:
            result = executor.execute_sync({"action": "brain_fire", "neuron_id": 42})
        assert result["success"] is True
        assert result["op"] == "brain_fire"
        mock_fire.assert_called_once_with(neuron_id=42)

    def test_unavailable_graceful(self, executor):
        from core.brain.client import BrainUnavailableError

        with patch("core.brain.fire", side_effect=BrainUnavailableError("down")):
            result = executor.execute_sync({"action": "brain_fire", "neuron_id": 7})
        assert result["success"] is False
        assert result["error"] == "brain_unavailable"

    def test_neuron_id_passed_correctly(self, executor):
        with patch("core.brain.fire", return_value={"fired": True, "neuron_id": 99}) as mock_fire:
            executor.execute_sync({"action": "brain_fire", "neuron_id": 99})
        mock_fire.assert_called_once_with(neuron_id=99)
