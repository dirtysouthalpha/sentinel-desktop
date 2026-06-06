"""Test IT support script templates load and execute correctly."""

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock

from core.action_executor import ActionExecutor
from core.script_engine import ScriptEngine


def test_all_it_scripts_can_execute():
    """Verify all IT support scripts can be executed without errors."""
    scripts_dir = Path("scripts/it_support")
    failed = []
    executed = []

    # Mock the action executor
    mock_executor = MagicMock(spec=ActionExecutor)
    mock_executor.execute_action = Mock(return_value={"status": "success"})

    engine = ScriptEngine(mock_executor)

    for script_file in scripts_dir.glob("*.json"):
        try:
            with open(script_file) as f:
                template = json.load(f)

            # Try to execute the script (mock executor makes it safe)
            result = engine.run_script_from_dict(template)

            # Verify it returns a ScriptResult object
            assert hasattr(result, "success"), (
                f"{script_file.name}: result should have 'success' attribute"
            )
            assert hasattr(result, "steps_completed"), (
                f"{script_file.name}: result should have 'steps_completed' attribute"
            )

            executed.append(script_file.name)
        except Exception as e:
            failed.append(f"{script_file.name}: {str(e)}")

    assert not failed, f"Some scripts failed to execute: {failed}"
    assert len(executed) == 19, f"Expected 19 scripts, executed {len(executed)}"


def test_script_templates_have_required_fields():
    """Verify all script templates have required fields and valid structure."""
    scripts_dir = Path("scripts/it_support")
    required_fields = ["name", "description", "category", "steps"]

    for script_file in scripts_dir.glob("*.json"):
        with open(script_file) as f:
            template = json.load(f)

        # Check required fields
        for field in required_fields:
            assert field in template, f"{script_file.name}: missing '{field}' field"

        # Validate steps
        assert isinstance(template["steps"], list), f"{script_file.name}: steps must be a list"
        assert len(template["steps"]) > 0, f"{script_file.name}: steps cannot be empty"

        # Each step should have at least 'action' field
        for i, step in enumerate(template["steps"]):
            assert "action" in step, f"{script_file.name} step {i}: missing 'action' field"
