"""Sentinel Desktop v21 — Evaluation harness.

Provides deterministic replay of recorded scenarios through ActionExecutor,
per-step scoring, regression detection, and aggregate reporting.

Usage::

    from eval.registry import EvalRegistry
    from eval.runner import ScenarioRunner

    registry = EvalRegistry()
    runner = ScenarioRunner(executor_fn=my_executor.execute)
    result = runner.run(registry.load("click_notepad"))
    print(result.score)
"""

from eval.registry import EvalRegistry
from eval.report import EvalReport
from eval.runner import ScenarioRunner
from eval.scenario import Scenario, ScenarioResult, ScenarioStep, ScenarioStepResult

__all__ = [
    "Scenario",
    "ScenarioStep",
    "ScenarioResult",
    "ScenarioStepResult",
    "ScenarioRunner",
    "EvalRegistry",
    "EvalReport",
]
