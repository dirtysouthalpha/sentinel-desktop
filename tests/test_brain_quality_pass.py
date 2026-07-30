"""
Tests for scripts/brain_quality_pass.py

Uses unittest.mock to patch requests so no real brain is needed.
Covers: health check, dry-run safety, execute deletes, orphan connection,
unreachable brain, limit enforcement, stale detection, stats display.
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make scripts/ importable
SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import brain_quality_pass as bqp  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────

def _mock_response(status_code=200, json_data=None, text=""):
    """Build a fake requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text
    return resp


def _sample_neurons(n=5, with_connections=True):
    """Generate a list of fake neurons."""
    neurons = []
    for i in range(1, n + 1):
        neuron = {
            "id": i,
            "topic": f"topic_{i}",
            "content": f"content for neuron {i}",
            "quality": 0.1 * i,  # 0.1, 0.2, 0.3, ...
            "region": "general",
            "connections": [i + 1] if with_connections else [],
            "connection_count": 1 if with_connections else 0,
            "last_fired": "2020-01-01T00:00:00",
        }
        neurons.append(neuron)
    return neurons


# ── Tests ────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_ok(self):
        with patch("brain_quality_pass.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, {"status": "ok"})
            assert bqp.health_check("http://fake:8001") is True

    def test_health_offline(self):
        import requests as req
        with patch("brain_quality_pass.requests.get") as mock_get:
            mock_get.side_effect = req.exceptions.ConnectionError("refused")
            assert bqp.health_check("http://fake:8001") is False

    def test_health_http_error(self):
        with patch("brain_quality_pass.requests.get") as mock_get:
            mock_get.return_value = _mock_response(500, text="server error")
            assert bqp.health_check("http://fake:8001") is False


class TestDryRunDoesNotDelete:
    """Dry-run mode must never issue DELETE requests."""

    def test_prune_dry_run_no_delete(self):
        neurons = _sample_neurons(5)
        with patch("brain_quality_pass.requests.get") as mock_get, \
             patch("brain_quality_pass.requests.delete") as mock_del:
            mock_get.return_value = _mock_response(200, neurons)
            report = bqp.prune_low_quality(
                "http://fake:8001", threshold=0.3, limit=100, execute=False
            )
            assert mock_del.call_count == 0
            assert report["dry_run"] is True
            # neurons with quality < 0.3: id=1 (0.1), id=2 (0.2)
            assert report["found"] == 2
            assert report["deleted"] == 0

    def test_connect_dry_run_no_post(self):
        orphans = _sample_neurons(2, with_connections=False)
        with patch("brain_quality_pass.requests.get") as mock_get, \
             patch("brain_quality_pass.requests.post") as mock_post:
            # First call: list neurons; subsequent calls: search for candidates
            mock_get.side_effect = [
                _mock_response(200, orphans),  # list_neurons
                _mock_response(200, [{"id": 99, "topic": "match"}]),  # search
                _mock_response(200, [{"id": 99, "topic": "match"}]),  # search
            ]
            report = bqp.connect_orphans(
                "http://fake:8001", limit=100, execute=False
            )
            assert mock_post.call_count == 0
            assert report["dry_run"] is True
            assert report["found"] == 2


class TestExecuteDeletes:
    """--execute should actually call DELETE on low-quality neurons."""

    def test_prune_execute_deletes(self):
        neurons = _sample_neurons(5)
        with patch("brain_quality_pass.requests.get") as mock_get, \
             patch("brain_quality_pass.requests.delete") as mock_del:
            mock_get.return_value = _mock_response(200, neurons)
            mock_del.return_value = _mock_response(204)
            report = bqp.prune_low_quality(
                "http://fake:8001", threshold=0.3, limit=100, execute=True
            )
            assert report["dry_run"] is False
            assert report["found"] == 2
            assert report["deleted"] == 2
            assert mock_del.call_count == 2

    def test_connect_execute_posts(self):
        orphans = _sample_neurons(2, with_connections=False)
        with patch("brain_quality_pass.requests.get") as mock_get, \
             patch("brain_quality_pass.requests.post") as mock_post:
            mock_get.side_effect = [
                _mock_response(200, orphans),
                _mock_response(200, [{"id": 99, "topic": "match"}]),
                _mock_response(200, [{"id": 99, "topic": "match"}]),
            ]
            mock_post.return_value = _mock_response(200)
            report = bqp.connect_orphans(
                "http://fake:8001", limit=100, execute=True
            )
            assert report["dry_run"] is False
            assert report["connected"] == 2
            assert mock_post.call_count == 2


class TestOrphanConnection:
    def test_find_orphans_filters_correctly(self):
        """Only neurons with no connections should be returned as orphans."""
        neurons = [
            {"id": 1, "connections": [2], "connection_count": 1},
            {"id": 2, "connections": [], "connection_count": 0},
            {"id": 3, "connections": [], "connection_count": 0},
        ]
        with patch("brain_quality_pass.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, neurons)
            orphans = bqp.find_orphans("http://fake:8001", limit=100)
            ids = [o["id"] for o in orphans]
            assert ids == [2, 3]

    def test_orphan_skips_self_in_candidates(self):
        """An orphan should not be connected to itself."""
        orphan = {"id": 5, "topic": "solo", "content": "lonely", "connections": [], "connection_count": 0}
        # Search returns the orphan itself as top candidate
        candidates = [
            {"id": 5, "topic": "solo"},  # self
            {"id": 10, "topic": "other"},
        ]
        with patch("brain_quality_pass.requests.get") as mock_get, \
             patch("brain_quality_pass.requests.post") as mock_post:
            mock_get.side_effect = [
                _mock_response(200, [orphan]),  # list
                _mock_response(200, candidates),  # search
            ]
            mock_post.return_value = _mock_response(200)
            report = bqp.connect_orphans("http://fake:8001", limit=100, execute=True)
            assert report["connected"] == 1
            # Should connect to id=10, not id=5
            call_args = mock_post.call_args
            assert "/neurons/5/connect" in call_args[0][0]
            assert call_args[1]["json"]["target_id"] == 10


class TestUnreachableBrain:
    def test_main_exits_when_unreachable(self, capsys):
        """main() should return 1 if brain is unreachable."""
        with patch("brain_quality_pass.health_check", return_value=False):
            result = bqp.main(["--stats"])
            assert result == 1


class TestLimitEnforcement:
    def test_prune_respects_limit(self):
        """Even if more neurons match, only --limit should be processed."""
        neurons = _sample_neurons(10)  # 10 neurons, quality 0.1..1.0
        with patch("brain_quality_pass.requests.get") as mock_get, \
             patch("brain_quality_pass.requests.delete") as mock_del:
            mock_get.return_value = _mock_response(200, neurons)
            mock_del.return_value = _mock_response(204)
            report = bqp.prune_low_quality(
                "http://fake:8001", threshold=0.5, limit=3, execute=True
            )
            # 4 neurons below 0.5 (0.1, 0.2, 0.3, 0.4) but limit=3
            assert report["found"] == 4
            assert mock_del.call_count == 3
            assert report["deleted"] == 3


class TestEnrichStale:
    def test_stale_detection(self):
        """Neurons not fired in N days should be flagged."""
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        old = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S")
        neurons = [
            {"id": 1, "topic": "fresh", "last_fired": recent},
            {"id": 2, "topic": "stale", "last_fired": old},
            {"id": 3, "topic": "never", "last_fired": None},
        ]
        with patch("brain_quality_pass.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, neurons)
            report = bqp.enrich_stale("http://fake:8001", days=30, limit=100)
            assert report["found"] == 2  # id=2 and id=3


class TestStatsDisplay:
    def test_get_stats(self):
        fake_stats = {"total": 5490, "orphans": 731, "low_quality": 4288}
        with patch("brain_quality_pass.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, fake_stats)
            stats = bqp.get_stats("http://fake:8001")
            assert stats == fake_stats

    def test_print_stats_empty(self, capsys):
        """print_stats should handle empty dict gracefully."""
        bqp.print_stats({})
        captured = capsys.readouterr()
        assert "No stats available" in captured.out


class TestMainCLI:
    def test_main_default_shows_stats(self, capsys):
        """With no action flags, main() defaults to --stats."""
        with patch("brain_quality_pass.health_check", return_value=True), \
             patch("brain_quality_pass.get_stats", return_value={"total": 100}):
            result = bqp.main([])
            assert result == 0

    def test_main_auto_runs_all(self):
        """--auto should run prune + connect + enrich."""
        with patch("brain_quality_pass.health_check", return_value=True), \
             patch("brain_quality_pass.get_stats", return_value={}), \
             patch("brain_quality_pass.prune_low_quality", return_value={"found": 0}) as mock_prune, \
             patch("brain_quality_pass.connect_orphans", return_value={"found": 0}) as mock_conn, \
             patch("brain_quality_pass.enrich_stale", return_value={"found": 0}) as mock_enrich:
            result = bqp.main(["--auto"])
            assert result == 0
            mock_prune.assert_called_once()
            mock_conn.assert_called_once()
            mock_enrich.assert_called_once()
