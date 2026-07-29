"""Daily digest pipeline for the fleet mesh."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.mesh.digest import DailyDigest
from core.mesh.metrics import FleetMetricsAggregator

logger = logging.getLogger(__name__)


class DigestPipeline:
    """Generates and delivers daily fleet digests."""

    def __init__(
        self,
        metrics: FleetMetricsAggregator,
        memory=None,  # NeuralisMemory | None
    ) -> None:
        self.metrics = metrics
        self.memory = memory
        self.daily = DailyDigest()

    def generate_digest(self) -> str:
        """Generate the daily digest from current fleet state."""
        summary = self.metrics.get_fleet_summary()
        nodes_data = [
            {
                "node_id": nid,
                "status": "healthy" if info.get("cpu_percent", 0) < 90 else "warning",
                "cpu": info.get("cpu_percent", 0),
            }
            for nid, info in summary.get("nodes", {}).items()
        ]
        tasks = []  # Would come from orchestrator
        lessons = []  # Would come from Neuralis

        report = self.daily.generate(tasks=tasks, nodes=nodes_data, lessons=lessons)
        return report

    def deliver(self) -> bool:
        """Generate, store, and deliver the digest."""
        report = self.generate_digest()
        logger.info("Daily digest generated (%d chars)", len(report))

        # Store in Neuralis
        if self.memory:
            self.memory.store_event("daily_digest", {
                "report": report,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        return True
