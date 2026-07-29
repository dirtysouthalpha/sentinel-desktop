"""CNS Reasoner — rule-based reasoning over task outputs.

Applies a set of declarative rules to subtask results to derive
conclusions, detect anomalies, and recommend actions. This is the
"evaluate" half of the CNS loop: after the conductor executes tasks,
the reasoner interprets what happened.

Rules are simple callables: (context, findings) -> list[Conclusion].
New rules can be registered at runtime.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from core.cns.evaluator import EvalResult, EvalStatus
from core.cns.planner import TaskType

logger = logging.getLogger(__name__)

# Rule signature: takes (results, findings) and returns list[Conclusion].
Rule = Callable[[list[EvalResult], dict[str, Any]], list["Conclusion"]]


@dataclass
class Conclusion:
    """A derived insight from the reasoner."""
    rule: str
    severity: str  # info, warning, critical
    message: str
    action: str = ""  # recommended action, if any


@dataclass
class ReasoningResult:
    """Output of a reasoning pass."""
    conclusions: list[Conclusion] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(c.severity == "critical" for c in self.conclusions)


def _rule_all_passed(results: list[EvalResult], findings: dict[str, Any]) -> list[Conclusion]:
    """If all evaluations passed, emit an info conclusion."""
    if results and all(r.status == EvalStatus.PASS for r in results):
        return [Conclusion(
            rule="all_passed",
            severity="info",
            message=f"All {len(results)} subtasks passed evaluation.",
        )]
    return []


def _rule_any_failed(results: list[EvalResult], findings: dict[str, Any]) -> list[Conclusion]:
    """If any subtask failed, emit a warning or critical."""
    failed = [r for r in results if r.status == EvalStatus.FAIL]
    if not failed:
        return []

    severity = "critical" if len(failed) > len(results) / 2 else "warning"
    return [Conclusion(
        rule="any_failed",
        severity=severity,
        message=f"{len(failed)}/{len(results)} subtasks failed evaluation.",
        action="Review failed subtasks and retry with adjusted parameters.",
    )]


def _rule_low_score(results: list[EvalResult], findings: dict[str, Any]) -> list[Conclusion]:
    """If overall score is below 0.5, recommend re-planning."""
    if not results:
        return []
    avg = sum(r.score for r in results) / len(results)
    if avg < 0.5:
        return [Conclusion(
            rule="low_score",
            severity="warning",
            message=f"Overall score {avg:.2f} is below 0.5 — plan may need restructuring.",
            action="Decompose goal into smaller, more focused subtasks.",
        )]
    return []


def _rule_retry_exhausted(results: list[EvalResult], findings: dict[str, Any]) -> list[Conclusion]:
    """If any subtask exhausted retries, flag it."""
    retried = findings.get("retried", 0)
    if retried > 0:
        return [Conclusion(
            rule="retry_exhausted",
            severity="warning",
            message=f"Plan required {retried} retries — consider alternative approaches for flaky subtasks.",
            action="Investigate flaky subtasks and add resilience or fallback handlers.",
        )]
    return []


class Reasoner:
    """Rule-based reasoning engine for CNS 1.0."""

    def __init__(self) -> None:
        self._rules: list[Rule] = []

    def register(self, rule: Rule) -> None:
        """Register a new reasoning rule."""
        self._rules.append(rule)

    def reason(
        self,
        results: list[EvalResult],
        findings: dict[str, Any] | None = None,
    ) -> ReasoningResult:
        """Apply all registered rules to evaluation results.

        Args:
            results: Evaluation results from the conductor.
            findings: Additional context (retry counts, timing, etc.).

        Returns:
            ReasoningResult with conclusions, anomalies, recommendations.
        """
        if findings is None:
            findings = {}

        output = ReasoningResult()
        for rule_fn in self._rules:
            try:
                conclusions = rule_fn(results, findings)
                output.conclusions.extend(conclusions)
            except Exception as e:
                logger.warning("Reasoning rule %s failed: %s", rule_fn.__name__, e)

        # Derive anomalies and recommendations from conclusions
        for c in output.conclusions:
            if c.severity in ("warning", "critical"):
                output.anomalies.append(c.message)
            if c.action:
                output.recommendations.append(c.action)

        return output


def default_reasoner() -> Reasoner:
    """Create a reasoner pre-loaded with the built-in rules."""
    r = Reasoner()
    r.register(_rule_all_passed)
    r.register(_rule_any_failed)
    r.register(_rule_low_score)
    r.register(_rule_retry_exhausted)
    return r
