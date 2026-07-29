"""Tests for the daily digest pipeline."""
from __future__ import annotations

from unittest.mock import MagicMock

from core.mesh.digest_scheduler import DigestPipeline
from core.mesh.metrics import FleetMetricsAggregator


class TestDigestPipeline:
    def test_construct(self):
        agg = FleetMetricsAggregator()
        pipe = DigestPipeline(metrics=agg)
        assert pipe.metrics is agg

    def test_generate_digest(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 50.0, "memory_percent": 60.0})
        pipe = DigestPipeline(metrics=agg)
        report = pipe.generate_digest()
        assert "FLEET DAILY DIGEST" in report
        assert "n1" in report

    def test_deliver(self):
        agg = FleetMetricsAggregator()
        pipe = DigestPipeline(metrics=agg)
        result = pipe.deliver()
        assert result is True

    def test_deliver_with_memory(self):
        agg = FleetMetricsAggregator()
        mock_memory = MagicMock()
        pipe = DigestPipeline(metrics=agg, memory=mock_memory)
        pipe.deliver()
        mock_memory.store_event.assert_called_once()
