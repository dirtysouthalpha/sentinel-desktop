"""Gap tests for core.server.{daemon,fleet,job_queue}.

Covers:
  daemon.py  — lines 135-136 (_save_state OSError), 139-144 (_load_state all paths)
  fleet.py   — lines 133 (heartbeat not-found), 137 (health param),
                174-175 (_load exception), 182-183 (_save OSError)
  job_queue.py — lines 153, 165, 177 (not-found), 179 (cancel non-cancellable),
                 195 (list_jobs skip None), 200 (list_jobs limit break),
                 225-227 (_load_job_file exception)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.server.daemon import SentinelDaemon
from core.server.fleet import FleetManager
from core.server.job_queue import JobQueue

# ── SentinelDaemon ────────────────────────────────────────────────────────


class TestDaemonSaveStateOSError:
    """Lines 135-136 — OSError in _save_state() is swallowed."""

    def test_save_state_oserror_does_not_raise(self, tmp_path):
        daemon = SentinelDaemon(state_path=tmp_path / "state.json")
        daemon.start()

        # Patch write_text to fail after start() already wrote the file
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            daemon.record_job(success=True)  # triggers _save_state()

        # The daemon should still be running despite the OSError
        assert daemon.is_running is True

    def test_save_state_oserror_logs_warning(self, tmp_path, caplog):
        import logging

        daemon = SentinelDaemon(state_path=tmp_path / "state.json")
        daemon.start()

        with patch.object(Path, "write_text", side_effect=OSError("no space left")):
            with caplog.at_level(logging.WARNING, logger="core.server.daemon"):
                daemon.record_job(success=False)

        assert any("daemon state" in r.message.lower() for r in caplog.records)


class TestDaemonLoadState:
    """Lines 139-144 — _load_state() all three paths."""

    def test_load_state_no_file_returns_empty(self, tmp_path):
        daemon = SentinelDaemon(state_path=tmp_path / "missing.json")
        result = daemon._load_state()
        assert result == {}

    def test_load_state_valid_json_returns_dict(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"status": "running", "pid": 1234}), encoding="utf-8")
        daemon = SentinelDaemon(state_path=state_path)
        result = daemon._load_state()
        assert result["status"] == "running"
        assert result["pid"] == 1234

    def test_load_state_corrupt_json_returns_empty(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_path.write_text("{ not valid json }", encoding="utf-8")
        daemon = SentinelDaemon(state_path=state_path)
        result = daemon._load_state()
        assert result == {}

    def test_load_state_oserror_returns_empty(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_path.write_text("{}", encoding="utf-8")
        daemon = SentinelDaemon(state_path=state_path)
        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            result = daemon._load_state()
        assert result == {}


# ── FleetManager ──────────────────────────────────────────────────────────


class TestFleetHeartbeatNotFound:
    """Line 133 — update_heartbeat() when node is not registered."""

    def test_heartbeat_unknown_node_returns_error(self, tmp_path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        result = fleet.update_heartbeat("ghost-node-99")
        assert result["success"] is False
        assert "not found" in result["error"]


class TestFleetHeartbeatWithHealth:
    """Line 137 — node.health = health is set when health dict is provided."""

    def test_heartbeat_sets_health_on_node(self, tmp_path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        fleet.register_node("n1", hostname="box1")
        health_data = {"cpu": 42.0, "mem": 78.5}

        result = fleet.update_heartbeat("n1", health=health_data)

        assert result["success"] is True
        node = fleet.get_node("n1")
        assert node["health"] == health_data


class TestFleetLoadException:
    """Lines 174-175 — corrupted JSON in fleet file is caught."""

    def test_corrupt_fleet_file_loads_empty(self, tmp_path):
        fleet_file = tmp_path / "fleet.json"
        fleet_file.write_text("NOT JSON", encoding="utf-8")
        # FleetManager calls _load() in __init__
        fleet = FleetManager(path=fleet_file)
        assert fleet.count() == 0

    def test_corrupt_fleet_file_logs_warning(self, tmp_path, caplog):
        import logging

        fleet_file = tmp_path / "fleet.json"
        fleet_file.write_text("{{{bad", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="core.server.fleet"):
            FleetManager(path=fleet_file)
        assert any("fleet" in r.message.lower() for r in caplog.records)


class TestFleetLoadCorruptFilePreservation:
    """A corrupt fleet file must be quarantined, not silently overwritten with
    empty by the next mutation (mirrors the TriggerRegistry fix)."""

    def test_corrupt_file_quarantined_before_save_clobbers_it(self, tmp_path):
        fleet_file = tmp_path / "fleet.json"
        original_bytes = '{not valid json at all'
        fleet_file.write_text(original_bytes, encoding="utf-8")

        fleet = FleetManager(path=fleet_file)
        # A mutation triggers _save(); without quarantine this overwrites the
        # corrupt file with an empty-ish fleet, destroying the operator's data.
        fleet.register_node("n1", hostname="box1")

        backup = tmp_path / "fleet.json.corrupt"
        assert backup.exists(), "corrupt fleet file should be quarantined, not clobbered"
        assert backup.read_text(encoding="utf-8") == original_bytes

    def test_malformed_node_record_does_not_crash_load(self, tmp_path):
        """One node missing required 'node_id' must be skipped, not crash __init__."""
        fleet_file = tmp_path / "fleet.json"
        fleet_file.write_text(
            json.dumps({"nodes": [{"hostname": "no-id-here"}]}),
            encoding="utf-8",
        )
        fleet = FleetManager(path=fleet_file)  # must not raise
        assert fleet.count() == 0

    def test_malformed_node_skipped_valid_nodes_preserved(self, tmp_path):
        """A bad record skips only itself; valid siblings are still loaded."""
        fleet_file = tmp_path / "fleet.json"
        fleet_file.write_text(
            json.dumps(
                {
                    "nodes": [
                        {"node_id": "good-1", "hostname": "box1"},
                        {"hostname": "missing-id"},  # malformed
                        {"node_id": "good-2", "hostname": "box2"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        fleet = FleetManager(path=fleet_file)
        assert fleet.count() == 2
        assert fleet.get_node("good-1") is not None
        assert fleet.get_node("good-2") is not None


class TestFleetSaveOSError:
    """Lines 182-183 — OSError in _save() is swallowed."""

    def test_save_oserror_does_not_raise(self, tmp_path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        fleet.register_node("n1", hostname="box1")

        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            # unregister_node() calls _save() internally
            fleet.unregister_node("n1")

        # The operation should complete (node is gone from memory)
        # even though persisting to disk failed
        assert fleet.get_node("n1") is None


# ── JobQueue ──────────────────────────────────────────────────────────────


class TestJobQueueNotFound:
    """Lines 153, 165, 177 — complete/fail/cancel return False for unknown job_id."""

    def test_complete_unknown_job_returns_false(self, tmp_path):
        q = JobQueue(path=tmp_path)
        assert q.complete("nonexistent-job-id") is False

    def test_fail_unknown_job_returns_false(self, tmp_path):
        q = JobQueue(path=tmp_path)
        assert q.fail("nonexistent-job-id", error="something broke") is False

    def test_cancel_unknown_job_returns_false(self, tmp_path):
        q = JobQueue(path=tmp_path)
        assert q.cancel("nonexistent-job-id") is False


class TestJobQueueCancelNonCancellable:
    """Line 179 — cancel() returns False when job is already completed."""

    def test_cancel_completed_job_returns_false(self, tmp_path):
        q = JobQueue(path=tmp_path)
        job_id = q.submit("do something")
        q.claim_next()  # moves to RUNNING
        q.complete(job_id, result={"done": True})

        assert q.cancel(job_id) is False

    def test_cancel_failed_job_returns_false(self, tmp_path):
        q = JobQueue(path=tmp_path)
        job_id = q.submit("do something")
        q.claim_next()  # moves to RUNNING
        q.fail(job_id, error="it broke")

        assert q.cancel(job_id) is False


class TestJobQueueListJobsCorruptFile:
    """Lines 195, 225-227 — list_jobs skips None from corrupt job files."""

    def test_corrupt_job_file_skipped_in_list(self, tmp_path):
        q = JobQueue(path=tmp_path)
        # Write a corrupt JSON file that looks like a job file
        corrupt = tmp_path / "badjob123.json"
        corrupt.write_text("NOT JSON AT ALL", encoding="utf-8")

        # Should not raise and should skip the corrupt file
        jobs = q.list_jobs()
        assert isinstance(jobs, list)
        # Corrupt file is skipped — no job with that id
        assert not any(j.get("job_id") == "badjob123" for j in jobs)

    def test_corrupt_job_file_logs_warning(self, tmp_path, caplog):
        import logging

        q = JobQueue(path=tmp_path)
        corrupt = tmp_path / "badjob456.json"
        corrupt.write_text("{{bad json}}", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="core.server.job_queue"):
            q.list_jobs()

        assert any("Failed to load job" in r.message for r in caplog.records)


class TestJobQueueListJobsLimit:
    """Lines 199-200 — list_jobs() stops at limit."""

    def test_list_jobs_respects_limit(self, tmp_path):
        q = JobQueue(path=tmp_path)
        for i in range(5):
            q.submit(f"job goal {i}")

        result = q.list_jobs(limit=3)
        assert len(result) == 3
