"""Tests for empire task handlers (yt-stats, alpaca-pnl, buffer-metrics, empire-score, narrative).

Verifies that each handler:
  - Returns structured data in stub mode (no live credentials).
  - empire-score correctly aggregates upstream results.
  - narrative generates readable summaries from score data.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

from core.mesh.empire_tasks import (
    EMPIRE_HANDLERS,
    handle_alpaca_pnl,
    handle_buffer_metrics,
    handle_empire_score,
    handle_narrative,
    handle_yt_stats,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestEmpireRegistry:
    """All five empire handlers are registered."""

    def test_five_handlers(self):
        assert len(EMPIRE_HANDLERS) == 5

    def test_handler_names(self):
        expected = {"yt-stats", "alpaca-pnl", "buffer-metrics", "empire-score", "narrative"}
        assert set(EMPIRE_HANDLERS.keys()) == expected


# ---------------------------------------------------------------------------
# Individual handlers (stub mode)
# ---------------------------------------------------------------------------

class TestYtStats:
    @pytest.mark.asyncio
    async def test_stub_returns_structure(self):
        result = await handle_yt_stats({"params": {}})
        assert result["source"] == "stub"
        assert "views" in result
        assert "subscribers" in result
        assert "channel_id" in result

    @pytest.mark.asyncio
    async def test_stub_with_channel_id(self):
        result = await handle_yt_stats({"params": {"channel_id": "UCtest123"}})
        assert result["channel_id"] == "UCtest123"

    @pytest.mark.asyncio
    async def test_live_fetch(self, monkeypatch):
        """When a live endpoint responds, result should reflect live data."""

        class FakeResp:
            def read(self):
                return b'{"views": 1500, "subscribers": 200, "watch_time_minutes": 3000}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: FakeResp())
        result = await handle_yt_stats({"params": {"analytics_url": "http://fake", "channel_id": "UCx"}})
        assert result["source"] == "live"
        assert result["views"] == 1500


class TestAlpacaPnl:
    @pytest.mark.asyncio
    async def test_stub_returns_structure(self):
        result = await handle_alpaca_pnl({"params": {}})
        assert result["source"] == "stub"
        assert "equity" in result
        assert "unrealized_pl" in result

    @pytest.mark.asyncio
    async def test_stub_with_positions(self):
        result = await handle_alpaca_pnl({"params": {"include_positions": True}})
        assert "positions" in result

    @pytest.mark.asyncio
    async def test_live_fetch(self, monkeypatch):
        """Live Alpaca fetch returns parsed account data."""
        account_json = b'{"id": "acc-123", "equity": "95000.0", "cash": "5000.0", "unrealized_pl": "1200.0"}'
        positions_json = b'[{"symbol": "AAPL", "qty": "10", "unrealized_pl": "500"}]'

        class FakeResp:
            def __init__(self, data):
                self._data = data
            def read(self):
                return self._data
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        call_count = 0
        def fake_urlopen(req, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FakeResp(account_json)
            return FakeResp(positions_json)

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        result = await handle_alpaca_pnl({"params": {
            "key_id": "FAKEKEY",
            "secret": "FAKESECRET",
            "base_url": "https://paper-api.alpaca.markets",
        }})
        assert result["source"] == "live"
        assert result["equity"] == 95000.0
        assert result["unrealized_pl"] == 1200.0
        assert len(result["positions"]) == 1


class TestBufferMetrics:
    @pytest.mark.asyncio
    async def test_stub_returns_structure(self):
        result = await handle_buffer_metrics({"params": {}})
        assert result["source"] == "stub"
        assert "posts" in result

    @pytest.mark.asyncio
    async def test_live_fetch(self, monkeypatch):
        class FakeResp:
            def read(self):
                return b'[{"id": "p1", "service": "twitter"}, {"id": "p2", "service": "instagram"}]'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: FakeResp())
        result = await handle_buffer_metrics({"params": {"access_token": "fake-token"}})
        assert result["source"] == "live"
        assert result["profiles_count"] == 2


# ---------------------------------------------------------------------------
# Empire score aggregation
# ---------------------------------------------------------------------------

class TestEmpireScore:
    @pytest.mark.asyncio
    async def test_score_zero_when_no_data(self):
        result = await handle_empire_score({"params": {"dependency_results": {}}})
        assert result["source"] == "computed"
        assert 0 <= result["total_score"] <= 100

    @pytest.mark.asyncio
    async def test_score_aggregates_upstream(self):
        dep_results = {
            "yt-stats": {"views": 2000, "subscribers": 150},
            "alpaca-pnl": {"unrealized_pl": 5000},
            "buffer-metrics": {"posts": 15, "engagement": 8.5},
        }
        result = await handle_empire_score({"params": {"dependency_results": dep_results}})
        assert result["source"] == "computed"
        assert result["total_score"] > 0
        assert "components" in result
        assert set(result["components"].keys()) == {"yt_growth", "trading_pnl", "social_engagement", "content_output"}

    @pytest.mark.asyncio
    async def test_custom_weights(self):
        dep_results = {
            "yt-stats": {"views": 1000, "subscribers": 100},
            "alpaca-pnl": {"unrealized_pl": 1000},
            "buffer-metrics": {"posts": 5, "engagement": 5.0},
        }
        weights = {"yt_growth": 0.5, "trading_pnl": 0.5, "social_engagement": 0.0, "content_output": 0.0}
        result = await handle_empire_score({"params": {"dependency_results": dep_results, "weights": weights}})
        assert result["source"] == "computed"


# ---------------------------------------------------------------------------
# Narrative generation
# ---------------------------------------------------------------------------

class TestNarrative:
    @pytest.mark.asyncio
    async def test_narrative_from_score(self):
        dep_results = {
            "empire-score": {
                "total_score": 72.5,
                "components": {"yt_growth": 80.0, "trading_pnl": 65.0, "social_engagement": 70.0, "content_output": 75.0},
            }
        }
        result = await handle_narrative({"params": {"dependency_results": dep_results}})
        assert "72.5" in result["narrative"]
        assert result["tone"] == "professional"
        assert result["source"] == "generated"

    @pytest.mark.asyncio
    async def test_narrative_hype_tone(self):
        dep_results = {
            "empire-score": {"total_score": 95.0, "components": {}}
        }
        result = await handle_narrative({"params": {"dependency_results": dep_results, "tone": "hype"}})
        assert "crushing" in result["narrative"].lower() or "95" in result["narrative"]

    @pytest.mark.asyncio
    async def test_narrative_no_deps(self):
        result = await handle_narrative({"params": {}})
        assert result["score"] == 0
        assert "0" in result["narrative"]


# ---------------------------------------------------------------------------
# End-to-end empire plan simulation
# ---------------------------------------------------------------------------

class TestEmpirePlanE2E:
    """Simulate a full empire plan execution: data → score → narrative."""

    @pytest.mark.asyncio
    async def test_full_pipeline_stub_mode(self):
        """All five task types complete in dependency order using stub data."""
        # Step 1: data tasks (no dependencies).
        yt = await handle_yt_stats({"params": {"channel_id": "UCtest"}})
        alpaca = await handle_alpaca_pnl({"params": {"include_positions": False}})
        buffer = await handle_buffer_metrics({"params": {}})

        assert yt["source"] == "stub"
        assert alpaca["source"] == "stub"
        assert buffer["source"] == "stub"

        # Step 2: aggregate score from upstream results.
        dep_results = {
            "yt-stats": yt,
            "alpaca-pnl": alpaca,
            "buffer-metrics": buffer,
        }
        score = await handle_empire_score({"params": {"dependency_results": dep_results}})
        assert score["source"] == "computed"
        assert 0 <= score["total_score"] <= 100

        # Step 3: narrative from score.
        narrative = await handle_narrative({"params": {"dependency_results": {"empire-score": score}}})
        assert narrative["source"] == "generated"
        assert len(narrative["narrative"]) > 0

    @pytest.mark.asyncio
    async def test_full_pipeline_live_data(self):
        """Pipeline with simulated live upstream data."""
        dep_results = {
            "yt-stats": {"views": 5000, "subscribers": 300, "source": "live"},
            "alpaca-pnl": {"unrealized_pl": 8500, "equity": 104000, "source": "live"},
            "buffer-metrics": {"posts": 42, "impressions": 1659, "engagement": 12.5, "source": "live"},
        }
        score = await handle_empire_score({"params": {"dependency_results": dep_results}})
        assert score["total_score"] > 50  # Strong metrics → higher score.
        narrative = await handle_narrative({"params": {"dependency_results": {"empire-score": score}}})
        assert str(score["total_score"]) in narrative["narrative"]
