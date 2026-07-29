"""Tests for the CNS 1.0 Evaluator."""
import pytest
from core.cns.evaluator import (
    Evaluator,
    EvalResult,
    EvalStatus,
    compute_score,
)


class TestEvalResult:
    def test_eval_result_creation(self):
        result = EvalResult(
            subtask_id="a",
            status=EvalStatus.PASS,
            score=0.9,
            feedback="All good",
        )
        assert result.subtask_id == "a"
        assert result.status == EvalStatus.PASS
        assert result.score == 0.9

    def test_eval_result_pass_threshold(self):
        """Result with score >= threshold is passing."""
        result = EvalResult(subtask_id="a", status=EvalStatus.PASS, score=0.8)
        assert result.is_passing(threshold=0.7) is True
        assert result.is_passing(threshold=0.9) is False


class TestComputeScore:
    def test_perfect_score(self):
        """Matching output scores 1.0."""
        score = compute_score(expected="success", actual="success")
        assert score == 1.0

    def test_zero_score(self):
        """Completely different output scores 0.0."""
        score = compute_score(expected="alpha", actual="beta")
        assert score == 0.0

    def test_partial_score(self):
        """Partial match scores between 0 and 1."""
        score = compute_score(expected="disk usage 80%", actual="disk usage 90%")
        assert 0.0 < score < 1.0

    def test_empty_actual_scores_zero(self):
        """Empty actual output scores 0."""
        score = compute_score(expected="something", actual="")
        assert score == 0.0

    def test_case_insensitive(self):
        """Scoring is case-insensitive."""
        score = compute_score(expected="SUCCESS", actual="success")
        assert score == 1.0


class TestEvaluator:
    def test_evaluate_success(self):
        """Evaluator marks matching output as PASS."""
        ev = Evaluator()
        result = ev.evaluate(
            subtask_id="a",
            expected="disk check complete",
            actual="disk check complete",
        )
        assert result.status == EvalStatus.PASS
        assert result.score == 1.0

    def test_evaluate_failure(self):
        """Evaluator marks mismatched output as FAIL."""
        ev = Evaluator()
        result = ev.evaluate(
            subtask_id="a",
            expected="success",
            actual="error: timeout",
        )
        assert result.status == EvalStatus.FAIL

    def test_evaluate_with_custom_threshold(self):
        """Custom pass threshold changes pass/fail boundary."""
        ev = Evaluator(pass_threshold=0.5)
        result = ev.evaluate(subtask_id="a", expected="abc xyz", actual="abc def")
        # Partial match — with a 0.5 threshold this should pass
        assert result.score >= 0
        assert result.status == EvalStatus.PASS

    def test_evaluate_batch(self):
        """Batch evaluation returns results for all subtasks."""
        ev = Evaluator()
        cases = [
            {"subtask_id": "a", "expected": "ok", "actual": "ok"},
            {"subtask_id": "b", "expected": "done", "actual": "failed"},
        ]
        results = ev.evaluate_batch(cases)
        assert len(results) == 2
        assert results[0].status == EvalStatus.PASS
        assert results[1].status == EvalStatus.FAIL

    def test_compute_overall_score(self):
        """Overall score is the average of individual scores."""
        ev = Evaluator()
        results = [
            EvalResult("a", EvalStatus.PASS, 1.0),
            EvalResult("b", EvalStatus.PASS, 0.5),
            EvalResult("c", EvalStatus.FAIL, 0.0),
        ]
        overall = ev.overall_score(results)
        assert overall == pytest.approx(0.5)

    def test_compute_overall_score_empty(self):
        """Overall score of empty results is 0."""
        ev = Evaluator()
        assert ev.overall_score([]) == 0.0

    def test_summary_generates_report(self):
        """Summary produces a human-readable report."""
        ev = Evaluator()
        results = [
            EvalResult("a", EvalStatus.PASS, 1.0),
            EvalResult("b", EvalStatus.FAIL, 0.2, feedback="timeout"),
        ]
        summary = ev.summary(results)
        assert "Passed:  1" in summary
        assert "Failed:  1" in summary
        assert "b: timeout" in summary
