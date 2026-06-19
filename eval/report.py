"""Sentinel Desktop v21 — Eval report aggregation.

Provides static helpers for aggregating multiple :class:`~eval.scenario.ScenarioResult`
objects into a summary report and detecting cross-run regressions.
"""

from __future__ import annotations

from typing import Any

from eval.scenario import ScenarioResult


class EvalReport:
    """Aggregate and analyse evaluation results."""

    @staticmethod
    def aggregate(results: list[ScenarioResult]) -> dict[str, Any]:
        """Produce a summary report across multiple scenario results.

        Args:
            results: One result per scenario.

        Returns:
            Dict with overall pass rate, per-scenario scores, and a list
            of failing scenarios.
        """
        if not results:
            return {
                "total_scenarios": 0,
                "passed": 0,
                "failed": 0,
                "pass_rate": 0.0,
                "average_score": 0.0,
                "total_duration_ms": 0.0,
                "scenarios": [],
                "failing": [],
            }

        total = len(results)
        passed_count = sum(1 for r in results if r.passed)
        failing = [r.scenario_name for r in results if not r.passed]

        return {
            "total_scenarios": total,
            "passed": passed_count,
            "failed": total - passed_count,
            "pass_rate": round(passed_count / total, 4),
            "average_score": round(sum(r.score for r in results) / total, 4),
            "total_duration_ms": round(sum(r.duration_ms for r in results), 2),
            "scenarios": [
                {
                    "name": r.scenario_name,
                    "passed": r.passed,
                    "score": r.score,
                    "steps_passed": r.steps_passed,
                    "steps_total": r.steps_total,
                    "duration_ms": r.duration_ms,
                }
                for r in results
            ],
            "failing": failing,
        }

    @staticmethod
    def regression_check(
        baseline: dict[str, Any],
        current: dict[str, Any],
        threshold: float = 0.05,
    ) -> dict[str, Any]:
        """Compare two aggregate reports for regressions.

        A regression is flagged when the current ``pass_rate`` dropped by
        more than *threshold* compared to *baseline*.

        Args:
            baseline: A prior :meth:`aggregate` output.
            current: The latest :meth:`aggregate` output.
            threshold: Minimum pass-rate drop to flag as regression.

        Returns:
            Dict with ``regression`` bool, ``delta``, and lists of newly
            failing and newly passing scenarios.
        """
        baseline_rate = baseline.get("pass_rate", 0.0)
        current_rate = current.get("pass_rate", 0.0)
        delta = round(current_rate - baseline_rate, 4)

        baseline_failing = set(baseline.get("failing", []))
        current_failing = set(current.get("failing", []))

        newly_failing = sorted(current_failing - baseline_failing)
        newly_passing = sorted(baseline_failing - current_failing)

        return {
            "regression": delta < -threshold,
            "delta": delta,
            "baseline_pass_rate": baseline_rate,
            "current_pass_rate": current_rate,
            "newly_failing": newly_failing,
            "newly_passing": newly_passing,
        }
