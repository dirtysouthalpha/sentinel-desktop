"""
Tests for the v30.0.0 NL Workflow Builder module.
"""
from core.nl_workflow import generate_workflow, _parse_step


class TestGenerateWorkflow:
    def test_simple_workflow(self):
        result = generate_workflow("open notepad, type hello world")
        assert result["success"]
        assert result["step_count"] >= 2

    def test_empty_description(self):
        result = generate_workflow("")
        assert not result["success"]

    def test_too_long(self):
        result = generate_workflow("x" * 6000)
        assert not result["success"]

    def test_no_actions_found(self):
        result = generate_workflow("just some random words here")
        assert not result["success"]

    def test_multi_step(self):
        desc = "open browser then click search then type query then press enter"
        result = generate_workflow(desc)
        assert result["success"]
        assert result["step_count"] >= 3


class TestParseStep:
    def test_open_action(self):
        step = _parse_step("open notepad")
        assert step is not None
        assert step["action"] == "launch"
        assert "notepad" in step["target"]

    def test_type_action(self):
        step = _parse_step("type hello world")
        assert step is not None
        assert step["action"] == "type_text"

    def test_unknown_action(self):
        step = _parse_step("randomize everything")
        assert step is None
