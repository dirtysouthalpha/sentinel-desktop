"""Verification tests for the bundled IT support script templates.

Guards every ``scripts/it_support/*.json`` template: it must parse, carry the
documented metadata, and pass the ScriptEngine validator against the real
ActionExecutor dispatch table (i.e. every step uses a known action and has
the required fields). This is the "verify all IT support script templates
load and execute correctly" item from the project checklist — short of an
actual Windows desktop, validating against the live action set is the
strongest load-time guarantee available.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.action_executor import ActionExecutor
from core.script_engine import _extract_required_params, _validate_script

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "it_support"
_TEMPLATES = sorted(_SCRIPTS_DIR.glob("*.json"))

_REQUIRED_TOP_LEVEL = {"name", "description", "steps", "parameters"}


def test_templates_directory_is_populated():
    assert _TEMPLATES, f"No IT support templates found in {_SCRIPTS_DIR}"


@pytest.fixture(scope="module")
def known_actions() -> set[str]:
    return set(ActionExecutor()._dispatch_table.keys())


@pytest.mark.parametrize("path", _TEMPLATES, ids=lambda p: p.name)
class TestTemplate:
    def test_parses_as_json(self, path):
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data, dict)

    def test_has_required_metadata(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = _REQUIRED_TOP_LEVEL - set(data)
        assert not missing, f"{path.name} missing keys: {sorted(missing)}"
        assert isinstance(data["steps"], list) and data["steps"], "steps must be a non-empty list"
        assert isinstance(data["parameters"], list)

    def test_steps_well_formed(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        for idx, step in enumerate(data["steps"], start=1):
            assert "action" in step, f"{path.name} step {idx} missing 'action'"
            assert "params" in step, f"{path.name} step {idx} missing 'params'"
            assert "description" in step, f"{path.name} step {idx} missing 'description'"

    def test_validates_against_engine(self, path, known_actions):
        data = json.loads(path.read_text(encoding="utf-8"))
        executor = ActionExecutor()
        # Supply dummy values for any declared/used parameters so the
        # required-parameter check passes — we're validating structure and
        # action types, not exercising a real run.
        params = dict.fromkeys(_extract_required_params(data), "x")
        errors = _validate_script(data, params=params, executor=executor)
        assert errors == [], f"{path.name} failed validation: {errors}"

    def test_declared_parameters_cover_placeholders(self, path):
        """Every ``{{placeholder}}`` used must be a declared parameter so the
        UI knows to prompt for it before running."""
        data = json.loads(path.read_text(encoding="utf-8"))
        declared = {p.get("name") for p in data.get("parameters", [])}
        used = _extract_required_params(data)
        undeclared = used - declared
        assert not undeclared, (
            f"{path.name} uses undeclared parameters: {sorted(undeclared)}"
        )

    def test_all_actions_are_known(self, path, known_actions):
        data = json.loads(path.read_text(encoding="utf-8"))
        for idx, step in enumerate(data["steps"], start=1):
            assert step["action"] in known_actions, (
                f"{path.name} step {idx} uses unknown action {step['action']!r}"
            )
