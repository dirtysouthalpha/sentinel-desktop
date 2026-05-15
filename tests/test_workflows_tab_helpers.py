"""Tests for gui/tabs/workflows_tab.py static helper _step_summary."""

from gui.tabs.workflows_tab import WorkflowsTab


class TestStepSummary:
    def test_script(self):
        result = WorkflowsTab._step_summary({"type": "script", "path": "clean.ps1"})
        assert result == "Run script: clean.ps1"

    def test_action(self):
        result = WorkflowsTab._step_summary(
            {
                "type": "action",
                "action": {"action": "click", "x": 10, "y": 20},
            }
        )
        assert "click" in result
        assert "x=10" in result

    def test_action_excludes_action_key(self):
        result = WorkflowsTab._step_summary(
            {
                "type": "action",
                "action": {"action": "click", "x": 5},
            }
        )
        # 'action' key should not appear in the params string
        assert "action=click" not in result

    def test_condition(self):
        result = WorkflowsTab._step_summary({"type": "condition", "check": "file_exists"})
        assert result == "If: file_exists"

    def test_loop(self):
        result = WorkflowsTab._step_summary({"type": "loop", "over": "items"})
        assert result == "Loop over: items"

    def test_sub_workflow(self):
        result = WorkflowsTab._step_summary({"type": "sub_workflow", "path": "sub.json"})
        assert result == "Sub-workflow: sub.json"

    def test_delay(self):
        result = WorkflowsTab._step_summary({"type": "delay", "delay_seconds": 5})
        assert result == "Wait 5s"

    def test_notify(self):
        result = WorkflowsTab._step_summary({"type": "notify", "message": "Done!"})
        assert result == "Notify: Done!"

    def test_unknown_type(self):
        result = WorkflowsTab._step_summary({"type": "custom"})
        assert result == "custom"

    def test_no_type_defaults_to_action(self):
        result = WorkflowsTab._step_summary({})
        assert "Action:" in result
