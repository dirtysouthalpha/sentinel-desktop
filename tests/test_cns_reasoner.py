"""Tests for the CNS 1.0 Reasoner."""
import pytest
from core.cns.reasoner import (
    Conclusion,
    Reasoner,
    ReasoningResult,
    default_reasoner,
    _rule_all_passed,
    _rule_any_failed,
    _rule_low_score,
    _rule_retry_exhausted,
)
from core.cns.evaluator import EvalResult, EvalStatus


class TestConclusion:
    def test_conclusion_creation(self):
        c = Conclusion(rule="test", severity="info", message="all good")
        assert c.rule == "test"
        assert c.severity == "info"
        assert c.action == ""


class TestReasoningResult:
    def test_empty_result(self):
        r = ReasoningResult()
        assert r.has_critical is False
        assert r.anomalies == []

    def test_has_critical(self):
        r = ReasoningResult()
        r.conclusions = [Conclusion("x", "critical", "bad")]
        assert r.has_critical is True

    def test_no_critical(self):
        r = ReasoningResult()
        r.conclusions = [Conclusion("x", "warning", "careful")]
        assert r.has_critical is False


class TestRules:
    def test_all_passed_when_all_pass(self):
        results = [EvalResult("a", EvalStatus.PASS, 1.0)]
        conclusions = _rule_all_passed(results, {})
        assert len(conclusions) == 1
        assert conclusions[0].severity == "info"

    def test_all_passed_when_any_fails(self):
        results = [
            EvalResult("a", EvalStatus.PASS, 1.0),
            EvalResult("b", EvalStatus.FAIL, 0.2),
        ]
        conclusions = _rule_all_passed(results, {})
        assert len(conclusions) == 0

    def test_any_failed_warning(self):
        results = [
            EvalResult("a", EvalStatus.PASS, 1.0),
            EvalResult("b", EvalStatus.FAIL, 0.2),
        ]
        conclusions = _rule_any_failed(results, {})
        assert len(conclusions) == 1
        assert conclusions[0].severity == "warning"

    def test_any_failed_critical_when_majority_fail(self):
        results = [
            EvalResult("a", EvalStatus.FAIL, 0.1),
            EvalResult("b", EvalStatus.FAIL, 0.2),
            EvalResult("c", EvalStatus.PASS, 0.9),
        ]
        conclusions = _rule_any_failed(results, {})
        assert len(conclusions) == 1
        assert conclusions[0].severity == "critical"

    def test_any_failed_none(self):
        results = [EvalResult("a", EvalStatus.PASS, 1.0)]
        conclusions = _rule_any_failed(results, {})
        assert len(conclusions) == 0

    def test_low_score_triggers(self):
        results = [EvalResult("a", EvalStatus.FAIL, 0.3)]
        conclusions = _rule_low_score(results, {})
        assert len(conclusions) == 1
        assert conclusions[0].severity == "warning"
        assert "restructuring" in conclusions[0].message.lower() or "re-plan" in conclusions[0].action.lower()

    def test_low_score_not_triggered(self):
        results = [EvalResult("a", EvalStatus.PASS, 0.9)]
        conclusions = _rule_low_score(results, {})
        assert len(conclusions) == 0

    def test_retry_exhausted_triggers(self):
        conclusions = _rule_retry_exhausted([], {"retried": 3})
        assert len(conclusions) == 1
        assert conclusions[0].severity == "warning"

    def test_retry_exhausted_not_triggered(self):
        conclusions = _rule_retry_exhausted([], {"retried": 0})
        assert len(conclusions) == 0


class TestReasoner:
    def test_default_reasoner_has_rules(self):
        """Default reasoner comes with built-in rules."""
        r = default_reasoner()
        results = [EvalResult("a", EvalStatus.PASS, 1.0)]
        output = r.reason(results)
        assert len(output.conclusions) >= 1

    def test_reasoner_no_rules(self):
        """Empty reasoner produces no conclusions."""
        r = Reasoner()
        output = r.reason([])
        assert output.conclusions == []

    def test_register_custom_rule(self):
        """Custom rules can be registered."""
        def my_rule(results, findings):
            return [Conclusion("custom", "info", "custom rule fired")]

        r = Reasoner()
        r.register(my_rule)
        output = r.reason([])
        assert len(output.conclusions) == 1
        assert output.conclusions[0].rule == "custom"

    def test_anomalies_extracted(self):
        """Warning/critical conclusions become anomalies."""
        r = default_reasoner()
        results = [
            EvalResult("a", EvalStatus.FAIL, 0.1),
            EvalResult("b", EvalStatus.FAIL, 0.2),
        ]
        output = r.reason(results)
        assert len(output.anomalies) >= 1

    def test_recommendations_extracted(self):
        """Conclusions with actions become recommendations."""
        r = default_reasoner()
        results = [EvalResult("a", EvalStatus.FAIL, 0.1)]
        output = r.reason(results, {"retried": 2})
        assert len(output.recommendations) >= 1

    def test_rule_exception_caught(self):
        """A failing rule doesn't crash the reasoner."""
        def bad_rule(results, findings):
            raise RuntimeError("boom")

        r = default_reasoner()
        r.register(bad_rule)
        # Should not raise
        output = r.reason([EvalResult("a", EvalStatus.PASS, 1.0)])
        assert output is not None
