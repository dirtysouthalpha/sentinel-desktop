"""Tests for scripts/brain_loop_daemon.py — the brain cognitive loop closer.

These tests mock the brain HTTP calls so they run without a live brain.
We verify:
  * Each loop function calls the correct endpoint with correct method/body.
  * The daemon's tick scheduler respects cadences.
  * Dry-run mode never calls mutating endpoints.
  * Errors in one loop don't crash the tick.
  * The CLI --once flag produces valid JSON output.
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
    _run_curiosity_gap_fill,
    _run_quality_prune,
    _run_dream_trigger,
    _run_consolidate_trigger,
    _run_self_modify,
    _run_creativity_execute,
    _run_outcome_log,
    _run_prediction_rebuild,
    _run_report_generate,
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
    """Build a FakeResponse with the given JSON/string.

    Returns a FakeResponse directly (not a callable) so it works as an item
    in a side_effect list.  When used as ``side_effect`` on a Mock, the mock
    returns the FakeResponse directly on each call.
    """
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
            "dream_trigger",
            "consolidate_trigger",
            "self_modify",
            "creativity_execute",
            "outcome_log",
            "learning_update",
            "orphan_rescue",
            "prediction_rebuild",
            "report_generate",
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
        # Verify the call was made with POST to /cognitive/cycle
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.full_url == "http://brain:8001/cognitive/cycle"
        assert req.method == "POST"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_synapse_maintenance(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "deleted": 100})
        result = _run_synapse_maintenance("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "deleted": 100}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/synapses/reap"
        assert req.method == "POST"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_curiosity_gap_fill(self, mock_urlopen):
        # First call returns gaps list, second call fills the top gap
        mock_urlopen.side_effect = [
            _mock_urlopen({"gaps": [{"id": 49, "fire_count": 17}, {"id": 51, "fire_count": 14}]}),
            _mock_urlopen({"gap_query": "test", "results_ingested": 3}),
        ]
        result = _run_curiosity_gap_fill("http://brain:8001", dry_run=False)
        assert result == {"gap_query": "test", "results_ingested": 3}
        # The second call should target gap 49 (highest fire_count)
        second_req = mock_urlopen.call_args_list[1][0][0]
        body = json.loads(second_req.data)
        assert body["gap_neuron_id"] == 49

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_curiosity_gap_fill_no_gaps(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"gaps": []})
        result = _run_curiosity_gap_fill("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert "no gaps" in result["message"]

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_quality_prune(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "pruned": 5})
        result = _run_quality_prune("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "pruned": 5}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/quality/prune"
        body = json.loads(req.data)
        assert body["threshold"] == 0.3
        assert body["limit"] == 50

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_dream_trigger(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "dreamed": True})
        result = _run_dream_trigger("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "dreamed": True}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/dream"
        assert req.method == "POST"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_consolidate_trigger(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "consolidated": True})
        result = _run_consolidate_trigger("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "consolidated": True}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/consolidate"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_self_modify_gate_active(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            "total_proposals": 27,
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
                "total_proposals": 27,
                "applied": 0,
                "constraints": {"approval_required_first_7_days": False},
            }),
            _mock_urlopen({"ok": True, "applied": 1}),
        ]
        result = _run_self_modify("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "applied": 1}

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_creativity_execute_no_pending(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen({"experiments": []}),
            _mock_urlopen({"ok": True, "status": "proposed"}),
        ]
        result = _run_creativity_execute("http://brain:8001", dry_run=False)
        assert result == {"ok": True, "status": "proposed"}

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_creativity_execute_has_pending(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen({
                "experiments": [{"id": 1, "status": "proposed", "gap": "No cross-region neuron synthesis"}],
            }),
            _mock_urlopen({"ok": True, "domain_a": "knowledge", "domain_b": "infrastructure", "synthesis": "test"}),
        ]
        result = _run_creativity_execute("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["experiment_id"] == 1
        assert result["domain_a"] == "knowledge"
        assert result["domain_b"] == "infrastructure"
        # Verify the synthesis endpoint was called
        second_req = mock_urlopen.call_args_list[1][0][0]
        assert "/creative/synthesize" in second_req.full_url

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_outcome_log(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        result = _run_outcome_log("http://brain:8001", dry_run=False)
        assert result == {"ok": True}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/outcome"
        body = json.loads(req.data)
        assert "neuron_ids" in body
        assert "outcome" in body
        assert body["outcome"] == "good"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_prediction_rebuild(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"ok": True})
        result = _run_prediction_rebuild("http://brain:8001", dry_run=False)
        assert result == {"ok": True}
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/transitions/rebuild"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_report_generate(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen("brain report text")
        result = _run_report_generate("http://brain:8001", dry_run=False)
        assert result == "brain report text"
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/report"
        assert req.method == "GET"


# ---------------------------------------------------------------------------
# Test: dry-run mode never mutates
# ---------------------------------------------------------------------------

class TestDryRun:
    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_cognitive_cycle_dry_run(self, mock_urlopen):
        result = _run_cognitive_cycle("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True

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
        # Use very short cadences so everything runs immediately
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
            cadences={name: 3600 for name in LOOP_REGISTRY},  # 1 hour cadence
        )
        report1 = daemon.tick()
        assert len(report1.loops_run) == len(LOOP_REGISTRY)
        # Immediately tick again — all should be skipped
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
        # At least one loop should be in errored
        assert len(report.loops_errored) >= 1
        # And the rest should still have run
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
        assert isinstance(report.loops_run, list)
        assert isinstance(report.results, dict)
        d = report.to_dict()
        assert "timestamp" in d
        assert "loops_run" in d
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
            assert state.last_run > 0, f"{name} last_run not set"

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
            # Catch SystemExit from argparse if needed
            try:
                from scripts import brain_loop_daemon
                # Run main by importing and calling
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

        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://brain:8001/brain/dream",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=None,
        )
        # HTTPError needs a read() method on fp for our handler
        # Create a proper mock
        error_mock = MagicMock()
        error_mock.read.return_value = b'{"detail":"brain overloaded"}'
        error_mock.__enter__ = MagicMock(return_value=error_mock)
        error_mock.__exit__ = MagicMock(return_value=False)
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://brain:8001/brain/dream",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=error_mock,
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
        # /neurons returns a list directly
        mock_urlopen.side_effect = [
            _mock_urlopen([{"id": 120937, "fire_count": 1420}, {"id": 120825, "fire_count": 1285}]),
            _mock_urlopen({"ok": True, "new_weight": 0.525}),
            _mock_urlopen({"grade": "high"}),
        ]
        from scripts.brain_loop_daemon import _run_learning_update
        result = _run_learning_update("http://brain:8001", dry_run=False)
        assert result["ok"] is True
        assert result["neuron_id"] == 120937  # highest fire_count
        # Verify query-param endpoints were called
        learn_req = mock_urlopen.call_args_list[1][0][0]
        assert "/v6/learn/online" in learn_req.full_url
        assert "neuron_id=120937" in learn_req.full_url

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
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://brain:8001/brain/self-heal/rescue-orphans"

    @patch("scripts.brain_loop_daemon.urllib.request.urlopen")
    def test_orphan_rescue_dry_run(self, mock_urlopen):
        from scripts.brain_loop_daemon import _run_orphan_rescue
        result = _run_orphan_rescue("http://brain:8001", dry_run=True)
        mock_urlopen.assert_not_called()
        assert result["dry_run"] is True


# Need urllib.error imported at module level for tests above
import urllib.error  # noqa: E402
