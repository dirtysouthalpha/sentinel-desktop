"""CNS Evaluator — scores subtask results and determines pass/fail.

Uses token-overlap scoring to compare expected vs actual outputs.
Handles batch evaluation, overall score computation, and summary
report generation for the conductor loop.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EvalStatus(str, Enum):
    """Outcome of a single subtask evaluation."""
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


def _tokenize(text: str) -> Counter:
    """Tokenize text into a normalized Counter of words."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return Counter(words)


def compute_score(expected: str, actual: str) -> float:
    """Compute a similarity score between expected and actual output.

    Uses token overlap (Dice coefficient) for robust partial matching.
    Returns 0.0 to 1.0.
    """
    if not expected or not actual:
        return 0.0

    tokens_exp = _tokenize(expected)
    tokens_act = _tokenize(actual)

    if not tokens_exp or not tokens_act:
        return 0.0

    # Dice coefficient: 2 * |intersection| / (|A| + |B|)
    intersection = sum((tokens_exp & tokens_act).values())
    total = sum(tokens_exp.values()) + sum(tokens_act.values())
    if total == 0:
        return 0.0

    return (2.0 * intersection) / total


class EvalResult:
    """Result of evaluating a single subtask."""

    def __init__(
        self,
        subtask_id: str,
        status: EvalStatus,
        score: float,
        feedback: str = "",
    ) -> None:
        self.subtask_id = subtask_id
        self.status = status
        self.score = score
        self.feedback = feedback

    def is_passing(self, threshold: float = 0.7) -> bool:
        """True if the score meets or exceeds the threshold."""
        return self.score >= threshold


class Evaluator:
    """Evaluates subtask results against expected outputs."""

    def __init__(self, pass_threshold: float = 0.7) -> None:
        self.pass_threshold = pass_threshold

    def evaluate(
        self,
        subtask_id: str,
        expected: str,
        actual: str,
        feedback: str = "",
    ) -> EvalResult:
        """Evaluate a single subtask result."""
        score = compute_score(expected, actual)
        status = EvalStatus.PASS if score >= self.pass_threshold else EvalStatus.FAIL
        if not feedback and status == EvalStatus.FAIL:
            feedback = f"Score {score:.2f} below threshold {self.pass_threshold}"
        return EvalResult(subtask_id, status, score, feedback)

    def evaluate_batch(self, cases: list[dict[str, Any]]) -> list[EvalResult]:
        """Evaluate a batch of subtask results.

        Each case dict needs: subtask_id, expected, actual.
        Optional: feedback.
        """
        results = []
        for case in cases:
            result = self.evaluate(
                subtask_id=case["subtask_id"],
                expected=case.get("expected", ""),
                actual=case.get("actual", ""),
                feedback=case.get("feedback", ""),
            )
            results.append(result)
        return results

    def overall_score(self, results: list[EvalResult]) -> float:
        """Compute the mean score across all results."""
        if not results:
            return 0.0
        return sum(r.score for r in results) / len(results)

    def summary(self, results: list[EvalResult]) -> str:
        """Generate a human-readable summary report."""
        if not results:
            return "No evaluation results."

        passed = sum(1 for r in results if r.status == EvalStatus.PASS)
        failed = sum(1 for r in results if r.status == EvalStatus.FAIL)
        skipped = sum(1 for r in results if r.status == EvalStatus.SKIP)
        overall = self.overall_score(results)

        lines = [
            f"CNS EVALUATION SUMMARY",
            f"{'=' * 40}",
            f"  Total:   {len(results)}",
            f"  Passed:  {passed}",
            f"  Failed:  {failed}",
            f"  Skipped: {skipped}",
            f"  Score:   {overall:.2f} (threshold: {self.pass_threshold})",
        ]

        if failed > 0:
            lines.append("")
            lines.append("Failures:")
            for r in results:
                if r.status == EvalStatus.FAIL:
                    lines.append(f"  {r.subtask_id}: {r.feedback}")

        return "\n".join(lines)
