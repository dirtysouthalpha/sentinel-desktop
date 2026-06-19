"""Tests for the eval/ package (v21 eval harness)."""

from __future__ import annotations

import pytest

from eval.registry import EvalRegistry
from eval.report import EvalReport
from eval.runner import ScenarioRunner
from eval.scenario import Scenario, ScenarioResult, ScenarioStep, ScenarioStepResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scenario(
    name: str = "test_scenario", steps: list[ScenarioStep] | None = None
) -> Scenario:
    if steps is None:
        steps = [
            ScenarioStep(
                action="screenshot", params={}, expected_keys=["output"], expect_success=True
            ),
        ]
    return Scenario(
        name=name,
        description="A simple test scenario",
        goal="Test something",
        steps=steps,
        tags=["test"],
    )


def _success_executor(action: str, **params) -> dict:
    return {"success": True, "output": "ok"}


def _fail_executor(action: str, **params) -> dict:
    return {"success": False, "output": "nope"}


# ---------------------------------------------------------------------------
# Scenario model
# ---------------------------------------------------------------------------


class TestScenarioStep:
    def test_to_dict_roundtrip(self):
        step = ScenarioStep(action="click", params={"x": 10, "y": 20}, expected_keys=["output"])
        d = step.to_dict()
        assert d["action"] == "click"
        assert d["params"] == {"x": 10, "y": 20}
        assert d["expected_keys"] == ["output"]

    def test_from_dict(self):
        data = {
            "action": "type_text",
            "params": {"text": "hello"},
            "expected_keys": [],
            "expect_success": True,
        }
        step = ScenarioStep.from_dict(data)
        assert step.action == "type_text"
        assert step.params == {"text": "hello"}


class TestScenario:
    def test_save_and_load(self, tmp_path):
        s = _make_scenario()
        s.save(tmp_path / "s.json")
        loaded = Scenario.load(tmp_path / "s.json")
        assert loaded.name == s.name
        assert len(loaded.steps) == len(s.steps)
        assert loaded.steps[0].action == s.steps[0].action

    def test_created_roundtrips(self, tmp_path):
        s = _make_scenario()
        s.created = "2026-06-19T00:00:00+00:00"
        s.save(tmp_path / "s.json")
        loaded = Scenario.load(tmp_path / "s.json")
        assert loaded.created == "2026-06-19T00:00:00+00:00"

    def test_to_dict_contains_all_fields(self):
        s = _make_scenario()
        d = s.to_dict()
        for field in ("name", "description", "goal", "steps", "tags", "version", "created"):
            assert field in d


class TestScenarioResult:
    def test_to_dict(self):
        sr = ScenarioStepResult(
            step_number=1, action="click", passed=True, result={"success": True}, duration_ms=5.0
        )
        result = ScenarioResult(
            scenario_name="x",
            passed=True,
            steps_passed=1,
            steps_failed=0,
            steps_total=1,
            score=1.0,
            duration_ms=10.0,
            step_results=[sr],
        )
        d = result.to_dict()
        assert d["scenario_name"] == "x"
        assert d["score"] == 1.0
        assert d["passed"] is True
        assert len(d["step_results"]) == 1


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class TestScenarioRunner:
    def test_all_pass(self):
        scenario = _make_scenario()
        runner = ScenarioRunner(_success_executor)
        result = runner.run(scenario)
        assert result.passed is True
        assert result.score == 1.0
        assert result.steps_passed == 1

    def test_fail_when_success_false(self):
        scenario = _make_scenario()
        runner = ScenarioRunner(_fail_executor)
        result = runner.run(scenario)
        assert result.passed is False
        assert result.steps_failed == 1

    def test_fail_when_expected_key_missing(self):
        step = ScenarioStep(action="screenshot", expected_keys=["missing_key"], expect_success=True)
        scenario = _make_scenario(steps=[step])
        runner = ScenarioRunner(_success_executor)
        result = runner.run(scenario)
        assert result.passed is False

    def test_exception_counts_as_failure(self):
        def boom(action, **params):
            raise RuntimeError("kaboom")

        scenario = _make_scenario()
        runner = ScenarioRunner(boom)
        result = runner.run(scenario)
        assert result.passed is False
        assert result.step_results[0].error is not None

    def test_stop_on_failure(self):
        steps = [
            ScenarioStep(action="a"),
            ScenarioStep(action="b"),
        ]
        scenario = _make_scenario(steps=steps)
        runner = ScenarioRunner(_fail_executor, stop_on_failure=True)
        result = runner.run(scenario)
        assert result.steps_total == 1  # stopped after first fail

    def test_score_is_fraction(self):
        steps = [
            ScenarioStep(action="a"),
            ScenarioStep(action="b"),
        ]
        call_count = {"n": 0}

        def mixed(action, **params):
            call_count["n"] += 1
            return {"success": call_count["n"] == 1}

        scenario = _make_scenario(steps=steps)
        runner = ScenarioRunner(mixed)
        result = runner.run(scenario)
        assert result.score == pytest.approx(0.5)

    def test_empty_scenario(self):
        scenario = _make_scenario(steps=[])
        runner = ScenarioRunner(_success_executor)
        result = runner.run(scenario)
        assert result.score == 0.0
        assert result.steps_total == 0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestEvalRegistry:
    def test_list_empty(self, tmp_path):
        registry = EvalRegistry(scenarios_dir=tmp_path / "s", results_dir=tmp_path / "r")
        assert registry.list_scenarios() == []

    def test_save_and_load(self, tmp_path):
        registry = EvalRegistry(scenarios_dir=tmp_path / "s", results_dir=tmp_path / "r")
        s = _make_scenario("my_scenario")
        registry.save(s)
        assert "my_scenario" in registry.list_scenarios()
        loaded = registry.load("my_scenario")
        assert loaded.name == "my_scenario"

    def test_load_missing_raises(self, tmp_path):
        registry = EvalRegistry(scenarios_dir=tmp_path / "s", results_dir=tmp_path / "r")
        with pytest.raises(FileNotFoundError):
            registry.load("ghost")

    def test_delete(self, tmp_path):
        registry = EvalRegistry(scenarios_dir=tmp_path / "s", results_dir=tmp_path / "r")
        s = _make_scenario("deleteme")
        registry.save(s)
        assert registry.delete("deleteme") is True
        assert "deleteme" not in registry.list_scenarios()

    def test_delete_missing_returns_false(self, tmp_path):
        registry = EvalRegistry(scenarios_dir=tmp_path / "s", results_dir=tmp_path / "r")
        assert registry.delete("ghost") is False

    def test_save_result_and_list_results(self, tmp_path):
        registry = EvalRegistry(scenarios_dir=tmp_path / "s", results_dir=tmp_path / "r")
        result = ScenarioResult(
            scenario_name="x",
            passed=True,
            steps_passed=1,
            steps_failed=0,
            steps_total=1,
            score=1.0,
            duration_ms=5.0,
            step_results=[],
        )
        registry.save_result(result)
        records = registry.list_results("x", limit=10)
        assert len(records) == 1
        assert records[0]["score"] == 1.0

    def test_list_results_empty_when_no_file(self, tmp_path):
        registry = EvalRegistry(scenarios_dir=tmp_path / "s", results_dir=tmp_path / "r")
        assert registry.list_results("no_such") == []

    def test_compare_to_baseline_no_prior(self, tmp_path):
        registry = EvalRegistry(scenarios_dir=tmp_path / "s", results_dir=tmp_path / "r")
        result = ScenarioResult(
            scenario_name="x",
            passed=True,
            steps_passed=1,
            steps_failed=0,
            steps_total=1,
            score=0.9,
            duration_ms=1.0,
            step_results=[],
        )
        comparison = registry.compare_to_baseline(result)
        assert comparison["baseline_score"] is None
        assert comparison["regression"] is False

    def test_compare_to_baseline_regression(self, tmp_path):
        registry = EvalRegistry(scenarios_dir=tmp_path / "s", results_dir=tmp_path / "r")
        prior = ScenarioResult(
            scenario_name="x",
            passed=True,
            steps_passed=1,
            steps_failed=0,
            steps_total=1,
            score=1.0,
            duration_ms=1.0,
            step_results=[],
        )
        registry.save_result(prior)
        current = ScenarioResult(
            scenario_name="x",
            passed=False,
            steps_passed=0,
            steps_failed=1,
            steps_total=1,
            score=0.0,
            duration_ms=1.0,
            step_results=[],
        )
        comparison = registry.compare_to_baseline(current)
        assert comparison["regression"] is True
        assert comparison["score_delta"] == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# EvalReport
# ---------------------------------------------------------------------------


class TestEvalReport:
    def _make_result(self, name: str, score: float, passed: bool) -> ScenarioResult:
        return ScenarioResult(
            scenario_name=name,
            passed=passed,
            steps_passed=int(passed),
            steps_failed=int(not passed),
            steps_total=1,
            score=score,
            duration_ms=1.0,
            step_results=[],
        )

    def test_aggregate_empty(self):
        report = EvalReport.aggregate([])
        assert report["total_scenarios"] == 0
        assert report["pass_rate"] == 0.0

    def test_aggregate_all_pass(self):
        results = [self._make_result("a", 1.0, True), self._make_result("b", 1.0, True)]
        report = EvalReport.aggregate(results)
        assert report["pass_rate"] == 1.0
        assert report["passed"] == 2
        assert report["failed"] == 0

    def test_aggregate_mixed(self):
        results = [self._make_result("a", 1.0, True), self._make_result("b", 0.0, False)]
        report = EvalReport.aggregate(results)
        assert report["pass_rate"] == 0.5
        assert "b" in report["failing"]

    def test_regression_check_detected(self):
        baseline = {"pass_rate": 1.0, "failing": []}
        current = {"pass_rate": 0.8, "failing": ["x"]}
        check = EvalReport.regression_check(baseline, current, threshold=0.05)
        assert check["regression"] is True
        assert "x" in check["newly_failing"]

    def test_regression_check_no_regression(self):
        baseline = {"pass_rate": 0.8, "failing": ["x"]}
        current = {"pass_rate": 0.9, "failing": []}
        check = EvalReport.regression_check(baseline, current)
        assert check["regression"] is False
        assert "x" in check["newly_passing"]
