"""Sentinel Desktop v10.0 — Job Queue.

Async job queue for submitting goals and getting results later.
Jobs are stored as JSON files so they survive restarts.

Usage::

    queue = JobQueue()
    job_id = queue.submit("Login to the firewall and check ARP table")
    # ... agent processes it ...
    queue.complete(job_id, result={"success": True, ...})
    status = queue.get_job(job_id)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_PATH = Path("config/jobs")


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job:
    """A single job in the queue."""

    def __init__(
        self,
        goal: str,
        job_id: str | None = None,
        priority: int = 0,
        node_id: str | None = None,
    ) -> None:
        self.job_id = job_id or uuid.uuid4().hex[:12]
        self.goal = goal
        self.priority = priority
        self.node_id = node_id
        self.status: JobStatus = JobStatus.PENDING
        self.created_at: str = datetime.utcnow().isoformat()
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "goal": self.goal,
            "priority": self.priority,
            "node_id": self.node_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        job = cls(
            goal=data["goal"],
            job_id=data.get("job_id"),
            priority=data.get("priority", 0),
            node_id=data.get("node_id"),
        )
        job.status = JobStatus(data.get("status", "pending"))
        # ``or`` (not plain .get) so an explicit null created_at — a hand-edit,
        # migration artifact, or external writer — falls back to a sane value
        # instead of None, which would crash list_jobs/claim_next's sort with a
        # TypeError and poison the whole queue.
        job.created_at = data.get("created_at") or job.created_at
        job.started_at = data.get("started_at")
        job.completed_at = data.get("completed_at")
        job.result = data.get("result")
        job.error = data.get("error")
        return job


class JobQueue:
    """Persistent job queue for async goal processing.

    Jobs are stored as individual JSON files in the queue directory.
    This makes them durable across restarts and easy to inspect.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_QUEUE_PATH
        self._path.mkdir(parents=True, exist_ok=True)

    def submit(
        self,
        goal: str,
        priority: int = 0,
        node_id: str | None = None,
    ) -> str:
        """Submit a new job. Returns the job ID."""
        job = Job(goal=goal, priority=priority, node_id=node_id)
        self._save_job(job)
        logger.info("Job submitted: %s — %s", job.job_id, goal[:60])
        return job.job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Get a job's status and details."""
        job = self._load_job(job_id)
        return job.to_dict() if job else None

    def claim_next(self, node_id: str | None = None) -> dict[str, Any] | None:
        """Claim the next pending job (highest priority first).

        Args:
            node_id: Node claiming the job.

        Returns:
            Job dict, or None if no pending jobs.
        """
        pending = []
        for job_file in self._path.glob("*.json"):
            job = self._load_job_file(job_file)
            if job and job.status == JobStatus.PENDING:
                pending.append(job)

        if not pending:
            return None

        # Sort by priority (descending), then by created_at (ascending)
        pending.sort(key=lambda j: (-j.priority, j.created_at))
        job = pending[0]

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow().isoformat()
        if node_id:
            job.node_id = node_id
        self._save_job(job)

        logger.info("Job claimed: %s by %s", job.job_id, node_id or "local")
        return job.to_dict()

    def complete(self, job_id: str, result: dict[str, Any] | None = None) -> bool:
        """Mark a job as completed."""
        job = self._load_job(job_id)
        if job is None:
            return False
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.utcnow().isoformat()
        job.result = result
        self._save_job(job)
        logger.info("Job completed: %s", job_id)
        return True

    def fail(self, job_id: str, error: str = "") -> bool:
        """Mark a job as failed."""
        job = self._load_job(job_id)
        if job is None:
            return False
        job.status = JobStatus.FAILED
        job.completed_at = datetime.utcnow().isoformat()
        job.error = error
        self._save_job(job)
        logger.info("Job failed: %s — %s", job_id, error[:80])
        return True

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending job."""
        job = self._load_job(job_id)
        if job is None:
            return False
        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return False
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.utcnow().isoformat()
        self._save_job(job)
        return True

    def list_jobs(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List jobs, most-recent-first, optionally filtered by status."""
        jobs: list[Job] = []
        for job_file in self._path.glob("*.json"):
            job = self._load_job_file(job_file)
            if job is None:
                continue
            if status and job.status.value != status:
                continue
            jobs.append(job)
        # Sort by created_at descending — filenames are random UUID prefixes, so
        # a glob-name sort yields meaningless order. Matches claim_next's ordering.
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs[:limit]]

    def count_pending(self) -> int:
        """Count pending jobs."""
        return len([j for j in self.list_jobs(status="pending")])

    def _save_job(self, job: Job) -> None:
        filepath = self._path / f"{job.job_id}.json"
        filepath.write_text(
            json.dumps(job.to_dict(), indent=2),
            encoding="utf-8",
        )

    def _load_job(self, job_id: str) -> Job | None:
        filepath = self._path / f"{job_id}.json"
        if not filepath.exists():
            return None
        return self._load_job_file(filepath)

    @staticmethod
    def _load_job_file(filepath: Path) -> Job | None:
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return Job.from_dict(data)
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning("Failed to load job from %s: %s", filepath, exc)
            return None
