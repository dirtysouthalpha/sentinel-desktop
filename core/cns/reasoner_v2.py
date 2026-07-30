"""CNS Causal Reasoner — enhanced reasoning with causal rule detection.

Extends the v1.0 Reasoner pattern with causal reasoning capabilities.
On top of the standard rule-based analysis, the CausalReasoner detects
trends across reasoning iterations:

  - Cascade failure: 3+ subtasks fail simultaneously → systemic issue
  - Improving trend: scores increasing over iterations → recovery working
  - Plateau: scores flat for 3+ iterations → stuck, try different approach

The CausalReasoner accepts a `history` parameter — a list of past
ReasoningResult — enabling trend detection across the agent loop.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from core.cns.evaluator import EvalResult, EvalStatus
from core.cns.reasoner import Conclusion, ReasoningResult

logger = logging.getLogger(__name__)

# Causal rule signature: takes (results, findings, history) -> list[Conclusion].
CausalRule = Callable[
    [list[EvalResult], dict[str, Any], list[ReasoningResult]],
    list[Conclusion],
]


@dataclass
class CausalRuleEntry:
    """A registered causal rule with its condition and metadata.

    Attributes:
        name: Human-readable name of the rule.
        condition: Callable that checks whether the rule applies.
        conclusion: The Conclusion to emit when the condition is true.
    """
    name: str
    condition: Callable[[list[EvalResult], dict[str, Any], list[ReasoningResult]], bool]
    conclusion: Conclusion


class CausalReasoner:
    """Enhanced reasoner with causal rule detection over iteration history.

    Extends the v1.0 Reasoner pattern by accepting a `history` of past
    ReasoningResult instances, enabling trend-based causal inference.
    Built-in rules detect cascade failures, improving trends, and plateaus.

    Example:
        reasoner = CausalReasoner()
        result = reasoner.reason(results, findings, history=[prev_result])
    """

    def __init__(self) -> None:
        self._causal_rules: list[CausalRuleEntry] = []
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register the built-in causal rules."""
        self._causal_rules.append(CausalRuleEntry(
            name="cascade_failure",
            condition=_rule_cascade_failure,
            conclusion=Conclusion(
                rule="cascade_failure",
                severity="critical",
                message="Cascade failure detected: 3+ subtasks failed.",
                action="Investigate systemic issue — check shared dependencies or environment.",
            ),
        ))
        self._causal_rules.append(CausalRuleEntry(
            name="improving_trend",
            condition=_rule_improving_trend,
            conclusion=Conclusion(
                rule="improving_trend",
                severity="info",
                message="Scores are improving across iterations — recovery is working.",
                action="Continue current approach; monitor for stabilization.",
            ),
        ))
        self._causal_rules.append(CausalRuleEntry(
            name="plateau",
            condition=_rule_plateau,
            conclusion=Conclusion(
                rule="plateau",
                severity="warning",
                message="Scores have plateaued for 3+ iterations — stuck.",
                action="Try a different approach or decompose into smaller subtasks.",
            ),
        ))

    def register_causal_rule(
        self,
        condition: Callable[[list[EvalResult], dict[str, Any], list[ReasoningResult]], bool],
        conclusion: Conclusion,
        name: str = "",
    ) -> None:
        """Register a custom causal rule.

        Args:
            condition: A callable that receives (results, findings, history)
                       and returns True if the rule should fire.
            conclusion: The Conclusion to emit when the condition is true.
            name: Optional name for the rule (used in logging).
        """
        rule_name = name or conclusion.rule or f"causal_rule_{len(self._causal_rules)}"
        self._causal_rules.append(CausalRuleEntry(
            name=rule_name,
            condition=condition,
            conclusion=conclusion,
        ))
        logger.debug("Registered causal rule '%s'", rule_name)

    def reason(
        self,
        results: list[EvalResult],
        findings: dict[str, Any] | None = None,
        history: list[ReasoningResult] | None = None,
    ) -> ReasoningResult:
        """Apply causal rules to evaluation results with history.

        Args:
            results: Current iteration's evaluation results.
            findings: Additional context (retry counts, timing, etc.).
            history: List of past ReasoningResult for trend detection.

        Returns:
            ReasoningResult with conclusions, anomalies, recommendations.
        """
        if findings is None:
            findings = {}
        if history is None:
            history = []

        output = ReasoningResult()

        for entry in self._causal_rules:
            try:
                fired = entry.condition(results, findings, history)
                if fired:
                    output.conclusions.append(entry.conclusion)
            except Exception as e:
                logger.warning("Causal rule '%s' failed: %s", entry.name, e)

        # Derive anomalies and recommendations from conclusions.
        for c in output.conclusions:
            if c.severity in ("warning", "critical"):
                output.anomalies.append(c.message)
            if c.action:
                output.recommendations.append(c.action)

        return output


# ---------------------------------------------------------------------------
# Built-in causal rule conditions
# ---------------------------------------------------------------------------

def _rule_cascade_failure(
    results: list[EvalResult],
    findings: dict[str, Any],
    history: list[ReasoningResult],
) -> bool:
    """True if 3 or more subtasks failed simultaneously (systemic issue)."""
    failed = [r for r in results if r.status == EvalStatus.FAIL]
    return len(failed) >= 3


def _rule_improving_trend(
    results: list[EvalResult],
    findings: dict[str, Any],
    history: list[ReasoningResult],
) -> bool:
    """True if overall scores are increasing across iterations.

    Uses the anomaly count from past ReasoningResult entries as a proxy:
    if anomalies are decreasing and the current iteration has a decent
    average score, the recovery is working.
    """
    if len(history) < 2:
        return False

    if not results:
        return False

    current_avg = sum(r.score for r in results) / len(results)
    current_anomalies = sum(1 for r in results if r.status == EvalStatus.FAIL)

    # Compare against the last 2 history entries.
    recent = history[-2:]
    # All past entries must have had more anomalies than now, and current
    # score must be above a minimum threshold.
    all_worse_before = all(
        len(h.anomalies) > current_anomalies for h in recent
    )
    return all_worse_before and current_avg > 0.5


def _rule_plateau(
    results: list[EvalResult],
    findings: dict[str, Any],
    history: list[ReasoningResult],
) -> bool:
    """True if scores have been flat for 3+ iterations (stuck)."""
    if len(history) < 3:
        return False

    # Look at the last 3 history entries. If all have the same anomaly
    # count and the current results have failures, it's a plateau.
    recent = history[-3:]
    # Count anomalies per history entry.
    anomaly_counts = [len(h.anomalies) for h in recent]
    # Plateau: same anomaly count for all 3 iterations, and current has failures.
    if len(set(anomaly_counts)) == 1 and anomaly_counts[0] > 0:
        current_failed = any(r.status == EvalStatus.FAIL for r in results)
        return current_failed
    return False
