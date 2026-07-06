import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.commands.agent import AgentPlanner
from core.legacy_engine import CommandResult


class TestAgentPlanner:
    def setup_method(self):
        self.planner = AgentPlanner()
        self.planner.engine = MagicMock()

    def test_is_complex_with_then(self):
        assert self.planner.is_complex("brief me on cnn.com then check cpu") is True

    def test_is_complex_with_commas(self):
        assert self.planner.is_complex("check cpu, check memory, check disk") is True

    def test_is_not_complex_simple(self):
        assert self.planner.is_complex("cpu") is False

    def test_is_not_complex_single(self):
        assert self.planner.is_complex("brief me on cnn.com") is False

    def test_create_plan_multi_step(self):
        plan = self.planner.create_plan("check cpu, then check memory, then check disk")
        assert len(plan) >= 2

    def test_create_plan_single(self):
        plan = self.planner.create_plan("check cpu")
        assert len(plan) == 1

    def test_execute_plan_multiple_steps(self):
        self.planner.engine.execute.return_value = CommandResult(True, "ok")
        result = self.planner.execute_plan("check cpu, then check memory")
        assert result.success is True
        assert "PLAN" in result.message
        assert "Step 1" in result.message
        assert "Step 2" in result.message

    def test_execute_plan_single_returns_empty(self):
        result = self.planner.execute_plan("cpu")
        assert result.success is False
        assert result.message == ""

    def test_execute_plan_reports_success(self):
        self.planner.engine.execute.return_value = CommandResult(True, "CPU: 10%")
        """"Not actually multi-step, but test the reporting path"""
        result = self.planner.execute_plan("check cpu, then check memory")
        assert "complete" in result.message.lower()

    def test_execute_plan_reports_failure(self):
        self.planner.engine.execute.return_value = CommandResult(False, "failed")
        result = self.planner.execute_plan("check cpu, then check memory")
        assert result.success is True

    def test_plan_strips_filler_words(self):
        plan = self.planner.create_plan("hey sentinel, please check cpu")
        assert "hey" not in plan[0].lower()
        assert "please" not in plan[0].lower()
