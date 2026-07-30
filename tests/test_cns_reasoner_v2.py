"""Tests for the CNS 2.0 Causal Reasoner."""
import pytest

from core.cns.evaluator import EvalResult, EvalStatus
from core.cns.reasoner import Conclusion, ReasoningResult
from core.cns.reasoner_v2 import CausalReasoner


def _make_result(subtask_id: str, status: EvalStatus, score: float) -> EvalResult:
    return EvalResult(subtask_id=subtask_id, status=status, score=score)


class TestCausalReasonerBuiltins:
    def test_cascade_failure_fires_on_3_failures(self):
        reasoner = CausalReasoner()
        results = [
            _make_result("a", EvalStatus.FAIL, 0.1),
            _make_result("b", EvalStatus.FAIL, 0.2),
            _make_result("c", EvalStatus.FAIL, 0.1),
        ]
        out = reasoner.reason(results)
        rules = [c.rule for c in out.conclusions]
        assert "cascade_failure" in rules

    def test_cascade_failure_not_fires_on_2_failures(self):
        reasoner = CausalReasoner()
        results = [
            _make_result("a", EvalStatus.FAIL, 0.1),
            _make_result("b", EvalStatus.FAIL, 0.2),
            _make_result("c", EvalStatus.PASS, 0.9),
        ]
        out = reasoner.reason(results)
        rules = [c.rule for c in out.conclusions]
        assert "cascade_failure" not in rules

    def test_cascade_failure_anomaly_recorded(self):
        reasoner = CausalReasoner()
        results = [
            _make_result("a", EvalStatus.FAIL, 0.1),
            _make_result("b", EvalStatus.FAIL, 0.2),
            _make_result("c", EvalStatus.FAIL, 0.1),
        ]
        out = reasoner.reason(results)
        assert len(out.anomalies) >= 1
        assert any("Cascade" in a for a in out.anomalies)

    def test_cascade_failure_recommendation(self):
        reasoner = CausalReasoner()
        results = [
            _make_result("a", EvalStatus.FAIL, 0.1),
            _make_result("b", EvalStatus.FAIL, 0.2),
            _make_result("c", EvalStatus.FAIL, 0.1),
        ]
        out = reasoner.reason(results)
        assert len(out.recommendations) >= 1

    def test_improving_trend_fires_with_history(self):
        reasoner = CausalReasoner()
        # Past history with anomalies (high anomaly count).
        past = ReasoningResult()
        past.anomalies = ["something wrong", "another issue"]
        past.conclusions = [Conclusion("x", "warning", "msg")]
        # Current results: all pass, decent score.
        results = [
            _make_result("a", EvalStatus.PASS, 0.8),
            _make_result("b", EvalStatus.PASS, 0.9),
        ]
        out = reasoner.reason(results, history=[past, past])
        rules = [c.rule for c in out.conclusions]
        assert "improving_trend" in rules

    def test_improving_trend_not_fires_without_history(self):
        reasoner = CausalReasoner()
        results = [
            _make_result("a", EvalStatus.PASS, 0.8),
            _make_result("b", EvalStatus.PASS, 0.9),
        ]
        out = reasoner.reason(results, history=[])
        rules = [c.rule for c in out.conclusions]
        assert "improving_trend" not in rules

    def test_plateau_fires_with_3_flat_iterations(self):
        reasoner = CausalReasoner()
        # 3 past iterations, each with 1 anomaly.
        history = []
        for _ in range(3):
            r = ReasoningResult()
            r.anomalies = ["stuck"]
            history.append(r)
        # Current: still has failures.
        results = [
            _make_result("a", EvalStatus.FAIL, 0.3),
            _make_result("b", EvalStatus.PASS, 0.8),
        ]
        out = reasoner.reason(results, history=history)
        rules = [c.rule for c in out.conclusions]
        assert "plateau" in rules

    def test_plateau_not_fires_with_only_2_iterations(self):
        reasoner = CausalReasoner()
        history = []
        for _ in range(2):
            r = ReasoningResult()
            r.anomalies = ["stuck"]
            history.append(r)
        results = [_make_result("a", EvalStatus.FAIL, 0.3)]
        out = reasoner.reason(results, history=history)
        rules = [c.rule for c in out.conclusions]
        assert "plateau" not in rules

    def test_plateau_not_fires_when_anomalies_vary(self):
        reasoner = CausalReasoner()
        h1 = ReasoningResult()
        h1.anomalies = ["a"]
        h2 = ReasoningResult()
        h2.anomalies = ["a", "b"]
        h3 = ReasoningResult()
        h3.anomalies = ["a"]
        results = [_make_result("x", EvalStatus.FAIL, 0.3)]
        out = reasoner.reason(results, history=[h1, h2, h3])
        rules = [c.rule for c in out.conclusions]
        assert "plateau" not in rules


class TestCausalReasonerCustomRules:
    def test_register_custom_rule(self):
        reasoner = CausalReasoner()

        def my_condition(results, findings, history):
            return True

        conclusion = Conclusion("custom", "info", "Custom fired")
        reasoner.register_causal_rule(my_condition, conclusion, name="my_rule")

        results = [_make_result("a", EvalStatus.PASS, 0.9)]
        out = reasoner.reason(results)
        rules = [c.rule for c in out.conclusions]
        assert "custom" in rules

    def test_register_custom_rule_fires_conditionally(self):
        reasoner = CausalReasoner()

        def my_condition(results, findings, history):
            return findings.get("trigger", False)

        conclusion = Conclusion("cond", "info", "Conditional")
        reasoner.register_causal_rule(my_condition, conclusion)

        results = [_make_result("a", EvalStatus.PASS, 0.9)]
        # Should NOT fire when trigger is False.
        out = reasoner.reason(results, findings={"trigger": False})
        rules = [c.rule for c in out.conclusions]
        assert "cond" not in rules
        # Should fire when trigger is True.
        out = reasoner.reason(results, findings={"trigger": True})
        rules = [c.rule for c in out.conclusions]
        assert "cond" in rules

    def test_rule_exception_does_not_crash(self):
        reasoner = CausalReasoner()

        def bad_condition(results, findings, history):
            raise RuntimeError("oops")

        conclusion = Conclusion("bad", "info", "Should not crash")
        reasoner.register_causal_rule(bad_condition, conclusion)

        results = [_make_result("a", EvalStatus.PASS, 0.9)]
        # Should not raise; the bad rule is skipped.
        out = reasoner.reason(results)
        rules = [c.rule for c in out.conclusions]
        assert "bad" not in rules

    def test_empty_results_no_crash(self):
        reasoner = CausalReasoner()
        out = reasoner.reason([])
        assert out.conclusions == []
        assert out.anomalies == []

    def test_history_none_defaults_to_empty(self):
        reasoner = CausalReasoner()
        results = [_make_result("a", EvalStatus.PASS, 0.9)]
        out = reasoner.reason(results, history=None)
        assert isinstance(out, ReasoningResult)
