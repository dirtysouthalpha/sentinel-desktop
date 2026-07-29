"""Integration test: empire tasks execute through the full TaskExecutor pipeline.

Verifies that empire task types (yt-stats, alpaca-pnl, buffer-metrics,
empire-score, narrative) are dispatched by TaskExecutor, executed, and
produce TASK_COMPLETED events on the live EventBus.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
import pytest_asyncio

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.executor import TaskExecutor
from core.mesh.node import NodeCapabilities, NodePriority
from core.mesh.task_graph import TaskGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _wait_for(predicate: Callable[[], bool], *, attempts: int = 100, interval: float = 0.1) -> bool:
    for _ in range(attempts):
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def executor_setup():
    """Set up an EventBus + TaskExecutor for empire task integration testing."""
    bus = EventBus()
    caps = NodeCapabilities(can_orchestrate=False, can_execute_desktop=True)
    executor = TaskExecutor(node_id="empire-test-node", bus=bus, capabilities=caps)
    executor.start()

    yield {"bus": bus, "executor": executor}

    executor.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmpireTasksViaExecutor:
    """Empire tasks flow through TaskExecutor → EventBus pipeline."""

    @pytest.mark.asyncio
    async def test_yt_stats_completes(self, executor_setup):
        """yt-stats task produces TASK_COMPLETED with structured data."""
        received: list[dict[str, Any]] = []
        executor_setup["bus"].subscribe(
            FleetEvent.TASK_COMPLETED, lambda env: received.append(env)
        )

        await executor_setup["bus"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "emp-yt-1",
            "plan_id": "empire-plan-1",
            "node_id": "empire-test-node",
            "task_type": "yt-stats",
            "goal": "fetch YouTube stats",
            "params": {"channel_id": "UCtest"},
        })

        arrived = await _wait_for(lambda: len(received) > 0, attempts=100)
        assert arrived, "TASK_COMPLETED never arrived for yt-stats task"

        result = received[0]["data"]["result"]
        assert result["source"] == "stub"
        assert "views" in result
        assert result["channel_id"] == "UCtest"

    @pytest.mark.asyncio
    async def test_alpaca_pnl_completes(self, executor_setup):
        """alpaca-pnl task produces TASK_COMPLETED."""
        received: list[dict[str, Any]] = []
        executor_setup["bus"].subscribe(
            FleetEvent.TASK_COMPLETED, lambda env: received.append(env)
        )

        await executor_setup["bus"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "emp-alp-1",
            "plan_id": "empire-plan-1",
            "node_id": "empire-test-node",
            "task_type": "alpaca-pnl",
            "goal": "fetch Alpaca P&L",
            "params": {"include_positions": False},
        })

        arrived = await _wait_for(lambda: len(received) > 0, attempts=100)
        assert arrived, "TASK_COMPLETED never arrived for alpaca-pnl task"

        result = received[0]["data"]["result"]
        assert result["source"] == "stub"
        assert "equity" in result

    @pytest.mark.asyncio
    async def test_buffer_metrics_completes(self, executor_setup):
        """buffer-metrics task produces TASK_COMPLETED."""
        received: list[dict[str, Any]] = []
        executor_setup["bus"].subscribe(
            FleetEvent.TASK_COMPLETED, lambda env: received.append(env)
        )

        await executor_setup["bus"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "emp-buf-1",
            "plan_id": "empire-plan-1",
            "node_id": "empire-test-node",
            "task_type": "buffer-metrics",
            "goal": "fetch Buffer metrics",
            "params": {},
        })

        arrived = await _wait_for(lambda: len(received) > 0, attempts=100)
        assert arrived, "TASK_COMPLETED never arrived for buffer-metrics task"

        result = received[0]["data"]["result"]
        assert result["source"] == "stub"
        assert "posts" in result

    @pytest.mark.asyncio
    async def test_empire_score_completes(self, executor_setup):
        """empire-score task aggregates upstream results."""
        received: list[dict[str, Any]] = []
        executor_setup["bus"].subscribe(
            FleetEvent.TASK_COMPLETED, lambda env: received.append(env)
        )

        dep_results = {
            "yt-stats": {"views": 3000, "subscribers": 250},
            "alpaca-pnl": {"unrealized_pl": 4000},
            "buffer-metrics": {"posts": 20, "engagement": 9.0},
        }

        await executor_setup["bus"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "emp-score-1",
            "plan_id": "empire-plan-1",
            "node_id": "empire-test-node",
            "task_type": "empire-score",
            "goal": "compute empire score",
            "params": {"dependency_results": dep_results},
        })

        arrived = await _wait_for(lambda: len(received) > 0, attempts=100)
        assert arrived, "TASK_COMPLETED never arrived for empire-score task"

        result = received[0]["data"]["result"]
        assert result["source"] == "computed"
        assert result["total_score"] > 0
        assert "components" in result

    @pytest.mark.asyncio
    async def test_narrative_completes(self, executor_setup):
        """narrative task generates a summary from score data."""
        received: list[dict[str, Any]] = []
        executor_setup["bus"].subscribe(
            FleetEvent.TASK_COMPLETED, lambda env: received.append(env)
        )

        dep_results = {
            "empire-score": {
                "total_score": 68.3,
                "components": {"yt_growth": 75.0, "trading_pnl": 60.0, "social_engagement": 70.0, "content_output": 68.0},
            }
        }

        await executor_setup["bus"].publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "emp-narr-1",
            "plan_id": "empire-plan-1",
            "node_id": "empire-test-node",
            "task_type": "narrative",
            "goal": "generate narrative summary",
            "params": {"dependency_results": dep_results, "tone": "professional"},
        })

        arrived = await _wait_for(lambda: len(received) > 0, attempts=100)
        assert arrived, "TASK_COMPLETED never arrived for narrative task"

        result = received[0]["data"]["result"]
        assert result["source"] == "generated"
        assert "68.3" in result["narrative"]

    @pytest.mark.asyncio
    async def test_full_empire_plan_five_tasks(self, executor_setup):
        """All five empire task types execute in a single plan."""
        completed: list[dict[str, Any]] = []
        executor_setup["bus"].subscribe(
            FleetEvent.TASK_COMPLETED, lambda env: completed.append(env)
        )

        tasks = [
            {"task_id": "yt-1", "task_type": "yt-stats", "params": {"channel_id": "UCfull"}},
            {"task_id": "alp-1", "task_type": "alpaca-pnl", "params": {"include_positions": False}},
            {"task_id": "buf-1", "task_type": "buffer-metrics", "params": {}},
            {"task_id": "score-1", "task_type": "empire-score", "params": {
                "dependency_results": {
                    "yt-stats": {"views": 5000, "subscribers": 400},
                    "alpaca-pnl": {"unrealized_pl": 6000},
                    "buffer-metrics": {"posts": 30, "engagement": 8.0},
                }
            }},
            {"task_id": "narr-1", "task_type": "narrative", "params": {
                "dependency_results": {"empire-score": {"total_score": 75.0, "components": {}}},
                "tone": "casual",
            }},
        ]

        for t in tasks:
            await executor_setup["bus"].publish(FleetEvent.TASK_ASSIGNED, {
                "task_id": t["task_id"],
                "plan_id": "empire-full-plan",
                "node_id": "empire-test-node",
                "task_type": t["task_type"],
                "goal": f"empire task {t['task_id']}",
                "params": t["params"],
            })

        # Wait for all 5 to complete.
        arrived = await _wait_for(lambda: len(completed) >= 5, attempts=200)
        assert arrived, f"Expected 5 TASK_COMPLETED events, got {len(completed)}"

        # Verify each task type produced valid results.
        by_id = {c["data"]["task_id"]: c["data"]["result"] for c in completed}
        assert by_id["yt-1"]["source"] == "stub"
        assert by_id["alp-1"]["source"] == "stub"
        assert by_id["buf-1"]["source"] == "stub"
        assert by_id["score-1"]["source"] == "computed"
        assert by_id["narr-1"]["source"] == "generated"
