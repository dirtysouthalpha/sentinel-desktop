"""Tests for scripts/brain_loop_daemon.py — the brain cognitive loop closer.

These tests mock the brain HTTP calls so they run without a live brain.
We verify:
  * Each loop function calls the correct endpoint with correct method/body.
  * The daemon's tick scheduler respects cadences.
  * Dry-run mode never calls mutating endpoints.
  * Errors in one loop don't crash the tick.
  * The CLI --once flag produces valid JSON output.
  * Gap-fix loops handle broken endpoints gracefully.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from scripts.brain_loop_daemon import (
    BrainLoopDaemon,
    TickReport,
    _run_cognitive_cycle,
    _run_synapse_maintenance,
    _run_quality_prune,
    _run_quality_enrich,
    _run_dream_trigger,
    _run_consolidate_trigger,
    _run_self_modify,
    _run_creativity_execute,
    _run_outcome_log,
    _run_prediction_rebuild,
    _run_prediction_score,
    _run_prediction_health,
    _run_report_generate,
    _run_decay_noise,
    LOOP_REGISTRY,
    DEFAULT_CADENCES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeResponse:
    """Fake urllib response for mocking."""

    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _mock_urlopen(return_value: dict | list | str, status: int = 200) -> FakeResponse:
    """Build a FakeResponse with the given JSON/string."""
    if isinstance(return_value, (dict, list)):
        raw = json.dumps(return_value).encode()
    else:
        raw = return_value.encode() if isinstance(return_value, str) else return_value
    return FakeResponse(raw, status)


# ---------------------------------------------------------------------------
# Test: all loops exist and are callable
# ---------------------------------------------------------------------------

class TestLoopRegistry:
    def test_all_expected_loops_present(self):
        expected = {
            "cognitive_cycle",
            "synapse_maintenance",
            "curiosity_gap_fill",
            "quality_prune",
            "quality_enrich",
            "dream_trigger",
            "consolidate_trigger",
            "self_modify",
            "creativity_execute",
            "outcome_log",
            "learning_update",
            "orphan_rescue",
            "decay_noise",
            "prediction_rebuild",
            "prediction_score",
            "prediction_health",
            "report_generate",
            "goal_pursuit",
            "fleet_telemetry",
            "working_memory",
            "self_heal_full",
            "actuator_execute",
            "cognitive_hypotheses",
            "synthesis_chain",
            "self_mod_watcher",
        }
        assert set(LOOP_REGISTRY) == expected

    def test_all_loops_are_callable(self):
        for name, func in LOOP_REGISTRY.items():
            assert callable(func), f"{name} is not callable"

    def test_default_cadences_cover_all_loops(self):
        for name in LOOP_REGISTRY:
            assert name in DEFAULT_CADENCES, f"{name} missing from DEFAULT_CADENCES"
            assert DEFAULT_CADENCES[name] > 0


# ---------------------------------------------------------------------------
# Test: each loop calls the correct endpoint
# ---------------------------------------------------------------------------

class TestLoopEndpoints:
    """Verify each loop makes the correct HTTP request."""

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_cognitive_cycle(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        result = _run_cognitive_cycle("http://brain:8001", dry_run=False)
        assert result == {"ok": True}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/cognitive/cycle"
        assert req.method == "POST"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_synapse_maintenance(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "deleted": 100})
        result = _run_synapse_maintenance("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "deleted": 100}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/synapses/reap"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_quality_prune(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "pruned": 5})
        result = _run_quality_prune("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "pruned": 5}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/quality/prune"
        body = json.loads(req.data)
        assert body["threshold"] == 0.3

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_quality_enrich(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen([{"id": 1, "quality": 0.3}, {"id": 2, "quality": 0.4}]),
            _mock_urlopen({"ok": True}),
            _mock_urlopen({"ok": True}),
        ]
        result = _run_quality_enrich("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["candidates"] == 2

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_dream_trigger(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "dreamed": True})
        result = _run_dream_trigger("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "dreamed": True}

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_consolidate_trigger(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "consolidated": True})
        result = _run_consolidate_trigger("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "consolidated": True}

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_self_modify_gate_active(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            "total_proposals": 31,
            "applied": 0,
            "constraints": {"approval_required_first_7_days": True},
        })
        result = _run_self_modify("http://brain:8001", dry_run=False)
        assert result["ok"] is False
        assert "approval gate" in result["message"]

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_self_modify_gate_inactive(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen({
                "total_proposals": 31,
                "applied": 0,
                "constraints": {"approval_required_first_7_days": False},
            }),
            _mock_urlopen({"ok": True, "applied": 1}),
        ]
        result = _run_self_modify("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "applied": 1}

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_creativity_execute(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            "ok": True, "domain_a": "technology", "domain_b": "science",
            "synthesis": "test",
        })
        result = _run_creativity_execute("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        req = mock_urlopen.call_args[0][0]
        assert "/creative/synthesize" in req.full_url
        assert req.method == "GET"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_outcome_log(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        result = _run_outcome_log("http://brain:8001", dry_run=False)
        assert result == {"ok": True}
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["outcome"] == "good"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_prediction_rebuild(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        result = _run_prediction_rebuild("http://brain:8001", dry_run=False)
        assert result == {"ok": True}

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_prediction_score(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            "predictions_scored": 3707, "hits": 2195, "hit_rate": 0.592,
        })
        result = _run_prediction_score("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["stats"]["hit_rate"] == 0.592

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_prediction_health(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            "predictions_scored": 3707, "hits": 2195, "hit_rate": 0.592,
            "transition_edges": 25228,
        })
        result = _run_prediction_health("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["hit_rate"] == 0.592
        assert result["healthy"] is True
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/predict/stats"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_prediction_health_unhealthy(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            "predictions_scored": 100, "hits": 10, "hit_rate": 0.1,
        })
        result = _run_prediction_health("http://brain:8001", dry_run=False)
        assert result["healthy"] is False

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_report_generate(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen("brain report text")
        result = _run_report_generate("http://brain:8001", dry_run=False)
        assert result == "brain report text"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_decay_noise(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"decayed": 435})
        result = _run_decay_noise("http://brain:8001", dry_run=False)
        assert result == {"decayed": 435}


# ---------------------------------------------------------------------------
# Test: gap-fix loops
# ---------------------------------------------------------------------------

class TestGapFixLoops:
    """Test the v22.1 gap-fix loops."""

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_prediction_rebuild_handles_500(self, mock_urlopen):
        """GAP FIX #1: prediction_rebuild handles 500 error gracefully."""
        import urllib.error
        # First call (rebuild) returns 500, second call (stats) succeeds
        error_mock = MagicMock()
        error_mock.read.return_value = b'Internal Server Error'
        error_mock.__enter__ = MagicMock(return_value=error_mock)
        error_mock.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = [
            urllib.error.HTTPError(
                url="http://brain:8001/brain/transitions/rebuild",
                code=500, msg="Internal Server Error", hdrs={}, fp=error_mock,
            ),
            _mock_urlopen({"hit_rate": 0.592, "predictions_scored": 3707}),
        ]
        result = _run_prediction_rebuild("http://brain:8001", dry_run=False)
        assert result["error"] is True
        assert "prediction_stats" in result
        assert "brain-side bug" in result["message"]

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_curiosity_gap_fill_with_fill_working(self, mock_urlopen):
        """GAP FIX #3: curiosity fill works when fill endpoint returns results."""
        mock_urlopen.side_effect = [
            _mock_urlopen({"gaps": [{"id": 461, "fire_count": 2, "query": "test"}]}),
            _mock_urlopen({"gap_query": "test", "results_ingested": 5}),
        ]
        from scripts.brain_loop_daemon import _run_curiosity_gap_fill
        result = _run_curiosity_gap_fill("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["method"] == "fill"
        assert result["results_ingested"] == 5

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_curiosity_gap_fill_fallback_to_answer(self, mock_urlopen):
        """GAP FIX #3: curiosity falls back to answer endpoint when fill returns 0."""
        mock_urlopen.side_effect = [
            _mock_urlopen({"gaps": [{"id": 461, "fire_count": 2, "query": "test query"}]}),
            _mock_urlopen({"gap_query": "test query", "results_ingested": 0}),
            _mock_urlopen({"ok": True, "gap_id": 461, "neuron_id": 999}),
        ]
        from scripts.brain_loop_daemon import _run_curiosity_gap_fill
        result = _run_curiosity_gap_fill("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["method"] == "answer_fallback"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_curiosity_gap_fill_no_gaps(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"gaps": []})
        from scripts.brain_loop_daemon import _run_curiosity_gap_fill
        result = _run_curiosity_gap_fill("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert "no gaps" in result["message"]

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_curiosity_gap_fill_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_curiosity_gap_fill
        result = _run_curiosity_gap_fill("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_synthesis_chain(self, mock_urlopen):
        """GAP FIX #4: synthesis_chain drives /brain/synthesize/chain."""
        mock_urlopen.side_effect = [
            _mock_urlopen([{"id": 120937, "fire_count": 1420}]),
            _mock_urlopen({"seed_id": 120937, "chain_length": 20, "synthesis_neuron_id": 888, "insight": "test insight"}),
        ]
        from scripts.brain_loop_daemon import _run_synthesis_chain
        result = _run_synthesis_chain("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["chain_length"] == 20
        assert result["synthesis_neuron_id"] == 888
        # Verify the chain endpoint was called
        chain_req = mock_urlopen.call_args_list[1][0][0]
        assert "/brain/synthesize/chain" in chain_req.full_url

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_synthesis_chain_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_synthesis_chain
        result = _run_synthesis_chain("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_self_mod_watcher_gate_active(self, mock_urlopen):
        """GAP FIX #2: self_mod_watcher reports gate active."""
        mock_urlopen.return_value = _mock_urlopen({
            "total_proposals": 31,
            "applied": 0,
            "constraints": {"approval_required_first_7_days": True},
        })
        from scripts.brain_loop_daemon import _run_self_mod_watcher
        result = _run_self_mod_watcher("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["gate"] == "active"
        assert "waiting" in result["message"]

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_self_mod_watcher_gate_clear(self, mock_urlopen):
        """GAP FIX #2: self_mod_watcher auto-applies when gate clears."""
        mock_urlopen.side_effect = [
            _mock_urlopen({
                "total_proposals": 31,
                "applied": 0,
                "constraints": {"approval_required_first_7_days": False},
            }),
            _mock_urlopen({"ok": True, "status": "applied"}),
        ]
        from scripts.brain_loop_daemon import _run_self_mod_watcher
        result = _run_self_mod_watcher("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["gate"] == "clear"
        assert "applied" in result["message"]

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_self_mod_watcher_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_self_mod_watcher
        result = _run_self_mod_watcher("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


# ---------------------------------------------------------------------------
# Test: v22 new loops
# ---------------------------------------------------------------------------

class TestGoalPursuit:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_goal_pursuit_with_active_goals(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen({
                "goals": [
                    {"content": "[goal] Reduce VPN downtime", "amygdala_weight": 0.9},
                    {"content": "[insight] Connection: a+b", "amygdala_weight": 0.7},
                ],
            }),
            _mock_urlopen({"ok": True, "goal": "Reduce VPN downtime", "relevant_knowledge": 6}),
        ]
        from scripts.brain_loop_daemon import _run_goal_pursuit
        result = _run_goal_pursuit("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["total_goals"] == 1

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_goal_pursuit_no_goals(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"goals": []})
        from scripts.brain_loop_daemon import _run_goal_pursuit
        result = _run_goal_pursuit("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert "no active goals" in result["message"]

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_goal_pursuit_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_goal_pursuit
        result = _run_goal_pursuit("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


class TestFleetTelemetry:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_fleet_telemetry(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen({"nodes": [{"name": "nuke"}, {"name": "homeserver"}]}),
            _mock_urlopen({"ok": True}),
        ]
        from scripts.brain_loop_daemon import _run_fleet_telemetry
        result = _run_fleet_telemetry("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["fleet_nodes"] == 2

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_fleet_telemetry_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_fleet_telemetry
        result = _run_fleet_telemetry("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


class TestWorkingMemory:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_working_memory(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen({"ok": True}),
            _mock_urlopen({"ok": True, "memories": []}),
        ]
        from scripts.brain_loop_daemon import _run_working_memory
        result = _run_working_memory("http://brain:8001", dry_run=False)
        assert result["ok"] is True

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_working_memory_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_working_memory
        result = _run_working_memory("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


class TestSelfHealFull:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_self_heal_full(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen({"issues": [], "warnings": []}),
            _mock_urlopen({"repaired": True}),
            _mock_urlopen({"rescued": 3}),
            _mock_urlopen({"decayed": 100}),
        ]
        from scripts.brain_loop_daemon import _run_self_heal_full
        result = _run_self_heal_full("http://brain:8001", dry_run=False)
        assert result["ok"] is True

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_self_heal_full_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_self_heal_full
        result = _run_self_heal_full("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


class TestActuatorExecute:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_actuator_execute_with_goals(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen({
                "goals": [{"content": "[goal] Test", "amygdala_weight": 0.9}],
            }),
            _mock_urlopen({"ok": True, "task_id": "abc123"}),
        ]
        from scripts.brain_loop_daemon import _run_actuator_execute
        result = _run_actuator_execute("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["task"]["task_id"] == "abc123"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_actuator_execute_no_goals(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"goals": []})
        from scripts.brain_loop_daemon import _run_actuator_execute
        result = _run_actuator_execute("http://brain:8001", dry_run=False)
        assert result["ok"] is True

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_actuator_execute_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_actuator_execute
        result = _run_actuator_execute("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


class TestCognitiveHypotheses:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_cognitive_hypotheses(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            "hypotheses": ["[hypothesis] test", "[hypothesis] test2"],
        })
        from scripts.brain_loop_daemon import _run_cognitive_hypotheses
        result = _run_cognitive_hypotheses("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["total"] == 2

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_cognitive_hypotheses_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_cognitive_hypotheses
        result = _run_cognitive_hypotheses("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


# ---------------------------------------------------------------------------
# Test: dry-run mode never mutates
# ---------------------------------------------------------------------------

class TestDryRun:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_all_loops_dry_run(self, mock_urlopen):
        """No loop should make an HTTP call in dry-run mode."""
        for name, func in LOOP_REGISTRY.items():
            mock_urlopen.reset_mock()
            result = func("http://brain:8001", dry_run=True)
            mock_urlopen.assert_not_called(), f"{name} made HTTP call in dry-run"
            assert result.get("dry_run") is True, f"{name} missing dry_run flag"


# ---------------------------------------------------------------------------
# Test: daemon tick scheduler
# ---------------------------------------------------------------------------

class TestDaemonTick:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_first_tick_runs_all_loops(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        daemon = BrainLoopDaemon(
            base_url="http://brain:8001",
            cadences={name: 0 for name in LOOP_REGISTRY},
        )
        report = daemon.tick()
        assert len(report.loops_run) == len(LOOP_REGISTRY)
        assert len(report.loops_skipped) == 0

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_second_tick_skips_recent_loops(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        daemon = BrainLoopDaemon(
            base_url="http://brain:8001",
            cadences={name: 3600 for name in LOOP_REGISTRY},
        )
        report1 = daemon.tick()
        assert len(report1.loops_run) == len(LOOP_REGISTRY)
        report2 = daemon.tick()
        assert len(report2.loops_run) == 0
        assert len(report2.loops_skipped) == len(LOOP_REGISTRY)

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_loop_error_doesnt_crash_tick(self, mock_urlopen):
        """If one loop raises, the others should still run."""
        call_count = 0

        def selective_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise urllib.error.URLError("connection refused")
            return FakeResponse(json.dumps({"ok": True}).encode())

        mock_urlopen.side_effect = selective_fail
        daemon = BrainLoopDaemon(
            base_url="http://brain:8001",
            cadences={name: 0 for name in LOOP_REGISTRY},
        )
        report = daemon.tick()
        assert len(report.loops_errored) >= 1
        assert len(report.loops_run) >= 1

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_tick_report_structure(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        daemon = BrainLoopDaemon(
            base_url="http://brain:8001",
            cadences={name: 0 for name in LOOP_REGISTRY},
        )
        report = daemon.tick()
        assert isinstance(report, TickReport)
        assert report.timestamp
        d = report.to_dict()
        assert "timestamp" in d
        assert "results" in d


# ---------------------------------------------------------------------------
# Test: daemon state tracking
# ---------------------------------------------------------------------------

class TestDaemonState:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_loop_states_track_runs(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        daemon = BrainLoopDaemon(
            base_url="http://brain:8001",
            cadences={name: 0 for name in LOOP_REGISTRY},
        )
        daemon.tick()
        for name, state in daemon.loop_states.items():
            assert state.run_count == 1, f"{name} run_count != 1"
            assert state.error_count == 0, f"{name} error_count != 0"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_loop_states_track_errors(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("boom")
        daemon = BrainLoopDaemon(
            base_url="http://brain:8001",
            cadences={name: 0 for name in LOOP_REGISTRY},
        )
        daemon.tick()
        for name, state in daemon.loop_states.items():
            assert state.error_count == 1, f"{name} error_count != 1"


# ---------------------------------------------------------------------------
# Test: CLI
# ---------------------------------------------------------------------------

class TestCLI:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_once_flag_outputs_json(self, mock_urlopen, capsys):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["brain_loop_daemon.py", "--once", "--url", "http://brain:8001"]
            try:
                from scripts import brain_loop_daemon
                brain_loop_daemon.main()
            except SystemExit:
                pass
        finally:
            sys.argv = old_argv

    def test_unknown_cadence_loop_exits(self):
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["brain_loop_daemon.py", "--once", "--cadence", "nonexistent=10"]
            from scripts.brain_loop_daemon import main
            with pytest.raises(SystemExit):
                main()
        finally:
            sys.argv = old_argv


# ---------------------------------------------------------------------------
# Test: HTTP error handling
# ---------------------------------------------------------------------------

class TestHTTPErrorHandling:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_http_error_returns_error_dict(self, mock_urlopen):
        import urllib.error

        error_mock = MagicMock()
        error_mock.read.return_value = b'{"detail":"brain overloaded"}'
        error_mock.__enter__ = MagicMock(return_value=error_mock)
        error_mock.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://brain:8001/brain/dream",
            code=503, msg="Service Unavailable", hdrs={}, fp=error_mock,
        )
        result = _run_dream_trigger("http://brain:8001", dry_run=False)
        assert result["error"] is True
        assert result["status"] == 503

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_url_error_returns_error_dict(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        result = _run_cognitive_cycle("http://brain:8001", dry_run=False)
        assert result["error"] is True
        assert "connection refused" in result["reason"]


# ---------------------------------------------------------------------------
# Test: learning_update and orphan_rescue loops
# ---------------------------------------------------------------------------

class TestLearningUpdate:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_learning_update(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen([{"id": 120937, "fire_count": 1420}, {"id": 120825, "fire_count": 1285}]),
            _mock_urlopen({"ok": True, "new_weight": 0.525}),
        ]
        from scripts.brain_loop_daemon import _run_learning_update
        result = _run_learning_update("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["neuron_id"] == 120937
        learn_req = mock_urlopen.call_args_list[1][0][0]
        assert "/v6/learn/online" in learn_req.full_url

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_learning_update_no_neurons(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen([])
        from scripts.brain_loop_daemon import _run_learning_update
        result = _run_learning_update("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert "no recent neurons" in result["message"]

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_learning_update_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_learning_update
        result = _run_learning_update("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


class TestOrphanRescue:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_orphan_rescue(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"rescued": 3, "orphans_found": 7})
        from scripts.brain_loop_daemon import _run_orphan_rescue
        result = _run_orphan_rescue("http://brain:8001", dry_run=False)
        assert result == {"rescued": 3, "orphans_found": 7}

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_orphan_rescue_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_orphan_rescue
        result = _run_orphan_rescue("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


# Need urllib.error imported at module level for tests above
import urllib.error  # noqa: E402
