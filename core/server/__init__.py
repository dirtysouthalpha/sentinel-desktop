"""Sentinel Desktop v10.0 — Sentinel Server subpackage.

Fleet/daemon mode for headless background service and multi-machine management.
"""

from core.server.daemon import SentinelDaemon
from core.server.fleet import FleetManager
from core.server.job_queue import JobQueue

__all__ = ["SentinelDaemon", "FleetManager", "JobQueue"]
