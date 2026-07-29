"""Tests for the golden eval suite.

Verifies that all registered evals execute and produce valid results,
and that the report aggregates correctly.
"""
from __future__ import annotations

import pytest

from core.mesh.golden_evals import (
    EvalComponent,
    EvalPriority,
    EvalReport,
    EvalResult,
    EvalSuite,
    suite as global_suite,
)


class TestEvalReport:
    """Report aggregation logic."""

    def test_pass_rate_all_pass(self):
        report = EvalReport(timestamp="2026-01-01T00:00:00Z")
        report.results = [
            EvalResult("a", EvalComponent.MESH, EvalPriority.HIGH, True, 0.1),
            EvalResult("b", EvalComponent.MESH, EvalPriority.HIGH, True, 0.1),
        ]
        assert report.pass_rate == 100.0
        assert report.critical_failures == []

    def test_pass_rate_mixed(self):
        report = EvalReport(timestamp="2026-01-01T00:00:00Z")
        report.results = [
            EvalResult("a", EvalComponent.MESH, EvalPriority.HIGH, True, 0.1),
            EvalResult("b", EvalComponent.EMPIRE, EvalPriority.CRITICAL, False, 0.1, "fail"),
        ]
        assert report.pass_rate == 50.0
        assert len(report.critical_failures) == 1

    def test_pass_rate_empty(self):
        report = EvalReport(timestamp="2026-01-01T00:00:00Z")
        assert report.pass_rate == 0.0

    def test_by_component(self):
        report = EvalReport(timestamp="2026-01-01T00:00:00Z")
        report.results = [
            EvalResult("a", EvalComponent.MESH, EvalPriority.HIGH, True, 0.1),
            EvalResult("b", EvalComponent.EMPIRE, EvalPriority.HIGH, True, 0.1),
            EvalResult("c", EvalComponent.MESH, EvalPriority.MEDIUM, False, 0.1),
        ]
        groups = report.by_component()
        assert len(groups["mesh"]) == 2
        assert len(groups["empire"]) == 1

    def test_summary_contains_rate(self):
        report = EvalReport(timestamp="2026-01-01T00:00:00Z")
        report.results = [
            EvalResult("a", EvalComponent.MESH, EvalPriority.HIGH, True, 0.1),
        ]
        s = report.summary()
        assert "100.0%" in s
        assert "mesh" in s


class TestEvalSuite:
    """Suite registration and execution."""

    def test_register_and_run(self):
        s = EvalSuite()

        @s.register(EvalComponent.MESH, EvalPriority.HIGH)
        def sample_eval() -> bool:
            return True

        report = s.run()
        assert report.total == 1
        assert report.passed == 1
        assert report.results[0].name == "sample_eval"

    def test_run_captures_exception(self):
        s = EvalSuite()

        @s.register(EvalComponent.MESH)
        def failing_eval() -> bool:
            raise RuntimeError("boom")

        report = s.run()
        assert report.total == 1
        assert report.failed == 1
        assert "boom" in report.results[0].message

    def test_run_handles_tuple_result(self):
        s = EvalSuite()

        @s.register(EvalComponent.MESH)
        def tuple_eval() -> tuple[bool, str]:
            return (False, "known failure")

        report = s.run()
        assert report.failed == 1
        assert report.results[0].message == "known failure"


class TestGlobalSuite:
    """The pre-populated global suite has evals registered."""

    def test_has_mesh_evals(self):
        report = global_suite.run()
        components = {r.component for r in report.results}
        assert EvalComponent.MESH in components

    def test_has_critical_evals(self):
        report = global_suite.run()
        criticals = [r for r in report.results if r.priority == EvalPriority.CRITICAL]
        assert len(criticals) >= 3

    def test_all_evals_execute(self):
        """Every registered eval runs without throwing."""
        report = global_suite.run()
        assert report.total > 0
        # No eval should have an exception message that indicates a bug in the eval itself.
        for r in report.results:
            assert "Traceback" not in r.message

    def test_report_summary(self):
        report = global_suite.run()
        s = report.summary()
        assert "Golden Eval Report" in s
        assert str(report.total) in s
