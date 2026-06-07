"""Tests for v10.0 Sentinel Server — daemon, fleet, job queue."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.server.daemon import DaemonStatus, SentinelDaemon
from core.server.fleet import FleetManager, FleetNode
from core.server.job_queue import JobQueue, JobStatus


# ===========================================================================
# Daemon tests
# ===========================================================================


class TestSentinelDaemon:
    def test_start(self, tmp_path: Path):
        daemon = SentinelDaemon(state_path=tmp_path / "daemon.json")
        result = daemon.start()
        assert result["success"] is True
        assert daemon.is_running is True
        assert daemon.status == DaemonStatus.RUNNING

    def test_stop(self, tmp_path: Path):
        daemon = SentinelDaemon(state_path=tmp_path / "daemon.json")
        daemon.start()
        result = daemon.stop()
        assert result["success"] is True
        assert daemon.is_running is False

    def test_stop_when_not_running(self, tmp_path: Path):
        daemon = SentinelDaemon(state_path=tmp_path / "daemon.json")
        result = daemon.stop()
        assert result["success"] is False

    def test_double_start(self, tmp_path: Path):
        daemon = SentinelDaemon(state_path=tmp_path / "daemon.json")
        daemon.start()
        result = daemon.start()
        assert result["success"] is False

    def test_get_status(self, tmp_path: Path):
        daemon = SentinelDaemon(state_path=tmp_path / "daemon.json")
        daemon.start()
        status = daemon.get_status()
        assert status["status"] == "running"
        assert status["pid"] is not None
        assert status["started_at"] is not None

    def test_record_job(self, tmp_path: Path):
        daemon = SentinelDaemon(state_path=tmp_path / "daemon.json")
        daemon.start()
        daemon.record_job(success=True)
        daemon.record_job(success=True)
        daemon.record_job(success=False)
        assert daemon.get_status()["jobs_completed"] == 2
        assert daemon.get_status()["jobs_failed"] == 1

    def test_heartbeat(self, tmp_path: Path):
        daemon = SentinelDaemon(state_path=tmp_path / "daemon.json")
        daemon.start()
        result = daemon.heartbeat()
        assert result["success"] is True
        assert result["timestamp"] is not None

    def test_uptime_seconds(self, tmp_path: Path):
        daemon = SentinelDaemon(state_path=tmp_path / "daemon.json")
        assert daemon.uptime_seconds == 0.0
        daemon.start()
        assert daemon.uptime_seconds > 0

    def test_state_persistence(self, tmp_path: Path):
        path = tmp_path / "daemon.json"
        daemon = SentinelDaemon(state_path=path)
        daemon.start()
        daemon.record_job(success=True)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["status"] == "running"
        assert data["jobs_completed"] == 1


# ===========================================================================
# Fleet tests
# ===========================================================================


class TestFleetManager:
    def test_register_node(self, tmp_path: Path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        result = fleet.register_node("core-1", hostname="SENTINEL-CORE", role="orchestrator")
        assert result["success"] is True
        assert fleet.count() == 1

    def test_register_duplicate(self, tmp_path: Path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        fleet.register_node("core-1")
        result = fleet.register_node("core-1")
        assert result["success"] is False

    def test_unregister_node(self, tmp_path: Path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        fleet.register_node("core-1")
        result = fleet.unregister_node("core-1")
        assert result["success"] is True
        assert fleet.count() == 0

    def test_unregister_missing(self, tmp_path: Path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        result = fleet.unregister_node("nope")
        assert result["success"] is False

    def test_heartbeat(self, tmp_path: Path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        fleet.register_node("core-1")
        result = fleet.update_heartbeat("core-1", health={"cpu": 45, "ram": 60})
        assert result["success"] is True
        node = fleet.get_node("core-1")
        assert node["health"]["cpu"] == 45
        assert node["status"] == "online"

    def test_record_job(self, tmp_path: Path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        fleet.register_node("core-1")
        fleet.record_job("core-1", success=True)
        fleet.record_job("core-1", success=True)
        fleet.record_job("core-1", success=False)
        node = fleet.get_node("core-1")
        assert node["jobs_completed"] == 2
        assert node["jobs_failed"] == 1

    def test_list_nodes(self, tmp_path: Path):
        fleet = FleetManager(path=tmp_path / "fleet.json")
        fleet.register_node("core-1", hostname="Core")
        fleet.register_node("edge-1", hostname="Edge", role="execution")
        nodes = fleet.list_nodes()
        assert len(nodes) == 2
        hostnames = {n["hostname"] for n in nodes}
        assert "Core" in hostnames
        assert "Edge" in hostnames

    def test_persistence(self, tmp_path: Path):
        path = tmp_path / "fleet.json"
        fleet1 = FleetManager(path=path)
        fleet1.register_node("core-1", hostname="Core")

        fleet2 = FleetManager(path=path)
        assert fleet2.count() == 1
        node = fleet2.get_node("core-1")
        assert node["hostname"] == "Core"


class TestFleetNode:
    def test_to_dict_roundtrip(self):
        node = FleetNode(node_id="test", hostname="host", role="agent", tags=["prod"])
        d = node.to_dict()
        restored = FleetNode.from_dict(d)
        assert restored.node_id == "test"
        assert restored.hostname == "host"
        assert restored.tags == ["prod"]


# ===========================================================================
# Job Queue tests
# ===========================================================================


class TestJobQueue:
    def test_submit(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        job_id = queue.submit("Login to firewall and check ARP")
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    def test_get_job(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        job_id = queue.submit("Test goal")
        job = queue.get_job(job_id)
        assert job is not None
        assert job["goal"] == "Test goal"
        assert job["status"] == "pending"

    def test_get_missing_job(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        assert queue.get_job("nonexistent") is None

    def test_claim_next(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        queue.submit("Low priority", priority=0)
        queue.submit("High priority", priority=10)
        queue.submit("Medium priority", priority=5)

        job = queue.claim_next(node_id="core-1")
        assert job is not None
        assert job["goal"] == "High priority"
        assert job["status"] == "running"
        assert job["node_id"] == "core-1"

    def test_claim_next_empty(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        assert queue.claim_next() is None

    def test_complete(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        job_id = queue.submit("Do something")
        queue.claim_next()
        result = queue.complete(job_id, result={"success": True, "output": "done"})
        assert result is True
        job = queue.get_job(job_id)
        assert job["status"] == "completed"
        assert job["result"]["success"] is True

    def test_fail(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        job_id = queue.submit("Will fail")
        queue.claim_next()
        queue.fail(job_id, error="Connection timeout")
        job = queue.get_job(job_id)
        assert job["status"] == "failed"
        assert "timeout" in job["error"]

    def test_cancel(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        job_id = queue.submit("Cancel me")
        result = queue.cancel(job_id)
        assert result is True
        job = queue.get_job(job_id)
        assert job["status"] == "cancelled"

    def test_cancel_completed_fails(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        job_id = queue.submit("Done already")
        queue.claim_next()
        queue.complete(job_id, result={})
        assert queue.cancel(job_id) is False

    def test_list_jobs(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        queue.submit("Job 1")
        queue.submit("Job 2")
        queue.submit("Job 3")
        jobs = queue.list_jobs()
        assert len(jobs) == 3

    def test_list_jobs_filter_by_status(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        queue.submit("Pending 1")
        queue.submit("Pending 2")
        job_id = queue.submit("Will complete")
        queue.claim_next()
        queue.complete(job_id, result={})

        pending = queue.list_jobs(status="pending")
        assert len(pending) == 1  # One was claimed and completed
        completed = queue.list_jobs(status="completed")
        assert len(completed) == 1

    def test_count_pending(self, tmp_path: Path):
        queue = JobQueue(path=tmp_path / "jobs")
        queue.submit("A")
        queue.submit("B")
        assert queue.count_pending() == 2
        queue.claim_next()
        assert queue.count_pending() == 1

    def test_full_lifecycle(self, tmp_path: Path):
        """Submit → claim → complete — full job lifecycle."""
        queue = JobQueue(path=tmp_path / "jobs")
        job_id = queue.submit("Login to 192.168.1.1 and check ARP")

        # Still pending
        job = queue.get_job(job_id)
        assert job["status"] == "pending"

        # Agent claims it
        claimed = queue.claim_next(node_id="sentinel-core")
        assert claimed["job_id"] == job_id
        assert claimed["status"] == "running"

        # Agent finishes
        queue.complete(job_id, result={"success": True, "output": {"arp_table": []}})
        job = queue.get_job(job_id)
        assert job["status"] == "completed"
        assert job["result"]["success"] is True
