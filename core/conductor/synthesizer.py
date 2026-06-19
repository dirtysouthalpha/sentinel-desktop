"""Sentinel Desktop v12.0 — Result Synthesizer.

Merges results from multiple parallel agent executions into a
coherent final result. Handles success/failure aggregation,
conflict resolution, and summary generation.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ResultSynthesizer:
    """Synthesize multi-agent results into a single coherent output.

    Usage::

        synthesizer = ResultSynthesizer()
        final = synthesizer.synthesize(goal, subtask_results)
    """

    def synthesize(
        self,
        goal: str,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Synthesize subtask results into a final result.

        Args:
            goal: The original goal.
            results: List of per-subtask result dicts.

        Returns:
            Final synthesized result dict.
        """
        total = len(results)
        successes = [r for r in results if r.get("status") == "success"]
        failures = [r for r in results if r.get("status") not in ("success",)]
        errors = [r for r in results if r.get("status") == "error"]
        timeouts = [r for r in results if r.get("status") == "timeout"]

        # Determine overall status
        if not results:
            overall_status = "no_tasks"
        elif len(successes) == total:
            overall_status = "success"
        elif len(successes) > 0:
            overall_status = "partial"
        elif errors:
            overall_status = "error"
        else:
            overall_status = "failed"

        # Build summary
        summary_parts = []
        for r in results:
            desc = r.get("description", r.get("subtask_id", "unknown"))
            status = r.get("status", "unknown")
            summary_parts.append(f"{desc}: {status}")

        final = {
            "goal": goal,
            "status": overall_status,
            "success": overall_status in ("success", "partial"),
            "summary": "; ".join(summary_parts),
            "tasks_total": total,
            "tasks_succeeded": len(successes),
            "tasks_failed": len(failures),
            "tasks_errored": len(errors),
            "tasks_timed_out": len(timeouts),
            "results": results,
        }

        logger.info(
            "Synthesized %d tasks: %s (%d succeeded, %d failed)",
            total,
            overall_status,
            len(successes),
            len(failures),
        )

        return final

    def extract_errors(self, results: list[dict[str, Any]]) -> list[str]:
        """Extract all error messages from results."""
        errors = []
        for r in results:
            if r.get("error"):
                errors.append(f"{r.get('subtask_id', '?')}: {r['error']}")
        return errors

    def extract_data(self, results: list[dict[str, Any]]) -> list[Any]:
        """Extract result data from successful tasks."""
        data = []
        for r in results:
            if r.get("status") == "success" and "result" in r:
                data.append(r["result"])
        return data
