"""Sentinel Desktop v21 — Eval registry.

Manages loading, saving, listing, and result persistence for evaluation
scenarios.  Scenarios live as JSON files under ``scenarios_dir``; results
are appended to a JSONL file under ``results_dir``.

Default paths (relative to the project root):
  eval/scenarios/   — scenario JSON files
  eval/results/     — result JSONL files (one per scenario)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from eval.scenario import Scenario, ScenarioResult

logger = logging.getLogger(__name__)

# Default directories — resolved relative to this file's location
_EVAL_DIR = Path(__file__).parent
_DEFAULT_SCENARIOS = _EVAL_DIR / "scenarios"
_DEFAULT_RESULTS = _EVAL_DIR / "results"


class EvalRegistry:
    """Load/save scenarios and persist/compare run results.

    Args:
        scenarios_dir: Directory holding ``<name>.json`` scenario files.
        results_dir: Directory holding ``<name>.jsonl`` result logs.
    """

    def __init__(
        self,
        scenarios_dir: Path | None = None,
        results_dir: Path | None = None,
    ) -> None:
        self._scenarios_dir = Path(scenarios_dir or _DEFAULT_SCENARIOS)
        self._results_dir = Path(results_dir or _DEFAULT_RESULTS)
        self._scenarios_dir.mkdir(parents=True, exist_ok=True)
        self._results_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Scenario CRUD
    # ------------------------------------------------------------------

    def list_scenarios(self) -> list[str]:
        """Return names of all available scenarios (sorted)."""
        return sorted(p.stem for p in self._scenarios_dir.glob("*.json"))

    def load(self, name: str) -> Scenario:
        """Load and return a scenario by *name*.

        Raises:
            FileNotFoundError: If the scenario JSON does not exist.
        """
        path = self._scenarios_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Scenario not found: {name!r} ({path})")
        return Scenario.load(path)

    def save(self, scenario: Scenario) -> None:
        """Persist a scenario to ``scenarios_dir/<name>.json``."""
        path = self._scenarios_dir / f"{scenario.name}.json"
        scenario.save(path)
        logger.info("eval.registry: saved scenario '%s' → %s", scenario.name, path)

    def delete(self, name: str) -> bool:
        """Delete a scenario by *name*.

        Returns:
            True if the file was deleted, False if it didn't exist.
        """
        path = self._scenarios_dir / f"{name}.json"
        if path.exists():
            path.unlink()
            logger.info("eval.registry: deleted scenario '%s'", name)
            return True
        return False

    # ------------------------------------------------------------------
    # Result persistence
    # ------------------------------------------------------------------

    def save_result(self, result: ScenarioResult) -> None:
        """Append *result* to ``results_dir/<scenario_name>.jsonl``."""
        path = self._results_dir / f"{result.scenario_name}.jsonl"
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(result.to_dict()) + "\n")
        except OSError as exc:
            logger.warning("eval.registry: could not persist result: %s", exc)

    def list_results(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return up to *limit* most recent results for scenario *name*."""
        path = self._results_dir / f"{name}.jsonl"
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            results: list[dict[str, Any]] = []
            for line in lines[-limit:]:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            return results
        except OSError:
            return []

    def compare_to_baseline(self, result: ScenarioResult) -> dict[str, Any]:
        """Compare *result* against the most recent prior run (baseline).

        Returns a dict with:
          ``score_delta``: current score minus baseline score.
          ``regression``: True when score dropped by more than 0.05.
          ``baseline_score``: Score from the prior run (or None).
          ``current_score``: Score from *result*.
        """
        history = self.list_results(result.scenario_name, limit=10)
        # The eval_run flow appends the current result via save_result
        # immediately before this call, so it is the trailing record. Drop it
        # by identity. The old score-based heuristic (``score != result.score``)
        # also discarded any genuine prior run that happened to share the
        # score, yielding the wrong baseline or None.
        current_dict = result.to_dict()
        if history and history[-1] == current_dict:
            history = history[:-1]
        if not history:
            return {
                "baseline_score": None,
                "current_score": result.score,
                "score_delta": None,
                "regression": False,
            }
        baseline_score = history[-1].get("score", 0.0)
        delta = round(result.score - baseline_score, 4)
        return {
            "baseline_score": baseline_score,
            "current_score": result.score,
            "score_delta": delta,
            "regression": delta < -0.05,
        }
