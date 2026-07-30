"""Scheduled-task helpers for self-improvement and Empire metrics.

These helpers are designed to be registered with :class:`TaskScheduler`
(via ``add_task``) and invoked on a schedule (e.g. daily).  Each function
is importable and callable with no arguments, making them suitable as
scheduler callbacks.

Typical usage::

    scheduler = TaskScheduler(engine=agent_engine)
    scheduler.add_task(
        name="self-improvement",
        task_type="goal",
        schedule="daily_9am",
        goal="run self-improvement audit",
    )
    scheduler.add_task(
        name="empire-metrics",
        task_type="goal",
        schedule="every_1h",
        goal="run empire metrics collection",
    )

The functions below can also be called directly (e.g. from a custom
scheduler hook or for testing)::

    from core.mesh.si_scheduler import run_scheduled_si, run_scheduled_empire
    run_scheduled_si()
    run_scheduled_empire()
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _project_root() -> str:
    """Return the project root (core/mesh/si_scheduler.py → 2 levels up)."""
    return str(Path(__file__).resolve().parent.parent.parent)


def run_scheduled_si() -> str:
    """Run the self-improvement audit cycle as a scheduled task.

    Creates a :class:`SelfImprovementLoop` against the project root,
    executes one full audit cycle, and logs the result.

    Returns the audit summary string (also logged at INFO level).
    """
    from core.mesh.self_improvement import SelfImprovementLoop

    root = _project_root()
    logger.info("Scheduled self-improvement: starting audit of %s", root)
    loop = SelfImprovementLoop(root)
    report = loop.run()
    logger.info("Scheduled self-improvement: %s", report.summary)
    return report.summary


def run_scheduled_empire() -> str:
    """Run the Empire metrics collection as a scheduled task.

    Fetches base metrics (yt-stats, alpaca-pnl, buffer-metrics), computes
    the empire health score, and logs the result.

    Returns the empire score string (also logged at INFO level).
    """
    import asyncio

    from core.mesh.empire_tasks import (
        handle_alpaca_pnl,
        handle_buffer_metrics,
        handle_empire_score,
        handle_yt_stats,
    )

    logger.info("Scheduled empire: starting metrics collection")

    yt = asyncio.run(handle_yt_stats({"params": {"days": 7}}))
    alpaca = asyncio.run(handle_alpaca_pnl({"params": {"include_positions": False}}))
    buffer = asyncio.run(handle_buffer_metrics({"params": {}}))

    score = asyncio.run(handle_empire_score({"params": {
        "dependency_results": {"yt-stats": yt, "alpaca-pnl": alpaca, "buffer-metrics": buffer},
    }}))

    summary = f"Empire score: {score['total_score']}/100"
    logger.info("Scheduled empire: %s", summary)
    return summary
